from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime

# Ingredient Schemas
class IngredientBase(BaseModel):
    """Base schema for recipe ingredients"""
    name: str = Field(..., min_length=1, max_length=255)
    amount: str = Field(..., min_length=1, max_length=100) 
    unit: Optional[str] = Field(None, max_length=50)
    category: str = Field(..., max_length=100)
    preparation: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = Field(None, max_length=500)
    is_optional: bool = False

class IngredientCreate(IngredientBase):
    """Schema for creating ingredients"""
    pass

class IngredientResponse(IngredientBase):
    """Schema for ingredient responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    recipe_id: int
    calories: Optional[float] = None
    created_at: datetime

class IngredientAPI(BaseModel):
    """Schema matching mobile app API expectations"""
    id: str
    name: str
    amount: str
    unit: Optional[str] = None
    category: str

# Recipe Schemas
class RecipeBase(BaseModel):
    """Base schema for recipes"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    prep_time: Optional[int] = Field(None, ge=0, le=480)  # 0-8 hours
    cook_time: Optional[int] = Field(None, ge=0, le=480)  # 0-8 hours
    servings: Optional[int] = Field(None, ge=1, le=50)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    instructions: List[str] = Field(..., min_items=1)
    tips: Optional[List[str]] = None
    cuisine_type: Optional[str] = Field(None, max_length=100)
    meal_type: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None

class RecipeCreate(RecipeBase):
    """Schema for creating recipes"""
    original_prompt: str = Field(..., min_length=1)
    llm_model: Optional[str] = None
    generation_metadata: Optional[Dict[str, Any]] = None
    ingredients: List[IngredientCreate] = Field(..., min_items=1)

class RecipeUpdate(BaseModel):
    """Schema for updating recipes"""
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    prep_time: Optional[int] = Field(None, ge=0, le=480)
    cook_time: Optional[int] = Field(None, ge=0, le=480)
    servings: Optional[int] = Field(None, ge=1, le=50)
    difficulty: Optional[str] = Field(None, pattern="^(easy|medium|hard)$")
    instructions: Optional[List[str]] = None
    tips: Optional[List[str]] = None
    cuisine_type: Optional[str] = Field(None, max_length=100)
    meal_type: Optional[str] = Field(None, max_length=50)
    tags: Optional[List[str]] = None

class RecipeResponse(RecipeBase):
    """Schema for recipe responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    original_prompt: str
    llm_model: Optional[str] = None
    calories_per_serving: Optional[int] = None
    ingredients: List[IngredientResponse] = []
    created_at: datetime
    updated_at: datetime

# Recipe API Schema (must come before RecipeGenerationResponse)
class RecipeAPI(BaseModel):
    """Recipe data matching mobile app expectations"""
    title: str
    description: Optional[str] = None
    instructions: List[str]
    prepTime: Optional[int] = None
    cookTime: Optional[int] = None
    servings: Optional[int] = None
    difficulty: Optional[str] = None
    tips: Optional[List[str]] = None

# Recipe Generation Schemas
class RecipeGenerationRequest(BaseModel):
    """Schema for recipe generation requests"""
    prompt: str = Field(..., min_length=3, max_length=1000)
    user_id: Optional[int] = None
    preferences: Optional[Dict[str, Any]] = None  # User preferences from mobile app

class RecipeGenerationResponse(BaseModel):
    """Schema matching mobile app expectations exactly"""
    id: str
    recipe: RecipeAPI
    ingredients: List[IngredientAPI]
    generatedAt: str  # ISO timestamp
    userPrompt: str

class RecipeModificationRequest(BaseModel):
    """Schema for recipe modification requests"""
    recipeId: str = Field(..., description="ID of the recipe to modify")
    modificationPrompt: str = Field(..., min_length=3, max_length=1000, description="What to change about the recipe")
    preferences: Optional[Dict[str, Any]] = None  # User preferences for context

# Recipe Ideas Generation Schemas
class RecipeIdeaGenerationRequest(BaseModel):
    """Schema for recipe idea generation requests"""
    prompt: str = Field(..., min_length=3, max_length=500, description="Prompt for generating recipe ideas")
    preferences: Optional[Dict[str, Any]] = None  # User preferences for context
    count: Optional[int] = Field(5, ge=1, le=20, description="Number of ideas to generate")

class RecipeIdea(BaseModel):
    """Individual recipe idea schema"""
    id: str = Field(..., description="Unique identifier for the idea")
    title: str = Field(..., min_length=1, max_length=100, description="Recipe idea title")
    description: str = Field(..., min_length=1, max_length=200, description="Brief description of the recipe")

class RecipeIdeasResponse(BaseModel):
    """Response schema for recipe ideas generation"""
    ideas: List[RecipeIdea] = Field(..., min_items=1, max_items=20)
    generatedAt: str = Field(..., description="ISO timestamp of generation")
    userPrompt: str = Field(..., description="Original user prompt")

# Saved Recipe Schemas
class SavedRecipeCreate(BaseModel):
    """Schema for saving recipes"""
    recipe_id: int
    is_favorite: bool = False
    personal_notes: Optional[str] = Field(None, max_length=2000)
    rating: Optional[int] = Field(None, ge=1, le=5)

class SavedRecipeUpdate(BaseModel):
    """Schema for updating saved recipes"""
    is_favorite: Optional[bool] = None
    personal_notes: Optional[str] = Field(None, max_length=2000)
    rating: Optional[int] = Field(None, ge=1, le=5)
    times_made: Optional[int] = Field(None, ge=0)
    custom_modifications: Optional[Dict[str, Any]] = None

class SavedRecipeResponse(BaseModel):
    """Schema for saved recipe responses"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    user_id: int
    recipe_id: int
    is_favorite: bool
    personal_notes: Optional[str] = None
    rating: Optional[int] = None
    times_made: int
    custom_modifications: Optional[Dict[str, Any]] = None
    recipe: RecipeResponse
    created_at: datetime
    updated_at: datetime

class SaveRecipeSuccessResponse(BaseModel):
    """Simple success response for saving recipes"""
    success: bool
    message: str
    savedRecipeId: str

# Recipe Import Schemas (guest -> account graduation)
class RecipeImportIngredient(BaseModel):
    """A single ingredient in a locally-stored guest recipe being imported"""
    name: str
    amount: str
    unit: Optional[str] = None
    category: str

class RecipeImportRecipe(BaseModel):
    """The recipe fields of a locally-stored guest recipe being imported"""
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    instructions: List[str] = Field(..., min_items=1)
    prepTime: Optional[int] = None
    cookTime: Optional[int] = None
    servings: Optional[int] = None
    difficulty: Optional[str] = None
    tips: Optional[List[str]] = None

class RecipeImportItem(BaseModel):
    """A single locally-stored guest recipe to import into an account"""
    recipe: RecipeImportRecipe
    ingredients: List[RecipeImportIngredient] = Field(default_factory=list)
    userPrompt: Optional[str] = None

class RecipeImportRequest(BaseModel):
    """Request body for POST /api/recipes/import"""
    recipes: List[RecipeImportItem] = Field(default_factory=list, max_items=100)

class RecipeImportResponse(BaseModel):
    """Response for POST /api/recipes/import"""
    imported: int
    skipped: int