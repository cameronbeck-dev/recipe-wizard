from fastapi import APIRouter, Depends, HTTPException, status
from fastapi_limiter.depends import RateLimiter
import os
from sqlalchemy.orm import Session
from typing import Optional
import logging

from ..database import get_db
from ..models import User, Recipe, RecipeIngredient, SavedRecipe
from ..schemas import (
    RecipeGenerationRequest, RecipeGenerationResponse, RecipeModificationRequest,
    RecipeIdeaGenerationRequest, RecipeIdeasResponse,
    RecipeAPI, IngredientAPI, SavedRecipeResponse, SaveRecipeSuccessResponse, ErrorResponse,
    RecipeImportRequest, RecipeImportResponse
)
from ..utils.auth import get_current_user
from ..services.llm_service import llm_service
from ..services.openai_service import RecipeRequestRefused

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/recipes", tags=["recipes"])

# Rate limiting configuration (optional)
_ENABLE_RATE_LIMIT = os.getenv("ENABLE_RATE_LIMIT", "true").lower() == "true" and bool(os.getenv("REDIS_URL"))
_RATE_LIMIT_TIMES = int(os.getenv("RATE_LIMIT_TIMES", "5"))
_RATE_LIMIT_SECONDS = int(os.getenv("RATE_LIMIT_SECONDS", "60"))
_generate_deps = [Depends(RateLimiter(times=_RATE_LIMIT_TIMES, seconds=_RATE_LIMIT_SECONDS))] if _ENABLE_RATE_LIMIT else None

