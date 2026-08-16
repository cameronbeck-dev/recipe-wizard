from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

# Job Request Schemas
class RecipeJobCreate(BaseModel):
    """Schema for creating recipe generation jobs"""
    prompt: str = Field(..., min_length=3, max_length=1000)
    preferences: Optional[Dict[str, Any]] = None

class RecipeModificationJobCreate(BaseModel):
    """Schema for creating recipe modification jobs"""
    recipe_id: str = Field(..., description="ID of the recipe to modify")
    modification_prompt: str = Field(..., min_length=3, max_length=1000)
    preferences: Optional[Dict[str, Any]] = None

# Job Response Schemas
class RecipeJobStatus(BaseModel):
    """Schema for job status responses"""
    id: str
    status: str  # pending, processing, completed, failed
    job_type: str  # generate, modify
    prompt: str
    progress: int  # 0-100
    recipe_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    estimated_completion: Optional[str] = None

class RecipeJobCreateResponse(BaseModel):
    """Response when creating a new job"""
    job_id: str
    status: str
    message: str
    estimated_completion: str
    status_url: str
    polling_interval: int = 3  # seconds
    guest_generations_remaining: Optional[int] = None
    guest_quota_reset_at: Optional[str] = None

class RecipeJobResult(BaseModel):
    """Complete job result with recipe data"""
    job_id: str
    status: str
    recipe_id: Optional[str] = None  # None for guest jobs (no Recipe row created)
    recipe: Dict[str, Any]  # Full recipe data
    ingredients: list[Dict[str, Any]]  # Full ingredients data
    generated_at: str
    user_prompt: str
    generation_metadata: Optional[Dict[str, Any]] = None

class RecipeJobError(BaseModel):
    """Job error response"""
    job_id: str
    status: str = "failed"
    error_message: str
    error_type: str  # timeout, validation, connection, etc.
    retry_available: bool = False