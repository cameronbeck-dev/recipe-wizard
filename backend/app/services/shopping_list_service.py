from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from collections import defaultdict
import logging

from ..models import (
    User, Recipe, RecipeIngredient, ShoppingList, ShoppingListItem,
    ShoppingListRecipeBreakdown, ShoppingListRecipeAssociation
)
from ..schemas.shopping_list import (
    ShoppingListResponseSchema, AddRecipeToShoppingListRequest,
    UpdateShoppingListItemRequest, ClearShoppingListRequest
)
from . import unit_conversion

logger = logging.getLogger(__name__)


class RecipeAlreadyInListError(ValueError):
    """Raised when a recipe is already in the shopping list and duplicates aren't allowed"""

    def __init__(self, recipe_id: int, added_at):
        self.recipe_id = recipe_id
        self.added_at = added_at
        super().__init__(f"Recipe {recipe_id} is already in the shopping list")


class ShoppingListService:
    """Service for managing shopping lists and ingredient consolidation"""

    def __init__(self, db: Session):
        self.db = db

    def get_or_create_shopping_list(self, user_id: int) -> ShoppingList:
        """Get user's active shopping list or create a new one"""
        shopping_list = self.db.query(ShoppingList).filter(
            and_(
                ShoppingList.user_id == user_id,
                ShoppingList.is_active == True
            )
        ).first()

        if not shopping_list:
            shopping_list = ShoppingList(
                user_id=user_id,
                name="My Shopping List",
                is_active=True
            )
            self.db.add(shopping_list)
            self.db.commit()
            self.db.refresh(shopping_list)

        return shopping_list

    def _get_unit_system(self, user_id: int) -> str:
        user = self.db.query(User).filter(User.id == user_id).first()
        return user.units if user and user.units else 'metric'

    def add_recipe_to_shopping_list(
        self,
        user_id: int,
        recipe_id: int,
        allow_duplicate: bool = False
    ) -> ShoppingListResponseSchema:
        """Add a recipe's ingredients to the shopping list"""

        # Get the recipe
        recipe = self.db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            raise ValueError(f"Recipe with ID {recipe_id} not found")

        # Get or create shopping list
        shopping_list = self.get_or_create_shopping_list(user_id)

        if not allow_duplicate:
            existing_association = self.db.query(ShoppingListRecipeAssociation).filter(
                and_(
                    ShoppingListRecipeAssociation.shopping_list_id == shopping_list.id,
                    ShoppingListRecipeAssociation.recipe_id == recipe_id
                )
            ).first()
            if existing_association:
                raise RecipeAlreadyInListError(recipe_id, existing_association.added_at)

        unit_system = self._get_unit_system(user_id)

        # Track that this recipe was added
        recipe_association = ShoppingListRecipeAssociation(
            shopping_list_id=shopping_list.id,
            recipe_id=recipe_id
        )
        self.db.add(recipe_association)

        # Add ingredients to shopping list
        for ingredient in recipe.ingredients:
            self._add_ingredient_to_shopping_list(
                shopping_list, recipe, ingredient, unit_system
            )

        self.db.commit()
        return self._get_shopping_list_response(shopping_list)

    def _add_ingredient_to_shopping_list(
        self,
        shopping_list: ShoppingList,
        recipe: Recipe,
        ingredient: RecipeIngredient,
        unit_system: str
    ):
        """Add or update an ingredient in the shopping list"""

        # Check if ingredient already exists in shopping list
        existing_item = self.db.query(ShoppingListItem).filter(
            and_(
                ShoppingListItem.shopping_list_id == shopping_list.id,
                ShoppingListItem.ingredient_name == ingredient.name,
                ShoppingListItem.category == ingredient.category
            )
        ).first()

        if existing_item:
            # Add to existing item
            self._add_to_existing_item(existing_item, recipe, ingredient, unit_system)
        else:
            # Create new item
            self._create_new_shopping_item(shopping_list, recipe, ingredient)

    def _add_to_existing_item(
        self,
        existing_item: ShoppingListItem,
        recipe: Recipe,
        ingredient: RecipeIngredient,
        unit_system: str
    ):
        """Add ingredient quantity to existing shopping list item"""

        # Create recipe breakdown entry
        breakdown = ShoppingListRecipeBreakdown(
            shopping_item_id=existing_item.id,
            recipe_id=recipe.id,
            original_ingredient_id=ingredient.id,
            recipe_title=recipe.title,
            quantity=f"{ingredient.amount} {ingredient.unit or ''}".strip()
        )
        self.db.add(breakdown)
        self.db.flush()  # Ensure breakdown is available in relationships

        # Refresh the item to get updated relationships
        self.db.refresh(existing_item)

        # Recalculate consolidated display
        existing_item.consolidated_display = self._calculate_consolidated_display(existing_item, unit_system)

    def _create_new_shopping_item(
        self,
        shopping_list: ShoppingList,
        recipe: Recipe,
        ingredient: RecipeIngredient
    ):
        """Create a new shopping list item"""

        # Create shopping list item with proper unit handling
        consolidated_display = self._format_ingredient_display(ingredient.amount, ingredient.unit)
        item = ShoppingListItem(
            shopping_list_id=shopping_list.id,
            ingredient_name=ingredient.name,
            category=ingredient.category,
            consolidated_display=consolidated_display,
            is_checked=False,
            source="recipe"
        )
        self.db.add(item)
        self.db.flush()  # Get the item ID

        # Create recipe breakdown with proper formatting
        quantity_display = self._format_ingredient_display(ingredient.amount, ingredient.unit)
        breakdown = ShoppingListRecipeBreakdown(
            shopping_item_id=item.id,
            recipe_id=recipe.id,
            original_ingredient_id=ingredient.id,
            recipe_title=recipe.title,
            quantity=quantity_display
        )
        self.db.add(breakdown)

    def _format_ingredient_display(self, amount: str, unit: str) -> str:
        """Format ingredient display, handling N/A units properly"""
        if not unit or unit.lower() == 'n/a':
            # For non-measurement ingredients like "pinch" or "to taste"
            # Check if amount is already descriptive (like "to taste", "pinch", etc.)
            amount_lower = amount.lower() if amount else ""
            if any(word in amount_lower for word in ['pinch', 'to taste', 'handful', 'dash', 'splash', 'squeeze']):
                return amount  # e.g., "pinch", "to taste"
            else:
                return amount  # e.g., "1", "2" (for items like eggs, onions)
        else:
            return f"{amount} {unit}".strip()

    def _calculate_consolidated_display(self, item: ShoppingListItem, unit_system: str) -> str:
        """Calculate consolidated display for an item with multiple recipe sources"""
        quantities = [breakdown.quantity for breakdown in item.recipe_breakdowns]

        manual_quantity = None
        if item.consolidation_metadata:
            manual_quantity = item.consolidation_metadata.get("manual_quantity")
        if manual_quantity:
            quantities.append(manual_quantity)

        if not quantities:
            return ""

        if len(quantities) == 1:
            return quantities[0]

        return unit_conversion.sum_quantities(quantities, unit_system)

    def get_shopping_list(self, user_id: int) -> ShoppingListResponseSchema:
        """Get user's shopping list"""
        shopping_list = self.get_or_create_shopping_list(user_id)
        return self._get_shopping_list_response(shopping_list)

    def _get_shopping_list_response(self, shopping_list: ShoppingList) -> ShoppingListResponseSchema:
        """Convert shopping list to API response format"""
        return ShoppingListResponseSchema(
            items=[item.to_api_format() for item in shopping_list.items],
            last_updated=shopping_list.updated_at
        )

    def update_item_status(
        self,
        user_id: int,
        item_id: int,
        is_checked: bool
    ) -> ShoppingListItem:
        """Update the checked status of a shopping list item"""

        # Verify item belongs to user
        item = self.db.query(ShoppingListItem).join(ShoppingList).filter(
            and_(
                ShoppingListItem.id == item_id,
                ShoppingList.user_id == user_id
            )
        ).first()

        if not item:
            raise ValueError(f"Shopping list item {item_id} not found for user {user_id}")

        item.is_checked = is_checked
        self.db.commit()
        self.db.refresh(item)

        return item

    def _get_owned_item(self, user_id: int, item_id: int) -> ShoppingListItem:
        item = self.db.query(ShoppingListItem).join(ShoppingList).filter(
            and_(
                ShoppingListItem.id == item_id,
                ShoppingList.user_id == user_id
            )
        ).first()

        if not item:
            raise ValueError(f"Shopping list item {item_id} not found for user {user_id}")

        return item

    def set_item_quantity(
        self,
        user_id: int,
        item_id: int,
        quantity: Optional[str]
    ) -> ShoppingListItem:
        """Set or clear a manual quantity override on an item"""

        item = self._get_owned_item(user_id, item_id)

        if quantity is None:
            item.user_quantity_override = None
            item.override_baseline_display = None
        else:
            item.user_quantity_override = quantity
            item.override_baseline_display = item.consolidated_display

        self.db.commit()
        self.db.refresh(item)

        return item

    def delete_item(self, user_id: int, item_id: int) -> ShoppingListResponseSchema:
        """Delete a single shopping list item"""

        item = self._get_owned_item(user_id, item_id)
        shopping_list = item.shopping_list

        recipe_ids = {b.recipe_id for b in item.recipe_breakdowns}

        # cascade="all, delete-orphan" on recipe_breakdowns handles the FK cleanup
        self.db.delete(item)
        self.db.flush()

        self._prune_associations(shopping_list.id, recipe_ids)

        self.db.commit()
        self.db.refresh(shopping_list)

        return self._get_shopping_list_response(shopping_list)

    def _prune_associations(self, shopping_list_id: int, recipe_ids):
        """Delete recipe associations that no longer have any breakdowns"""
        for recipe_id in recipe_ids:
            remaining = self.db.query(ShoppingListRecipeBreakdown).join(ShoppingListItem).filter(
                and_(
                    ShoppingListItem.shopping_list_id == shopping_list_id,
                    ShoppingListRecipeBreakdown.recipe_id == recipe_id
                )
            ).count()
            if remaining == 0:
                self.db.query(ShoppingListRecipeAssociation).filter(
                    and_(
                        ShoppingListRecipeAssociation.shopping_list_id == shopping_list_id,
                        ShoppingListRecipeAssociation.recipe_id == recipe_id
                    )
                ).delete(synchronize_session=False)

    def clear_checked_items(self, user_id: int) -> Tuple[int, ShoppingListResponseSchema]:
        """Delete only the checked items from the user's shopping list"""

        shopping_list = self.get_or_create_shopping_list(user_id)

        checked_items = self.db.query(ShoppingListItem).filter(
            and_(
                ShoppingListItem.shopping_list_id == shopping_list.id,
                ShoppingListItem.is_checked == True
            )
        ).all()

        removed_count = len(checked_items)
        recipe_ids = set()
        item_ids = []
        for item in checked_items:
            recipe_ids.update(b.recipe_id for b in item.recipe_breakdowns)
            item_ids.append(item.id)

        if item_ids:
            self.db.query(ShoppingListRecipeBreakdown).filter(
                ShoppingListRecipeBreakdown.shopping_item_id.in_(item_ids)
            ).delete(synchronize_session=False)

            self.db.query(ShoppingListItem).filter(
                ShoppingListItem.id.in_(item_ids)
            ).delete(synchronize_session=False)

        self.db.flush()
        self._prune_associations(shopping_list.id, recipe_ids)

        self.db.commit()
        self.db.refresh(shopping_list)

        return removed_count, self._get_shopping_list_response(shopping_list)

    def add_manual_item(
        self,
        user_id: int,
        ingredient_name: str,
        quantity: Optional[str],
        category: Optional[str]
    ) -> ShoppingListItem:
        """Add (or merge into) a manual shopping list item"""

        shopping_list = self.get_or_create_shopping_list(user_id)
        category = category or "pantry"
        unit_system = self._get_unit_system(user_id)

        existing_item = self.db.query(ShoppingListItem).filter(
            and_(
                ShoppingListItem.shopping_list_id == shopping_list.id,
                ShoppingListItem.ingredient_name == ingredient_name,
                ShoppingListItem.category == category
            )
        ).first()

        if existing_item:
            metadata = dict(existing_item.consolidation_metadata or {})
            if quantity:
                metadata["manual_quantity"] = quantity
            existing_item.consolidation_metadata = metadata
            existing_item.consolidated_display = self._calculate_consolidated_display(existing_item, unit_system)
            self.db.commit()
            self.db.refresh(existing_item)
            return existing_item

        metadata = {"manual_quantity": quantity} if quantity else {}
        item = ShoppingListItem(
            shopping_list_id=shopping_list.id,
            ingredient_name=ingredient_name,
            category=category,
            consolidated_display=quantity or "",
            is_checked=False,
            source="manual",
            consolidation_metadata=metadata
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)

        return item

    def get_shopping_list_recipes(self, user_id: int) -> List[ShoppingListRecipeAssociation]:
        """Get the recipes currently contributing to the user's shopping list"""

        shopping_list = self.get_or_create_shopping_list(user_id)

        associations = self.db.query(ShoppingListRecipeAssociation).filter(
            ShoppingListRecipeAssociation.shopping_list_id == shopping_list.id
        ).order_by(ShoppingListRecipeAssociation.added_at.desc()).all()

        seen = set()
        result = []
        for association in associations:
            if association.recipe_id in seen:
                continue
            seen.add(association.recipe_id)
            result.append(association)

        return result

    def clear_shopping_list(self, user_id: int) -> bool:
        """Clear all items from user's shopping list"""
        try:
            shopping_list = self.get_or_create_shopping_list(user_id)

            # Get all shopping list item IDs first
            item_ids = self.db.query(ShoppingListItem.id).filter(
                ShoppingListItem.shopping_list_id == shopping_list.id
            ).all()
            item_ids = [item_id[0] for item_id in item_ids]

            # Delete all recipe breakdowns for these items
            if item_ids:
                self.db.query(ShoppingListRecipeBreakdown).filter(
                    ShoppingListRecipeBreakdown.shopping_item_id.in_(item_ids)
                ).delete(synchronize_session=False)

            # Delete all items (recipe-sourced and manual)
            self.db.query(ShoppingListItem).filter(
                ShoppingListItem.shopping_list_id == shopping_list.id
            ).delete(synchronize_session=False)

            # Delete all recipe associations
            self.db.query(ShoppingListRecipeAssociation).filter(
                ShoppingListRecipeAssociation.shopping_list_id == shopping_list.id
            ).delete(synchronize_session=False)

            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise e

    def remove_recipe_from_shopping_list(
        self,
        user_id: int,
        recipe_id: int
    ) -> ShoppingListResponseSchema:
        """Remove a specific recipe's ingredients from the shopping list"""

        shopping_list = self.get_or_create_shopping_list(user_id)
        unit_system = self._get_unit_system(user_id)

        # Find all recipe associations for this recipe (there may be more than
        # one if the recipe was added multiple times with allow_duplicate)
        recipe_associations = self.db.query(ShoppingListRecipeAssociation).filter(
            and_(
                ShoppingListRecipeAssociation.shopping_list_id == shopping_list.id,
                ShoppingListRecipeAssociation.recipe_id == recipe_id
            )
        ).all()

        if not recipe_associations:
            raise ValueError(f"Recipe {recipe_id} not found in shopping list")

        # Find all breakdowns for this recipe
        recipe_breakdowns = self.db.query(ShoppingListRecipeBreakdown).join(
            ShoppingListItem
        ).filter(
            and_(
                ShoppingListItem.shopping_list_id == shopping_list.id,
                ShoppingListRecipeBreakdown.recipe_id == recipe_id
            )
        ).all()

        # For each breakdown, either remove it or update the item
        for breakdown in recipe_breakdowns:
            item = breakdown.shopping_item

            # Remove this breakdown
            self.db.delete(breakdown)

            # Check if item has other breakdowns
            remaining_breakdowns = [b for b in item.recipe_breakdowns if b.id != breakdown.id]

            has_manual_data = bool(item.consolidation_metadata and "manual_quantity" in item.consolidation_metadata)

            if not remaining_breakdowns and not has_manual_data:
                # No other recipes use this ingredient and no manual data to preserve
                self.db.delete(item)
            else:
                # Either other recipes still use it, or manual data must be preserved
                item.consolidated_display = self._calculate_consolidated_display(item, unit_system)

        # Remove all associations for this recipe
        for recipe_association in recipe_associations:
            self.db.delete(recipe_association)
        self.db.commit()

        return self._get_shopping_list_response(shopping_list)
