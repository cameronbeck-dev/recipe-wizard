from sqlalchemy import Column, String, Integer, ForeignKey, Boolean, JSON, Text, DateTime, func
from sqlalchemy.orm import relationship
from .base import BaseModel

class ShoppingList(BaseModel):
    """Shopping list aggregating ingredients from multiple recipes"""

    __tablename__ = "shopping_lists"

    # User who owns this shopping list
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Shopping list metadata
    name = Column(String(255), nullable=False, default="My Shopping List")
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    user = relationship("User", back_populates="shopping_lists")
    items = relationship("ShoppingListItem", back_populates="shopping_list", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ShoppingList(id={self.id}, user_id={self.user_id}, name='{self.name}')>"

    def to_api_format(self):
        """Convert to API format matching mobile app expectations"""
        return {
            "items": [item.to_api_format() for item in self.items],
            "lastUpdated": self.updated_at.isoformat() if self.updated_at else None
        }

class ShoppingListItem(BaseModel):
    """Individual item in a shopping list with consolidated quantities"""

    __tablename__ = "shopping_list_items"

    # Reference to shopping list
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False, index=True)

    # Ingredient information
    ingredient_name = Column(String(255), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)

    # Consolidated display (e.g., "2 whole + 1 cup") — the raw auto-computed value
    consolidated_display = Column(String(200), nullable=False)

    # User interaction
    is_checked = Column(Boolean, default=False, nullable=False)

    # Metadata
    consolidation_metadata = Column(JSON, nullable=True)  # Store consolidation logic details

    # Where this item originated: "recipe" or "manual"
    source = Column(String(20), nullable=False, server_default="recipe")

    # User-entered quantity that overrides the auto-computed display
    user_quantity_override = Column(String(200), nullable=True)

    # Snapshot of the auto-computed display at the moment the override was set,
    # used to detect staleness when new recipe contributions change the auto value
    override_baseline_display = Column(String(200), nullable=True)

    # Relationships
    shopping_list = relationship("ShoppingList", back_populates="items")
    recipe_breakdowns = relationship("ShoppingListRecipeBreakdown", back_populates="shopping_item", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ShoppingListItem(id={self.id}, name='{self.ingredient_name}', consolidated='{self.consolidated_display}')>"

    def to_api_format(self):
        """Convert to API format matching mobile app expectations"""
        auto_display = self.consolidated_display
        effective_display = self.user_quantity_override if self.user_quantity_override else auto_display
        override_is_stale = (
            self.user_quantity_override is not None
            and self.override_baseline_display != auto_display
        )
        return {
            "id": str(self.id),
            "ingredientName": self.ingredient_name,
            "category": self.category,
            "consolidatedDisplay": effective_display,
            "autoConsolidatedDisplay": auto_display,
            "source": self.source,
            "userQuantityOverride": self.user_quantity_override,
            "overrideIsStale": override_is_stale,
            "recipeBreakdown": [breakdown.to_api_format() for breakdown in self.recipe_breakdowns],
            "isChecked": self.is_checked
        }

class ShoppingListRecipeBreakdown(BaseModel):
    """Breakdown of how much of an ingredient comes from which recipe"""

    __tablename__ = "shopping_list_recipe_breakdowns"

    # References
    shopping_item_id = Column(Integer, ForeignKey("shopping_list_items.id"), nullable=False, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False, index=True)
    original_ingredient_id = Column(Integer, ForeignKey("recipe_ingredients.id"), nullable=False, index=True)

    # Recipe details
    recipe_title = Column(String(500), nullable=False)  # Denormalized for performance
    quantity = Column(String(100), nullable=False)  # Original quantity from recipe

    # Relationships
    shopping_item = relationship("ShoppingListItem", back_populates="recipe_breakdowns")
    recipe = relationship("Recipe")
    original_ingredient = relationship("RecipeIngredient")

    def __repr__(self):
        return f"<ShoppingListRecipeBreakdown(recipe='{self.recipe_title}', quantity='{self.quantity}')>"

    def to_api_format(self):
        """Convert to API format matching mobile app expectations"""
        return {
            "recipeId": str(self.recipe_id),
            "recipeTitle": self.recipe_title,
            "quantity": self.quantity
        }

class ShoppingListRecipeAssociation(BaseModel):
    """Track which recipes have been added to a shopping list"""

    __tablename__ = "shopping_list_recipe_associations"

    # References
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False, index=True)
    recipe_id = Column(Integer, ForeignKey("recipes.id"), nullable=False, index=True)

    # Metadata about when recipe was added
    added_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    shopping_list = relationship("ShoppingList")
    recipe = relationship("Recipe")

    def __repr__(self):
        return f"<ShoppingListRecipeAssociation(shopping_list_id={self.shopping_list_id}, recipe_id={self.recipe_id})>"