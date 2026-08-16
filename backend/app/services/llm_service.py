import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from ..models import User
from ..schemas import RecipeGenerationRequest, RecipeIdeaGenerationRequest, RecipeAPI, IngredientAPI
from .openai_service import openai_service

# Configure logging
logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with LLM for recipe generation - now using OpenAI"""
    
    def __init__(self):
        self.openai_service = openai_service
        
    async def check_llm_connection(self) -> bool:
        """Check if LLM service is available"""
        return await self.openai_service.check_openai_connection()
    
    def get_available_models(self) -> List[str]:
        """Get list of available models"""
        return self.openai_service.get_available_models()
    
    async def generate_recipe(
        self, 
        request: RecipeGenerationRequest, 
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Generate a recipe using the LLM.
        Returns the raw response data for further processing.
        """
        return await self.openai_service.generate_recipe(request, user)
    
    def convert_to_api_response(
        self, 
        recipe_data: Dict[str, Any], 
        original_prompt: str,
        generation_metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Convert LLM response to API format expected by mobile app"""
        try:
            recipe = recipe_data['recipe']
            ingredients = recipe_data['ingredients']
            
            # Convert to API format
            recipe_api = RecipeAPI(
                title=recipe['title'],
                description=recipe.get('description'),
                instructions=recipe['instructions'],
                prepTime=recipe.get('prepTime'),
                cookTime=recipe.get('cookTime'),
                servings=recipe.get('servings', 4),
                difficulty=recipe.get('difficulty'),
                tips=recipe.get('tips', [])
            )
            
            ingredients_api = [
                IngredientAPI(
                    id=str(i),  # Temporary ID for frontend
                    name=ing['name'],
                    amount=str(ing['amount']),
                    unit=ing.get('unit'),
                    category=ing['category']  # Should always exist after validation
                )
                for i, ing in enumerate(ingredients)
            ]
            
            response = {
                "id": f"temp_{int(time.time())}",  # Temporary ID before saving
                "recipe": recipe_api.model_dump(),
                "ingredients": [ing.model_dump() for ing in ingredients_api],
                "generatedAt": datetime.utcnow().isoformat(),
                "userPrompt": original_prompt
            }
            
            # Add retry information if available
            if generation_metadata.get('retry_count', 0) > 0:
                response['retryCount'] = generation_metadata['retry_count']
                response['retryMessage'] = generation_metadata.get('retry_message')
            
            return response
            
        except Exception as e:
            logger.error(f"Failed to convert to API response: {e}")
            raise ValueError(f"Response conversion failed: {str(e)}")
    
    async def generate_recipe_with_fallback(
        self, 
        request: RecipeGenerationRequest, 
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Generate recipe using LLM - no fallback, proper error handling
        """
        # Check if OpenAI is available
        if not await self.check_llm_connection():
            logger.error("OpenAI service is not available")
            raise ConnectionError("Unable to connect to recipe generation service. Please try again later.")
        
        # Try LLM generation
        return await self.generate_recipe(request, user)
    
    async def modify_recipe_with_fallback(
        self,
        original_recipe,
        original_ingredients,
        modification_prompt: str,
        user: Optional[User] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Modify an existing recipe using LLM with fallback error handling
        """
        # Check if OpenAI is available
        if not await self.check_llm_connection():
            logger.error("OpenAI service is not available")
            raise ConnectionError("Unable to connect to recipe modification service. Please try again later.")
        
        # Generate modified recipe using OpenAI service
        return await self.openai_service.modify_recipe(
            original_recipe,
            original_ingredients, 
            modification_prompt,
            user,
            preferences
        )
    
    async def generate_recipe_ideas_with_fallback(
        self,
        request: RecipeIdeaGenerationRequest,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """
        Generate recipe ideas using LLM with fallback error handling
        """
        # Check if OpenAI is available
        if not await self.check_llm_connection():
            logger.error("OpenAI service is not available")
            raise ConnectionError("Unable to connect to recipe ideas service. Please try again later.")
        
        # Get user preferences context if available
        user_preferences = None
        
        if request.preferences:
            logger.info("Using preferences from API request (mobile app) for ideas")
            user_preferences = self.openai_service._generate_preference_context_from_request(request.preferences)
            logger.info(f"Request preferences applied for ideas generation")
            
        elif user:
            logger.info(f"Using database preferences for user {user.email} for ideas")
            user_preferences = user.get_preference_context()
            
        # Generate recipe ideas using OpenAI service
        return await self.openai_service.generate_recipe_ideas(
            request.prompt,
            request.count,
            user_preferences,
            user=user
        )

# Global LLM service instance
llm_service = LLMService()

# Utility functions for easy access
async def generate_recipe_from_prompt(
    prompt: str, 
    user: Optional[User] = None
) -> Dict[str, Any]:
    """Convenience function to generate recipe from prompt"""
    request = RecipeGenerationRequest(prompt=prompt)
    return await llm_service.generate_recipe_with_fallback(request, user)

async def check_llm_service_status() -> Dict[str, Any]:
    """Check LLM service status for health checks"""
    try:
        is_connected = await llm_service.check_llm_connection()
        available_models = llm_service.get_available_models() if is_connected else []
        
        return {
            "status": "connected" if is_connected else "disconnected",
            "default_model": openai_service.default_model,
            "available_models": available_models[:5],  # Limit to first 5 models
            "service": "openai"
        }
    except Exception as e:
        logger.error(f"LLM service status check failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "service": "openai"
        }