@router.post("/generate", response_model=RecipeGenerationResponse, dependencies=_generate_deps)
async def generate_recipe(
    request: RecipeGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate a new recipe based on user prompt using LLM.
    
    Uses user preferences to customize the recipe generation.
    Returns structured recipe data with ingredients and instructions.
    """
    try:
        logger.info(f"Generating recipe for user {current_user.email} with prompt: {request.prompt[:100]}...")
        
        # Generate recipe using LLM service with user context
        generation_result = await llm_service.generate_recipe_with_fallback(request, current_user)
        
        # Convert to API response format first
        api_response = llm_service.convert_to_api_response(
            generation_result['recipe_data'],
            request.prompt,
            generation_result
        )
        
        # Create the response object to verify it's valid before saving to database
        response = RecipeGenerationResponse(
            id=api_response['id'],  # This will be temporary, replaced after DB save
            recipe=RecipeAPI(**api_response['recipe']),
            ingredients=[IngredientAPI(**ing) for ing in api_response['ingredients']],
            generatedAt=api_response['generatedAt'],
            userPrompt=api_response['userPrompt']
        )
        
        # Only save to database after successful API response creation
        recipe_id = await _save_recipe_to_database(
            db, 
            current_user, 
            generation_result['recipe_data'], 
            request.prompt,
            generation_result
        )
        
        # Update response with actual database ID
        response.id = str(recipe_id)
        
        return response
        
    except ConnectionError as e:
        logger.error(f"LLM service connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except RecipeRequestRefused as e:
        logger.warning(f"Recipe generation refused: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        logger.error(f"Recipe generation validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recipe generation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during recipe generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recipe generation failed due to server error"
        )

@router.post("/modify", response_model=RecipeGenerationResponse, dependencies=_generate_deps)
async def modify_recipe(
    request: RecipeModificationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Modify an existing recipe based on user feedback.
    
    Takes the original recipe and a modification prompt, then generates
    a new version with the requested changes while preserving the core recipe.
    """
    try:
        # Convert recipeId from string to int for database lookup
        try:
            recipe_id = int(request.recipeId)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid recipe ID format"
            )
            
        logger.info(f"Modifying recipe {recipe_id} for user {current_user.email}")
        logger.info(f"Modification request: {request.modificationPrompt[:100]}...")
        
        # Get the original recipe from database
        original_recipe = db.query(Recipe).filter(
            Recipe.id == recipe_id,
            Recipe.created_by_id == current_user.id  # Ensure user owns the recipe
        ).first()
        
        if not original_recipe:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found or you don't have permission to modify it"
            )
        
        # Get original ingredients
        original_ingredients = db.query(RecipeIngredient).filter(
            RecipeIngredient.recipe_id == recipe_id
        ).all()
        
        # Generate modified recipe using LLM service
        modification_result = await llm_service.modify_recipe_with_fallback(
            original_recipe, 
            original_ingredients,
            request.modificationPrompt,
            current_user,
            request.preferences
        )
        
        # Convert to API response format first
        api_response = llm_service.convert_to_api_response(
            modification_result['recipe_data'],
            f"Modified: {request.modificationPrompt}",
            modification_result
        )
        
        # Create the response object to verify it's valid before saving to database
        response = RecipeGenerationResponse(
            id=api_response['id'],  # This will be temporary, replaced after DB save
            recipe=RecipeAPI(**api_response['recipe']),
            ingredients=[IngredientAPI(**ing) for ing in api_response['ingredients']],
            generatedAt=api_response['generatedAt'],
            userPrompt=api_response['userPrompt']
        )
        
        # Only save to database after successful API response creation
        new_recipe_id = await _save_recipe_to_database(
            db, 
            current_user, 
            modification_result['recipe_data'],
            f"Modified: {request.modificationPrompt}",  # Store the modification as the new prompt
            modification_result
        )
        
        # Update response with actual database ID
        response.id = str(new_recipe_id)
        
        return response
        
    except HTTPException:
        raise
    except ConnectionError as e:
        logger.error(f"LLM service connection error during modification: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except RecipeRequestRefused as e:
        logger.warning(f"Recipe modification refused: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        logger.error(f"Recipe modification validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recipe modification failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during recipe modification: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recipe modification failed due to server error"
        )

@router.post("/generate-ideas", response_model=RecipeIdeasResponse, dependencies=_generate_deps)
async def generate_recipe_ideas(
    request: RecipeIdeaGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate recipe ideas based on user prompt using LLM.
    
    This is a faster, lighter-weight endpoint for brainstorming recipe concepts.
    Ideas are not stored in the database and are designed for quick inspiration.
    """
    try:
        logger.info(f"Generating {request.count} recipe ideas for user {current_user.email} with prompt: {request.prompt[:100]}...")
        
        # Generate recipe ideas using LLM service with user context
        ideas_result = await llm_service.generate_recipe_ideas_with_fallback(request, current_user)
        
        logger.info(f"Successfully generated {len(ideas_result['ideas'])} recipe ideas")
        
        return RecipeIdeasResponse(
            ideas=ideas_result['ideas'],
            generatedAt=ideas_result['generatedAt'], 
            userPrompt=request.prompt
        )
        
    except ConnectionError as e:
        logger.error(f"LLM service connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )
    except RecipeRequestRefused as e:
        logger.warning(f"Recipe ideas generation refused: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except ValueError as e:
        logger.error(f"Recipe ideas generation validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Recipe ideas generation failed: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error during recipe ideas generation: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Recipe ideas generation failed due to server error"
        )

@router.get("/history")
async def get_recipe_history(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's recipe generation history.
    
    Returns paginated list of previously generated recipes.
    """
    try:
        recipes_query = db.query(Recipe).filter(
            Recipe.created_by_id == current_user.id
        ).order_by(Recipe.created_at.desc())
        
        total_count = recipes_query.count()
        recipes = recipes_query.offset(offset).limit(limit).all()
        
        recipe_responses = []
        for recipe in recipes:
            # Get ingredients for this recipe
            ingredients = db.query(RecipeIngredient).filter(
                RecipeIngredient.recipe_id == recipe.id
            ).all()
            
            recipe_responses.append({
                "id": str(recipe.id),
                "recipe": {
                    "title": recipe.title,
                    "description": recipe.description,
                    "instructions": recipe.instructions,
                    "prepTime": recipe.prep_time,
                    "cookTime": recipe.cook_time,
                    "servings": recipe.servings,
                    "difficulty": recipe.difficulty,
                    "tips": recipe.tips
                },
                "ingredients": [
                    {
                        "id": str(ing.id),
                        "name": ing.name,
                        "amount": ing.amount,
                        "unit": ing.unit,
                        "category": ing.category
                    }
                    for ing in ingredients
                ],
                "generatedAt": recipe.created_at.isoformat(),
                "userPrompt": recipe.original_prompt
            })
        
        return {
            "success": True,
            "recipes": recipe_responses,
            "pagination": {
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "hasMore": offset + limit < total_count
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching recipe history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch recipe history"
        )

@router.post("/save/{recipe_id}", response_model=SaveRecipeSuccessResponse)
async def save_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Save a recipe to user's favorites.
    
    Adds recipe to saved recipes collection for easy access.
    """
    try:
        # Check if recipe exists
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipe not found"
            )
        
        # Check if already saved
        existing_save = db.query(SavedRecipe).filter(
            SavedRecipe.user_id == current_user.id,
            SavedRecipe.recipe_id == recipe_id
        ).first()
        
        if existing_save:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Recipe already saved"
            )
        
        # Create saved recipe record
        saved_recipe = SavedRecipe(
            user_id=current_user.id,
            recipe_id=recipe_id
        )
        
        db.add(saved_recipe)
        db.commit()
        db.refresh(saved_recipe)
        
        logger.info(f"Recipe {recipe_id} saved by user {current_user.email}")
        
        return SaveRecipeSuccessResponse(
            success=True,
            message="Recipe saved successfully",
            savedRecipeId=str(saved_recipe.id)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving recipe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save recipe"
        )

@router.delete("/saved/{recipe_id}")
async def unsave_recipe(
    recipe_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Remove recipe from user's saved recipes.
    """
    try:
        # Find saved recipe record
        saved_recipe = db.query(SavedRecipe).filter(
            SavedRecipe.user_id == current_user.id,
            SavedRecipe.recipe_id == recipe_id
        ).first()
        
        if not saved_recipe:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Saved recipe not found"
            )
        
        # Delete saved recipe record
        db.delete(saved_recipe)
        db.commit()
        
        logger.info(f"Recipe {recipe_id} unsaved by user {current_user.email}")
        
        return {
            "success": True,
            "message": "Recipe removed from saved recipes"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error unsaving recipe: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to unsave recipe"
        )

@router.get("/saved")
async def get_saved_recipes(
    limit: int = 20,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get user's saved recipes.
    
    Returns paginated list of user's favorite recipes.
    """
    try:
        # Join saved recipes with actual recipe data
        saved_recipes_query = db.query(Recipe).join(
            SavedRecipe, Recipe.id == SavedRecipe.recipe_id
        ).filter(
            SavedRecipe.user_id == current_user.id
        ).order_by(SavedRecipe.created_at.desc())
        
        total_count = saved_recipes_query.count()
        recipes = saved_recipes_query.offset(offset).limit(limit).all()
        
        recipe_responses = []
        for recipe in recipes:
            # Get ingredients for this recipe
            ingredients = db.query(RecipeIngredient).filter(
                RecipeIngredient.recipe_id == recipe.id
            ).all()
            
            # Get saved recipe record for saved timestamp
            saved_recipe = db.query(SavedRecipe).filter(
                SavedRecipe.user_id == current_user.id,
                SavedRecipe.recipe_id == recipe.id
            ).first()
            
            recipe_responses.append({
                "id": str(recipe.id),
                "recipe": {
                    "title": recipe.title,
                    "description": recipe.description,
                    "instructions": recipe.instructions,
                    "prepTime": recipe.prep_time,
                    "cookTime": recipe.cook_time,
                    "servings": recipe.servings,
                    "difficulty": recipe.difficulty,
                    "tips": recipe.tips
                },
                "ingredients": [
                    {
                        "id": str(ing.id),
                        "name": ing.name,
                        "amount": ing.amount,
                        "unit": ing.unit,
                        "category": ing.category
                    }
                    for ing in ingredients
                ],
                "generatedAt": recipe.created_at.isoformat(),
                "userPrompt": recipe.original_prompt,
                "savedAt": saved_recipe.created_at.isoformat() if saved_recipe else recipe.created_at.isoformat()
            })
        
        return {
            "success": True,
            "recipes": recipe_responses,
            "pagination": {
                "total": total_count,
                "offset": offset,
                "limit": limit,
                "hasMore": offset + limit < total_count
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching saved recipes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch saved recipes"
        )

@router.post("/import", response_model=RecipeImportResponse)
async def import_guest_recipes(
    request: RecipeImportRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import locally-stored guest recipes into the authenticated user's account.

    Fires on both register and login, so the account may already hold
    matching recipes. Dedupe is a deliberately cheap "good enough, not
    exact" heuristic (trimmed, casefolded title match) — do not "fix" this
    into fuzzy matching, ingredient similarity, or content hashing.
    """
    try:
        existing_titles = {
            title.strip().casefold()
            for (title,) in db.query(Recipe.title)
            .join(SavedRecipe, Recipe.id == SavedRecipe.recipe_id)
            .filter(SavedRecipe.user_id == current_user.id)
            .all()
        }

        imported = 0
        skipped = 0
        seen_in_batch = set()

        for item in request.recipes:
            normalized_title = item.recipe.title.strip().casefold()

            if normalized_title in existing_titles or normalized_title in seen_in_batch:
                skipped += 1
                continue

            seen_in_batch.add(normalized_title)

            recipe = Recipe(
                title=item.recipe.title,
                description=item.recipe.description or '',
                instructions=item.recipe.instructions,
                prep_time=item.recipe.prepTime,
                cook_time=item.recipe.cookTime,
                servings=item.recipe.servings or 4,
                difficulty=item.recipe.difficulty or 'medium',
                tips=item.recipe.tips or [],
                original_prompt=item.userPrompt or item.recipe.title,
                created_by_id=current_user.id,
            )
            db.add(recipe)
            db.flush()

            for ing in item.ingredients:
                db.add(RecipeIngredient(
                    recipe_id=recipe.id,
                    name=ing.name,
                    amount=str(ing.amount),
                    unit=ing.unit or '',
                    category=ing.category or 'pantry'
                ))

            db.add(SavedRecipe(user_id=current_user.id, recipe_id=recipe.id))
            imported += 1

        db.commit()

        logger.info(f"Imported {imported} guest recipes for user {current_user.email} ({skipped} skipped)")

        return RecipeImportResponse(imported=imported, skipped=skipped)

    except Exception as e:
        db.rollback()
        logger.error(f"Error importing guest recipes: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to import recipes"
        )

async def _save_recipe_to_database(
    db: Session, 
    user: User, 
    recipe_data: dict, 
    user_prompt: str,
    generation_metadata: dict
) -> int:
    """
    Helper function to save generated recipe to database.
    
    Returns the ID of the saved recipe.
    """
    try:
        # Create recipe record
        recipe = Recipe(
            title=recipe_data['recipe']['title'],
            description=recipe_data['recipe'].get('description', ''),
            instructions=recipe_data['recipe']['instructions'],
            prep_time=recipe_data['recipe'].get('prepTime'),
            cook_time=recipe_data['recipe'].get('cookTime'),
            servings=recipe_data['recipe'].get('servings', 4),
            difficulty=recipe_data['recipe'].get('difficulty', 'medium'),
            tips=recipe_data['recipe'].get('tips', []),
            original_prompt=user_prompt,
            created_by_id=user.id,
            generation_metadata={
                'model': generation_metadata['model'],
                'generation_time_ms': generation_metadata['generation_time_ms'],
                'token_count': generation_metadata['token_count'],
                'prompt_tokens': generation_metadata['prompt_tokens']
            }
        )
        
        db.add(recipe)
        db.flush()  # Get the ID without committing
        
        # Create ingredient records
        for ingredient_data in recipe_data['ingredients']:
            ingredient = RecipeIngredient(
                recipe_id=recipe.id,
                name=ingredient_data['name'],
                amount=str(ingredient_data['amount']),
                unit=ingredient_data.get('unit', ''),
                category=ingredient_data.get('category', 'pantry')
            )
            db.add(ingredient)
        
        db.commit()
        
        logger.info(f"Recipe '{recipe.title}' saved to database with ID {recipe.id}")
        
        return recipe.id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error saving recipe to database: {e}")
        raise ValueError(f"Failed to save recipe: {str(e)}")
