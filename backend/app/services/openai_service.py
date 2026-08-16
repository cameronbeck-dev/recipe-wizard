import os
import json
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
import time

from dotenv import load_dotenv
from openai import OpenAI
from openai.types.chat import ChatCompletion

from ..models import User
from ..schemas import RecipeGenerationRequest

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)


class RecipeRequestRefused(ValueError):
    """Raised when OpenAI declines a request (safety refusal or explicit
    refused:true in the structured response). Must never be silently
    swallowed by the generic retry-on-Exception path."""
    pass


class OpenAIService:
    """Service for interacting with OpenAI API for recipe generation"""

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_free = os.getenv("DEFAULT_MODEL_FREE", "gpt-5.6-luna")
        self.model_paid = os.getenv("DEFAULT_MODEL_PAID", "gpt-5.6-terra")
        self.default_model = os.getenv("DEFAULT_MODEL") or self.model_free

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self.client = OpenAI(api_key=self.api_key)

    def _is_premium_user(self, user: Optional["User"]) -> bool:
        return bool(user is not None and user.is_premium)

    def _select_model(self, user: Optional["User"]) -> str:
        try:
            return self.model_paid if self._is_premium_user(user) else self.model_free
        except Exception:
            return self.default_model

    def _check_moderation(self, text: str) -> None:
        """Pre-filter user-supplied text via OpenAI's moderation endpoint.

        Fails OPEN: any error talking to the moderation service is logged
        and generation proceeds normally. Only an explicit `flagged=True`
        result blocks the request.
        """
        try:
            result = self.client.moderations.create(model="omni-moderation-latest", input=text)
        except Exception as e:
            logger.warning(f"Moderation check failed, proceeding with generation: {e}")
            return

        try:
            flagged = result.results[0].flagged
        except Exception as e:
            logger.warning(f"Moderation check failed, proceeding with generation: {e}")
            return

        if flagged:
            raise RecipeRequestRefused(
                "This request could not be processed. Please try a different recipe request."
            )

    def _recipe_json_schema(self, categories: List[str]) -> dict:
        """Strict OpenAI structured-output schema for recipe/modification responses."""
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["refused", "refusal_reason", "recipe", "ingredients"],
            "properties": {
                "refused": {"type": "boolean"},
                "refusal_reason": {"type": ["string", "null"]},
                "recipe": {
                    "type": ["object", "null"],
                    "additionalProperties": False,
                    "required": [
                        "title", "description", "instructions", "prepTime",
                        "cookTime", "servings", "difficulty", "tips",
                    ],
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": ["string", "null"]},
                        "instructions": {"type": "array", "items": {"type": "string"}},
                        "prepTime": {"type": ["integer", "null"]},
                        "cookTime": {"type": ["integer", "null"]},
                        "servings": {"type": "integer"},
                        "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                        "tips": {"type": ["array", "null"], "items": {"type": "string"}},
                    },
                },
                "ingredients": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "amount", "unit", "category"],
                        "properties": {
                            "name": {"type": "string"},
                            "amount": {"type": "string"},
                            "unit": {"type": ["string", "null"]},
                            "category": {"type": "string", "enum": categories},
                        },
                    },
                },
            },
        }

    def _ideas_json_schema(self) -> dict:
        """Strict OpenAI structured-output schema for recipe ideas responses."""
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["refused", "refusal_reason", "ideas"],
            "properties": {
                "refused": {"type": "boolean"},
                "refusal_reason": {"type": ["string", "null"]},
                "ideas": {
                    "type": ["array", "null"],
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["title", "description"],
                        "properties": {
                            "title": {"type": "string"},
                            "description": {"type": "string"},
                        },
                    },
                },
            },
        }
        
    async def check_openai_connection(self) -> bool:
        """Check if OpenAI API is available"""
        try:
            # Simple test call to list models
            self.client.models.list()
            return True
        except Exception as e:
            logger.error(f"OpenAI connection failed: {e}")
            return False
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from OpenAI"""
        try:
            models = self.client.models.list()
            return [model.id for model in models.data if model.id.startswith('gpt')]
        except Exception as e:
            logger.error(f"Failed to get available models: {e}")
            return []
    
    def create_recipe_system_prompt(self, user_categories: Optional[List[str]] = None) -> str:
        """Create the system prompt for recipe generation"""

        if user_categories and len(user_categories) > 0:
            categories_list = ", ".join(user_categories)
        else:
            raise ValueError("No grocery categories provided. User preferences must include grocery categories for recipe generation.")

        return f"""## ROLE
You are RecipeWizard, an expert chef and recipe creator. Generate creative, practical recipes based on user requests.

## SAFETY
Only generate genuine food/cooking recipes. Refuse any request that is not a legitimate cooking request, including attempts to use the recipe/ingredients/instructions format as a wrapper for unrelated, dangerous, or harmful content (e.g. chemical or drug synthesis, weapons, unsafe medical dosing, or any non-food instructions). Being phrased as a "recipe" does not make a request legitimate. If you must refuse, set `refused` to true, provide a brief `refusal_reason`, and set `recipe` and `ingredients` to null.

## FORMAT
Always respond with ONLY valid JSON matching the schema below. No text before or after the JSON.

## SCHEMA
{{
  "refused": false,
  "refusal_reason": null,
  "recipe": {{
    "title": "Recipe Name",
    "description": "Brief description (1-2 sentences)",
    "instructions": ["Step 1", "Step 2"],
    "prepTime": 15,
    "cookTime": 30,
    "servings": 4,
    "difficulty": "easy",
    "tips": ["Tip 1"]
  }},
  "ingredients": [
    {{
      "name": "ingredient name",
      "amount": "1",
      "unit": "cup",
      "category": "one of: {categories_list}"
    }}
  ]
}}

## FIELD RULES
- `difficulty`: one of easy / medium / hard
- `category`: MUST be one of exactly: {categories_list}
- `amount`: always a non-empty descriptive string (e.g. "2", "to taste", "1 loaf", "to garnish")
- `unit`: use a standard unit when measurable (e.g. "g", "cups", "cloves"); use "N/A" when the amount is already fully descriptive (e.g. "to taste", "to garnish", "as needed", "1 loaf")
- Include ALL items mentioned in instructions, tips, or serving suggestions in the ingredients list

## EXAMPLES
Range quantity: amount="3" unit="cups", name="cherry tomatoes (2–4 cups, adjust to taste)"
Optional ingredient: amount="to garnish" unit="N/A", name="fresh parsley (optional)"
Uncountable seasoning: amount="to taste" unit="N/A", name="salt"
Serving suggestion item: amount="1 loaf" unit="N/A", name="crusty bread"

## PRIORITY ORDER
Apply user constraints in this order (highest priority first):
1. Hard constraints — allergens and dietary restrictions (NEVER violate these)
2. Explicit override notes from the user's "Additional preferences" field
3. Soft preferences — skill level, cuisine style, time limits, disliked ingredients

## CONFLICT RESOLUTION
- If a requested dish inherently contains an allergen or violates a dietary restriction, generate the closest compliant alternative and note the substitution in the description.
- If soft preferences conflict with each other, use good culinary judgement."""

    def create_recipe_messages(
        self, 
        user_prompt: str, 
        user_preferences: Optional[str] = None, 
        user_categories: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Create OpenAI messages for recipe generation"""
        
        system_prompt = self.create_recipe_system_prompt(user_categories)
        
        user_message = f"## USER REQUEST\n{user_prompt}"

        if user_preferences:
            user_message += user_preferences

        user_message += "\n\nRespond with ONLY valid JSON:"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    
    def _get_retry_message(self, attempt: int, error_type: str) -> str:
        """Get thematic retry message for user feedback"""
        messages = {
            'format': [
                'Refining the recipe structure...',
                'Correcting the ingredient format...',
                'Finalising recipe details...'
            ],
            'categories': [
                'Organising the grocery list...',
                'Sorting ingredients by aisle...',
                'Categorising items for shopping...'
            ],
            'compliance': [
                'Adjusting recipe for your dietary needs...',
                'Substituting ingredients to meet your requirements...',
                'Ensuring the recipe meets your preferences...'
            ],
            'validation': [
                'Adding final touches...',
                'Checking recipe details...',
                'Ensuring everything is complete...'
            ]
        }

        message_list = messages.get(error_type, messages['validation'])
        return message_list[min(attempt - 1, len(message_list) - 1)]
    
    def _simple_json_fix(self, response_text: str) -> str:
        """Simple JSON cleanup - remove common issues"""
        # Remove markdown code blocks
        if response_text.strip().startswith('```'):
            lines = response_text.strip().split('\n')
            # Remove first and last line if they contain ```
            if lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            response_text = '\n'.join(lines)
        
        # Find JSON object bounds
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start != -1 and json_end > json_start:
            return response_text[json_start:json_end]
        
        return response_text
    
    def _validate_recipe_data(self, data: Dict) -> tuple[bool, str]:
        """Basic validation - return (is_valid, error_type)"""
        try:
            if 'recipe' not in data or 'ingredients' not in data:
                return False, 'format'

            recipe = data['recipe']
            ingredients = data['ingredients']

            if not isinstance(recipe, dict):
                return False, 'format'
            if not recipe.get('title') or not isinstance(recipe['title'], str):
                return False, 'format'
            if 'instructions' not in recipe:
                return False, 'format'
            instructions = recipe['instructions']
            if not isinstance(instructions, (list, str)):
                return False, 'format'
            if isinstance(instructions, list) and len(instructions) == 0:
                return False, 'format'
            if isinstance(instructions, str) and not instructions.strip():
                return False, 'format'

            if not isinstance(ingredients, list) or len(ingredients) == 0:
                return False, 'format'

            for ing in ingredients:
                if not isinstance(ing, dict) or 'name' not in ing or 'amount' not in ing or 'category' not in ing:
                    return False, 'format'

            return True, ''

        except Exception:
            return False, 'format'

    def _ingredients_cover_common_references(self, recipe: Dict[str, Any], ingredients: List[Dict[str, Any]]) -> bool:
        """Best-effort check to ensure common instruction references are represented in ingredients.

        Looks for phrases like "serve with X", "garnish with X", "top with X" and checks that X is present
        in the ingredient names. This is a heuristic to reduce inconsistencies like suggesting bread without
        listing it in the grocery list.
        """
        try:
            import re

            # Aggregate text fields to scan
            texts: List[str] = []
            if isinstance(recipe.get('description'), str):
                texts.append(recipe['description'])
            if isinstance(recipe.get('tips'), list):
                texts.extend([t for t in recipe['tips'] if isinstance(t, str)])
            # instructions guaranteed to be list of str by this point
            texts.extend([t for t in recipe.get('instructions', []) if isinstance(t, str)])

            full_text = "\n".join(texts).lower()
            ing_names = [str(ing.get('name', '')).lower() for ing in ingredients]

            # Patterns to catch common serving/garnish references
            patterns = [
                r"serve(?:\s+with)?\s+([^\.;\n]+)",
                r"serve\s+over\s+([^\.;\n]+)",
                r"garnish(?:\s+with)?\s+([^\.;\n]+)",
                r"top\s+with\s+([^\.;\n]+)",
                r"alongside\s+([^\.;\n]+)",
            ]

            referenced_items: List[str] = []
            for pat in patterns:
                for m in re.finditer(pat, full_text):
                    phrase = m.group(1).strip()
                    # Split on common separators to get individual items
                    parts = re.split(r",| and | or |/|\\+", phrase)
                    referenced_items.extend([p.strip() for p in parts if p.strip()])

            # If nothing found, pass
            if not referenced_items:
                return True

            # If any referenced item has no fuzzy match in ingredient names, flag validation failure
            def has_match(ref: str) -> bool:
                tokens = [t for t in re.split(r"\s+", ref) if t]
                # Try simple containment against ingredient names
                for name in ing_names:
                    # require any non-trivial token to appear
                    if any(tok in name for tok in tokens if len(tok) > 2):
                        return True
                return False

            for ref in referenced_items:
                if not has_match(ref):
                    return False

            return True
        except Exception:
            # On any parsing error, don't block generation
            return True

    def _find_missing_references(self, recipe: Dict[str, Any], ingredients: List[Dict[str, Any]]) -> List[str]:
        """Return a list of referenced items (serve/garnish/top with) that are not covered by ingredients."""
        try:
            import re
            texts: List[str] = []
            if isinstance(recipe.get('description'), str):
                texts.append(recipe['description'])
            if isinstance(recipe.get('tips'), list):
                texts.extend([t for t in recipe['tips'] if isinstance(t, str)])
            texts.extend([t for t in recipe.get('instructions', []) if isinstance(t, str)])

            full_text = "\n".join(texts).lower()
            ing_names = [str(ing.get('name', '')).lower() for ing in ingredients]

            patterns = [
                r"serve(?:\s+with)?\s+([^\.;\n]+)",
                r"serve\s+over\s+([^\.;\n]+)",
                r"garnish(?:\s+with)?\s+([^\.;\n]+)",
                r"top\s+with\s+([^\.;\n]+)",
                r"alongside\s+([^\.;\n]+)",
            ]
            referenced_items: List[str] = []
            for pat in patterns:
                for m in re.finditer(pat, full_text):
                    phrase = m.group(1).strip()
                    parts = re.split(r",| and | or |/|\\+", phrase)
                    referenced_items.extend([p.strip() for p in parts if p.strip()])

            def has_match(ref: str) -> bool:
                tokens = [t for t in re.split(r"\s+", ref) if t]
                for name in ing_names:
                    if any(tok in name for tok in tokens if len(tok) > 2):
                        return True
                return False

            missing = []
            for ref in referenced_items:
                if not has_match(ref):
                    missing.append(ref)
            return missing
        except Exception:
            return []

    def _check_preference_compliance(
        self,
        recipe_data: Dict,
        preferences: Optional[Dict],
    ) -> Optional[str]:
        """Scan generated recipe for hard-constraint violations.

        Returns a targeted error string to append to the retry message if a
        violation is found, or None when the recipe looks compliant.
        Only checks allergens and dietary restrictions (hard constraints).
        False positives are acceptable; false negatives are not.
        """
        if not preferences:
            return None

        split = self._split_preferences(preferences)
        allergens = [a.lower() for a in split["hard_allergens"]]
        dietary = [d.lower() for d in split["hard_dietary"]]

        DIETARY_FORBIDDEN: Dict[str, List[str]] = {
            "vegan": ["meat", "chicken", "beef", "pork", "lamb", "fish", "seafood",
                      "shrimp", "prawn", "tuna", "salmon", "bacon", "ham", "turkey",
                      "milk", "cream", "butter", "cheese", "yogurt", "egg", "eggs",
                      "honey", "gelatin", "lard", "ghee", "whey", "casein"],
            "vegetarian": ["meat", "chicken", "beef", "pork", "lamb", "fish", "seafood",
                           "shrimp", "prawn", "tuna", "salmon", "bacon", "ham", "turkey",
                           "lard", "gelatin"],
            "gluten-free": ["wheat", "flour", "bread", "pasta", "noodle", "barley",
                            "rye", "semolina", "couscous", "bulgur", "spelt", "farro",
                            "breadcrumb", "soy sauce", "teriyaki"],
            "dairy-free": ["cow's milk", "whole milk", "skim milk", "heavy cream",
                           "sour cream", "butter", "cheese", "yogurt", "whey",
                           "casein", "ghee", "lactose", "half and half", "buttermilk"],
            "nut-free": ["almond", "cashew", "walnut", "pecan", "pistachio", "hazelnut",
                         "macadamia", "peanut", "pine nut", "nut"],
            "halal": ["pork", "bacon", "ham", "lard", "gelatin", "alcohol", "wine",
                      "beer", "spirits"],
            "kosher": ["pork", "bacon", "ham", "lard", "shellfish", "shrimp", "lobster",
                       "crab", "clam", "oyster"],
        }

        try:
            ingredients = recipe_data.get("ingredients", [])
            ing_names_lower = [str(ing.get("name", "")).lower() for ing in ingredients]

            violations: List[str] = []

            for diet in dietary:
                forbidden = DIETARY_FORBIDDEN.get(diet, [])
                for kw in forbidden:
                    for name in ing_names_lower:
                        if kw in name:
                            violations.append(f"{name!r} violates {diet} restriction")
                            break

            for allergen in allergens:
                for name in ing_names_lower:
                    if allergen in name:
                        violations.append(f"{name!r} contains allergen {allergen!r}")
                        break

            if violations:
                return ("The recipe violates hard constraints: " +
                        "; ".join(violations) +
                        ". Remove or substitute these ingredients so the recipe complies.")
            return None

        except Exception:
            return None

    async def generate_recipe(
        self,
        request: RecipeGenerationRequest,
        user: Optional[User] = None
    ) -> Dict[str, Any]:
        """Generate a recipe using OpenAI API with 3-attempt fallback"""
        start_time = time.time()
        max_retries = 3
        final_attempt = None  # Store final attempt to return if all fail

        try:
            # Get user preferences - prioritize request preferences over database
            user_preferences = None
            user_categories = None

            if request.preferences:
                logger.info("Using preferences from API request (mobile app)")
                user_categories = request.preferences.get('groceryCategories', [])
                user_preferences = self._generate_preference_context_from_request(request.preferences)
                logger.info(f"Request categories: {user_categories}")

            elif user:
                logger.info(f"Using database preferences for user {user.email}")
                user_preferences = user.get_preference_context()
                user_categories = user.grocery_categories
                logger.info(f"Database categories: {user_categories}")

            else:
                logger.info("No user or preferences provided")

            # Create the messages
            messages = self.create_recipe_messages(
                request.prompt,
                user_preferences,
                user_categories
            )

            # Moderation pre-filter — once, outside the retry loop, fails open
            self._check_moderation(request.prompt)

            model = self._select_model(user)
            schema = self._recipe_json_schema(user_categories)

            logger.info(f"Generating recipe for prompt: {request.prompt[:100]}...")

            for attempt in range(1, max_retries + 1):
                try:
                    # Call OpenAI API
                    response: ChatCompletion = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=2000,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "recipe_response", "strict": True, "schema": schema},
                        },
                    )

                    generation_time = int((time.time() - start_time) * 1000)

                    message = response.choices[0].message
                    if getattr(message, "refusal", None):
                        user_id = user.id if user else "anonymous"
                        logger.warning(f"OpenAI refused recipe generation for user {user_id}: {message.refusal}")
                        raise RecipeRequestRefused(
                            "This request could not be fulfilled because it doesn't look like a legitimate recipe request."
                        )

                    # Extract and clean the generated text
                    generated_text = message.content.strip()
                    cleaned_text = self._simple_json_fix(generated_text)

                    logger.info(f"OpenAI generated {len(generated_text)} characters in {generation_time}ms (attempt {attempt})")

                    # Parse and validate JSON
                    recipe_data = json.loads(cleaned_text)

                    if recipe_data.get('refused', False):
                        user_id = user.id if user else "anonymous"
                        reason = recipe_data.get('refusal_reason') or "This request could not be fulfilled because it doesn't look like a legitimate recipe request."
                        logger.warning(f"Model declined recipe generation for user {user_id}: {reason}")
                        raise RecipeRequestRefused(reason)

                    is_valid, error_type = self._validate_recipe_data(recipe_data)

                    if is_valid:
                        # Check hard-constraint compliance before accepting
                        compliance_error = self._check_preference_compliance(
                            recipe_data, request.preferences
                        )
                        if compliance_error and attempt < max_retries:
                            logger.warning(
                                f"Attempt {attempt} passed structure but failed compliance, retrying: {compliance_error}"
                            )
                            error_type = 'compliance'
                            messages.append({"role": "assistant", "content": cleaned_text})
                            messages.append({"role": "user", "content": compliance_error})

                    # Store this attempt for fallback (reflects updated error_type if compliance failed)
                    final_attempt = {
                        'recipe_data': recipe_data,
                        'generation_time_ms': generation_time,
                        'model': model,
                        'raw_response': generated_text,
                        'token_count': response.usage.completion_tokens if response.usage else 0,
                        'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                        'retry_count': attempt - 1,
                        'retry_message': self._get_retry_message(attempt, error_type) if attempt > 1 else None
                    }

                    if is_valid and error_type != 'compliance':
                        # Add default values for optional fields
                        recipe = recipe_data['recipe']
                        recipe['description'] = recipe.get('description') or ''
                        recipe['prepTime'] = recipe.get('prepTime')
                        recipe['cookTime'] = recipe.get('cookTime')
                        recipe.setdefault('servings', 4)
                        recipe.setdefault('difficulty', 'medium')
                        recipe['tips'] = recipe.get('tips') or []

                        # Ensure instructions is a list
                        if isinstance(recipe['instructions'], str):
                            recipe['instructions'] = [recipe['instructions']]

                        # Add default unit for ingredients
                        for ing in recipe_data['ingredients']:
                            ing['unit'] = ing.get('unit') or ''

                        return final_attempt
                    elif error_type == 'compliance' and attempt < max_retries:
                        # Compliance retry message already appended above
                        continue
                    elif error_type == 'compliance' and attempt == max_retries:
                        # Final compliance failure — return recipe with defaults applied
                        logger.warning(f"Returning final attempt ({attempt}) despite compliance issues")
                        recipe = recipe_data.get('recipe', {})
                        recipe.setdefault('title', 'Generated Recipe')
                        recipe['description'] = recipe.get('description') or ''
                        recipe.setdefault('instructions', ['Follow recipe steps'])
                        recipe['prepTime'] = recipe.get('prepTime')
                        recipe['cookTime'] = recipe.get('cookTime')
                        recipe.setdefault('servings', 4)
                        recipe.setdefault('difficulty', 'medium')
                        recipe['tips'] = recipe.get('tips') or []

                        # Ensure instructions is a list
                        if isinstance(recipe['instructions'], str):
                            recipe['instructions'] = [recipe['instructions']]

                        # Add default unit for ingredients
                        ingredients = recipe_data.get('ingredients', [])
                        for ing in ingredients:
                            ing['unit'] = ing.get('unit') or ''
                            ing.setdefault('name', 'Ingredient')
                            ing.setdefault('amount', '1')
                            ing.setdefault('category', 'pantry')

                        return final_attempt
                    elif error_type != 'compliance':
                        # Invalid format — retry with guidance
                        if attempt < max_retries:
                            logger.warning(f"Attempt {attempt} failed validation ({error_type}), retrying...")
                            detailed_retry = f"Previous response had {error_type} issues. Please fix and provide only valid JSON."
                            if error_type == 'validation':
                                detailed_retry += " Ensure the recipe format is correct and all required fields are present."
                            messages.append({"role": "assistant", "content": cleaned_text})
                            messages.append({"role": "user", "content": detailed_retry})
                            continue
                        else:
                            # On final attempt, return it even if not perfect
                            logger.warning(f"Returning final attempt ({attempt}) despite validation issues: {error_type}")
                            # Add defaults even for imperfect recipes to make them client-readable
                            recipe = recipe_data.get('recipe', {})
                            recipe.setdefault('title', 'Generated Recipe')
                            recipe['description'] = recipe.get('description') or ''
                            recipe.setdefault('instructions', ['Follow recipe steps'])
                            recipe['prepTime'] = recipe.get('prepTime')
                            recipe['cookTime'] = recipe.get('cookTime')
                            recipe.setdefault('servings', 4)
                            recipe.setdefault('difficulty', 'medium')
                            recipe['tips'] = recipe.get('tips') or []

                            # Ensure instructions is a list
                            if isinstance(recipe['instructions'], str):
                                recipe['instructions'] = [recipe['instructions']]

                            # Add default unit for ingredients
                            ingredients = recipe_data.get('ingredients', [])
                            for ing in ingredients:
                                ing['unit'] = ing.get('unit') or ''
                                ing.setdefault('name', 'Ingredient')
                                ing.setdefault('amount', '1')
                                ing.setdefault('category', 'pantry')

                            return final_attempt

                except RecipeRequestRefused:
                    raise

                except json.JSONDecodeError as e:
                    if attempt < max_retries:
                        logger.warning(f"JSON parsing failed on attempt {attempt}, retrying...")
                        retry_message = "Previous response was not valid JSON. Please provide only valid JSON format."
                        messages.append({"role": "user", "content": retry_message})
                        continue
                    else:
                        raise ValueError(f"JSON parsing failed after {max_retries} attempts: {str(e)}")

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"Generation failed on attempt {attempt}: {e}")
                        continue
                    else:
                        raise

            # Fallback - should not reach here but return final attempt if available
            if final_attempt:
                logger.warning("Returning final attempt as fallback")
                return final_attempt
            raise ValueError("Recipe generation failed after all retries")

        except RecipeRequestRefused:
            raise
        except Exception as e:
            logger.error(f"Recipe generation failed: {e}")
            raise RuntimeError(f"Recipe generation failed: {str(e)}")
    
    def _split_preferences(self, preferences: Dict) -> Dict[str, Any]:
        """Categorise a preferences dict into hard constraints and soft preferences.

        Returns a dict with keys:
          hard_allergens        — list[str]
          hard_dietary          — list[str]
          soft_difficulty       — str | None
          soft_servings         — int | None
          soft_max_cook_time    — int | None
          soft_max_prep_time    — int | None
          soft_units            — str | None
          soft_dislikes         — list[str]
          override_notes        — str | None  (additionalPreferences)
        """
        return {
            "hard_allergens": preferences.get("allergens") or [],
            "hard_dietary": preferences.get("dietaryRestrictions") or [],
            "soft_difficulty": preferences.get("preferredDifficulty"),
            "soft_servings": preferences.get("defaultServings"),
            "soft_max_cook_time": preferences.get("maxCookTime"),
            "soft_max_prep_time": preferences.get("maxPrepTime"),
            "soft_units": preferences.get("units"),
            "soft_dislikes": preferences.get("dislikes") or [],
            "override_notes": (preferences.get("additionalPreferences") or "").strip() or None,
        }

    def _generate_preference_context_from_request(self, preferences: Dict) -> str:
        """Build a structured preference block for the LLM user message."""
        split = self._split_preferences(preferences)
        sections: List[str] = []

        # --- Hard constraints ---
        hard_lines: List[str] = []
        if split["hard_allergens"]:
            hard_lines.append(f"ALLERGENS TO AVOID: {', '.join(split['hard_allergens'])}")
        if split["hard_dietary"]:
            hard_lines.append(f"Dietary restrictions: {', '.join(split['hard_dietary'])}")
        if hard_lines:
            sections.append("### Hard constraints (MUST follow — never violate)\n" +
                            "\n".join(f"• {l}" for l in hard_lines))

        # --- Override notes ---
        if split["override_notes"]:
            sections.append(f"### Additional preferences (override soft settings if needed)\n"
                            f"• {split['override_notes']}")

        # --- Soft preferences ---
        soft_lines: List[str] = []
        if split["soft_units"]:
            unit_desc = "kg, g, ml, l, °C" if split["soft_units"] == "metric" else "lbs, oz, cups, tablespoons, °F"
            soft_lines.append(f"Units: {split['soft_units']} ({unit_desc})")
        if split["soft_servings"]:
            soft_lines.append(f"Servings: {split['soft_servings']} people")
        if split["soft_difficulty"]:
            soft_lines.append(f"Difficulty: {split['soft_difficulty']}")
        if split["soft_max_cook_time"]:
            soft_lines.append(f"Max cook time: {split['soft_max_cook_time']} minutes")
        if split["soft_max_prep_time"]:
            soft_lines.append(f"Max prep time: {split['soft_max_prep_time']} minutes")
        if split["soft_dislikes"]:
            soft_lines.append(f"Avoid ingredients: {', '.join(split['soft_dislikes'])}")
        if soft_lines:
            sections.append("### Soft preferences (follow where possible)\n" +
                            "\n".join(f"• {l}" for l in soft_lines))

        if not sections:
            return ""

        return "\n\n## USER PROFILE\n" + "\n\n".join(sections)
    
    def create_recipe_modification_system_prompt(self, user_categories: Optional[List[str]] = None) -> str:
        """Create the system prompt for recipe modification"""
        
        if user_categories and len(user_categories) > 0:
            categories_list = ", ".join(user_categories)
        else:
            raise ValueError("No grocery categories provided. User preferences must include grocery categories for recipe modification.")
        
        return f"""You are RecipeWizard, an expert chef and recipe modifier. You MUST modify the given original recipe based on the user's specific change request while keeping everything else exactly the same.

SAFETY: Only modify genuine food/cooking recipes into other genuine food/cooking recipes. Refuse any modification request that would turn the recipe into a wrapper for unrelated, dangerous, or harmful content (e.g. chemical or drug synthesis, weapons, unsafe medical dosing, or any non-food instructions). Being phrased as a "recipe" does not make a request legitimate. If you must refuse, set `refused` to true, provide a brief `refusal_reason`, and set `recipe` and `ingredients` to null.

CRITICAL MODIFICATION INSTRUCTIONS:
1. Always respond with ONLY valid JSON in the exact format specified below
2. Do not include any text before or after the JSON
3. PRESERVE EVERYTHING POSSIBLE: Only change what the user specifically requests
4. Keep the original recipe structure, cooking methods, and overall character
5. Maintain ingredient proportions and cooking times unless modification requires changes
6. If user requests a substitution, replace only that specific ingredient
7. If user requests dietary changes, modify only ingredients that conflict with the diet
8. If user requests flavor changes, adjust only seasonings/flavorings that affect that aspect
9. IMPORTANT: Follow all user preferences provided, prioritizing modification request over general preferences
10. INGREDIENT CATEGORIES: Every ingredient MUST use one of these exact categories: {categories_list}
11. COMPLETE SHOPPING LIST: Include ALL items needed to make this recipe in the ingredients list. If you mention "serve with crusty bread" or "garnish with parsley", include those items in the ingredients so the user can buy them. Use amounts like "1 loaf" for bread, "to garnish" for herbs, or "as needed" for optional items, and set unit to "N/A" for descriptive amounts.

MODIFICATION APPROACH:
- For ingredient substitutions: Replace only the specified ingredient(s)
- For dietary restrictions: Change only conflicting ingredients to compliant alternatives
- For spice/flavor adjustments: Modify only seasonings and flavor components
- For cooking method changes: Adjust only the specified cooking technique
- For texture changes: Modify only ingredients/techniques affecting texture
- For portion changes: Scale ingredients proportionally

REQUIRED JSON FORMAT:
{{
  "refused": false,
  "refusal_reason": null,
  "recipe": {{
    "title": "Modified Recipe Name (only change if modification affects the dish identity)",
    "description": "Brief description (preserve original unless modification changes it)",
    "instructions": ["Step 1", "Step 2", "..."],
    "prepTime": 15,
    "cookTime": 30,
    "servings": 4,
    "difficulty": "easy",
    "tips": ["Tip 1", "Tip 2"]
  }},
  "ingredients": [
    {{
      "name": "ingredient name",
      "amount": "1",
      "unit": "cup",
      "category": "MUST_BE_FROM_THIS_LIST: {categories_list}"
    }}
  ]
}}

INGREDIENT MEASUREMENT RULES:
- For measurable quantities, use specific amounts and units (e.g., "2", "cups")
- For taste-based ingredients (salt, pepper, spices), use descriptive amounts like "to taste", "pinch", "dash" and set unit to "N/A"
- For garnishes or optional additions, use amounts like "to garnish", "as needed" and set unit to "N/A"
- NEVER use "N/A" as the amount - always provide a descriptive amount

DIFFICULTY LEVELS: easy, medium, hard"""

    def create_recipe_modification_messages(
        self, 
        original_recipe,
        original_ingredients,
        modification_prompt: str,
        user_preferences: Optional[str] = None, 
        user_categories: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Create OpenAI messages for recipe modification"""
        
        system_prompt = self.create_recipe_modification_system_prompt(user_categories)
        
        # Format the original recipe data for the LLM
        original_recipe_json = {
            "recipe": {
                "title": original_recipe.title,
                "description": original_recipe.description or "",
                "instructions": original_recipe.instructions,
                "prepTime": original_recipe.prep_time,
                "cookTime": original_recipe.cook_time,
                "servings": original_recipe.servings,
                "difficulty": original_recipe.difficulty,
                "tips": original_recipe.tips or []
            },
            "ingredients": [
                {
                    "name": ing.name,
                    "amount": ing.amount,
                    "unit": ing.unit or "",
                    "category": ing.category
                }
                for ing in original_ingredients
            ]
        }
        
        # Build user message with original recipe and modification request
        user_message = f"""ORIGINAL RECIPE TO MODIFY:
{json.dumps(original_recipe_json, indent=2)}

MODIFICATION REQUEST: {modification_prompt}

INSTRUCTIONS:
- Keep everything from the original recipe exactly the same EXCEPT what the modification specifically requests
- Only change what is necessary to fulfill the modification request
- Preserve the cooking method, timing, and overall recipe structure unless the modification requires changes
- Maintain ingredient proportions unless modification specifically affects them"""
        
        if user_preferences:
            user_message += f"\n\nUser Preferences (secondary to modification request):{user_preferences}"
        
        user_message += "\n\nGenerate the modified recipe with ONLY valid JSON response:"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    
    async def modify_recipe(
        self, 
        original_recipe,
        original_ingredients,
        modification_prompt: str,
        user: Optional[User] = None,
        preferences: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Modify an existing recipe using OpenAI API with the original recipe as context"""
        start_time = time.time()
        max_retries = 3
        
        try:
            # Get user preferences - prioritize request preferences over database
            user_preferences = None
            user_categories = None
            
            if preferences:
                logger.info("Using preferences from modification request")
                user_categories = preferences.get('groceryCategories', [])
                user_preferences = self._generate_preference_context_from_request(preferences)
                logger.info(f"Modification request categories: {user_categories}")
                
            elif user:
                logger.info(f"Using database preferences for user {user.email}")
                user_preferences = user.get_preference_context()
                user_categories = user.grocery_categories
                logger.info(f"Database categories: {user_categories}")
                
            else:
                logger.info("No user or preferences provided for modification")
            
            # Create the messages with original recipe context
            messages = self.create_recipe_modification_messages(
                original_recipe,
                original_ingredients,
                modification_prompt,
                user_preferences,
                user_categories
            )

            # Moderation pre-filter — once, outside the retry loop, fails open
            self._check_moderation(modification_prompt)

            model = self._select_model(user)
            schema = self._recipe_json_schema(user_categories)

            logger.info(f"Modifying recipe '{original_recipe.title}' with request: {modification_prompt[:100]}...")

            for attempt in range(1, max_retries + 1):
                try:
                    # Call OpenAI API
                    response: ChatCompletion = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=2000,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "recipe_response", "strict": True, "schema": schema},
                        },
                    )

                    generation_time = int((time.time() - start_time) * 1000)

                    message = response.choices[0].message
                    if getattr(message, "refusal", None):
                        user_id = user.id if user else "anonymous"
                        logger.warning(f"OpenAI refused recipe modification for user {user_id}: {message.refusal}")
                        raise RecipeRequestRefused(
                            "This modification could not be fulfilled because it doesn't look like a legitimate recipe request."
                        )

                    # Extract and clean the generated text
                    generated_text = message.content.strip()
                    cleaned_text = self._simple_json_fix(generated_text)

                    logger.info(f"OpenAI modified recipe in {generation_time}ms (attempt {attempt})")

                    # Parse and validate JSON
                    recipe_data = json.loads(cleaned_text)

                    if recipe_data.get('refused', False):
                        user_id = user.id if user else "anonymous"
                        reason = recipe_data.get('refusal_reason') or "This modification could not be fulfilled because it doesn't look like a legitimate recipe request."
                        logger.warning(f"Model declined recipe modification for user {user_id}: {reason}")
                        raise RecipeRequestRefused(reason)

                    is_valid, error_type = self._validate_recipe_data(recipe_data)

                    if is_valid:
                        # Add default values for optional fields
                        recipe = recipe_data['recipe']
                        recipe['description'] = recipe.get('description') or ''
                        recipe['prepTime'] = recipe.get('prepTime')
                        recipe['cookTime'] = recipe.get('cookTime')
                        recipe.setdefault('servings', 4)
                        recipe.setdefault('difficulty', 'medium')
                        recipe['tips'] = recipe.get('tips') or []

                        # Ensure instructions is a list
                        if isinstance(recipe['instructions'], str):
                            recipe['instructions'] = [recipe['instructions']]

                        # Add default unit for ingredients
                        for ing in recipe_data['ingredients']:
                            ing['unit'] = ing.get('unit') or ''

                        return {
                            'recipe_data': recipe_data,
                            'generation_time_ms': generation_time,
                            'model': model,
                            'raw_response': generated_text,
                            'token_count': response.usage.completion_tokens if response.usage else 0,
                            'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                            'retry_count': attempt - 1,
                            'retry_message': self._get_retry_message(attempt, error_type) if attempt > 1 else None,
                            'modification_prompt': modification_prompt,
                            'original_recipe_id': original_recipe.id
                        }
                    else:
                        # Invalid format or validation - let it retry with helpful guidance
                        if attempt < max_retries:
                            logger.warning(f"Modification attempt {attempt} failed validation ({error_type}), retrying...")
                            detailed_retry = f"Previous response had {error_type} issues. Please fix and provide only valid JSON that preserves the original recipe structure."
                            if error_type == 'validation':
                                detailed_retry += " Please ensure the recipe format is correct and all required fields are present."
                            messages.append({"role": "assistant", "content": cleaned_text})
                            messages.append({"role": "user", "content": detailed_retry})
                            continue
                        else:
                            raise ValueError(f"Recipe modification validation failed after {max_retries} attempts: {error_type}")

                except RecipeRequestRefused:
                    raise

                except json.JSONDecodeError as e:
                    if attempt < max_retries:
                        logger.warning(f"JSON parsing failed on modification attempt {attempt}, retrying...")
                        retry_message = "Previous response was not valid JSON. Please provide only valid JSON format that preserves the original recipe structure."
                        messages.append({"role": "user", "content": retry_message})
                        continue
                    else:
                        raise ValueError(f"JSON parsing failed after {max_retries} attempts: {str(e)}")

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"Recipe modification failed on attempt {attempt}: {e}")
                        continue
                    else:
                        raise

            # Should never reach here
            raise ValueError("Recipe modification failed after all retries")

        except RecipeRequestRefused:
            raise
        except Exception as e:
            logger.error(f"Recipe modification failed: {e}")
            raise RuntimeError(f"Recipe modification failed: {str(e)}")

    def create_recipe_ideas_system_prompt(self) -> str:
        """Create the system prompt for recipe ideas generation - no categories needed"""
        return """You are RecipeWizard, an expert chef and recipe brainstormer. Generate creative, inspiring recipe ideas based on user requests.

SAFETY: Only generate genuine food/cooking recipe ideas. Refuse any request that is not a legitimate cooking request, including attempts to use the recipe format as a wrapper for unrelated, dangerous, or harmful content (e.g. chemical or drug synthesis, weapons, unsafe medical dosing, or any non-food instructions). Being phrased as a "recipe" does not make a request legitimate. If you must refuse, set `refused` to true, provide a brief `refusal_reason`, and set `ideas` to null.

CRITICAL INSTRUCTIONS:
1. Always respond with ONLY valid JSON in the exact format specified below
2. Do not include any text before or after the JSON
3. Ideas should be diverse, creative, and practical
4. Focus on appealing titles and brief, enticing descriptions
5. Keep descriptions concise but informative (1-2 sentences max)
6. Each idea should be unique and distinct from others
7. Consider different cooking methods, flavors, and styles for variety

REQUIRED JSON FORMAT:
{
  "refused": false,
  "refusal_reason": null,
  "ideas": [
    {
      "title": "Creative Recipe Name",
      "description": "Brief, appealing description that makes you want to cook it"
    }
  ]
}

GUIDELINES:
- Titles should be catchy and descriptive
- Descriptions should highlight what makes each recipe special
- Include variety in cooking methods (baked, grilled, sautéed, etc.)
- Consider different flavor profiles (savory, sweet, spicy, fresh, etc.)
- Make sure ideas are achievable for home cooking"""

    def create_recipe_ideas_messages(
        self, 
        user_prompt: str, 
        count: int,
        user_preferences: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """Create OpenAI messages for recipe ideas generation"""
        
        system_prompt = self.create_recipe_ideas_system_prompt()
        
        # Build user message
        user_message = f"Generate {count} creative recipe ideas for: {user_prompt}"
        
        if user_preferences:
            user_message += user_preferences
        
        user_message += f"\n\nGenerate exactly {count} unique, diverse recipe ideas with ONLY valid JSON response:"
        
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]

    def _validate_ideas_data(self, data: Dict, expected_count: int) -> tuple[bool, str]:
        """Basic validation for ideas response - return (is_valid, error_type)"""
        try:
            # Check required top-level keys
            if 'ideas' not in data:
                return False, 'format'
            
            ideas = data['ideas']
            
            # Check ideas format
            if not isinstance(ideas, list) or len(ideas) == 0:
                return False, 'format'
            
            # Check we got the right count (allow some flexibility)
            if len(ideas) < max(1, expected_count - 2) or len(ideas) > expected_count + 2:
                return False, 'count'
            
            for idea in ideas:
                if not isinstance(idea, dict) or 'title' not in idea or 'description' not in idea:
                    return False, 'format'
                
                # Check for reasonable length
                if not idea['title'] or not idea['description']:
                    return False, 'content'
                
                if len(idea['title']) > 100 or len(idea['description']) > 200:
                    return False, 'content'
            
            return True, ''
            
        except Exception:
            return False, 'format'

    async def generate_recipe_ideas(
        self,
        prompt: str,
        count: int = 5,
        user_preferences: Optional[str] = None,
        *,
        user: Optional["User"] = None
    ) -> Dict[str, Any]:
        """Generate recipe ideas using OpenAI API with 2-attempt fallback"""
        start_time = time.time()
        max_retries = 2  # 2 attempts for faster ideas generation

        try:
            # Create the messages
            messages = self.create_recipe_ideas_messages(prompt, count, user_preferences)

            # Moderation pre-filter — once, outside the retry loop, fails open
            self._check_moderation(prompt)

            model = self._select_model(user)
            schema = self._ideas_json_schema()

            logger.info(f"Generating {count} recipe ideas for prompt: {prompt[:100]}...")

            for attempt in range(1, max_retries + 1):
                try:
                    # Call OpenAI API
                    response: ChatCompletion = self.client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_completion_tokens=1000,
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "recipe_ideas_response", "strict": True, "schema": schema},
                        },
                    )

                    generation_time = int((time.time() - start_time) * 1000)

                    message = response.choices[0].message
                    if getattr(message, "refusal", None):
                        user_id = user.id if user else "anonymous"
                        logger.warning(f"OpenAI refused recipe ideas generation for user {user_id}: {message.refusal}")
                        raise RecipeRequestRefused(
                            "This request could not be fulfilled because it doesn't look like a legitimate recipe request."
                        )

                    # Extract and clean the generated text
                    generated_text = message.content.strip()
                    cleaned_text = self._simple_json_fix(generated_text)

                    logger.info(f"OpenAI generated {len(generated_text)} characters for ideas in {generation_time}ms (attempt {attempt})")

                    # Parse and validate JSON
                    ideas_data = json.loads(cleaned_text)

                    if ideas_data.get('refused', False):
                        user_id = user.id if user else "anonymous"
                        reason = ideas_data.get('refusal_reason') or "This request could not be fulfilled because it doesn't look like a legitimate recipe request."
                        logger.warning(f"Model declined recipe ideas generation for user {user_id}: {reason}")
                        raise RecipeRequestRefused(reason)

                    is_valid, error_type = self._validate_ideas_data(ideas_data, count)

                    if is_valid:
                        # Add IDs to ideas
                        import uuid
                        for i, idea in enumerate(ideas_data['ideas']):
                            idea['id'] = str(uuid.uuid4())

                        return {
                            'ideas': ideas_data['ideas'],
                            'generation_time_ms': generation_time,
                            'model': model,
                            'token_count': response.usage.completion_tokens if response.usage else 0,
                            'prompt_tokens': response.usage.prompt_tokens if response.usage else 0,
                            'retry_count': attempt - 1,
                            'generatedAt': datetime.utcnow().isoformat()
                        }
                    else:
                        # Invalid format or validation - let it retry
                        if attempt < max_retries:
                            logger.warning(f"Ideas attempt {attempt} failed validation ({error_type}), retrying...")
                            retry_message = f"Previous response had {error_type} issues. Please provide exactly {count} unique recipe ideas with valid JSON format."
                            messages.append({"role": "assistant", "content": cleaned_text})
                            messages.append({"role": "user", "content": retry_message})
                            continue
                        else:
                            raise ValueError(f"Recipe ideas validation failed after {max_retries} attempts: {error_type}")

                except RecipeRequestRefused:
                    raise

                except json.JSONDecodeError as e:
                    if attempt < max_retries:
                        logger.warning(f"JSON parsing failed on ideas attempt {attempt}, retrying...")
                        retry_message = f"Previous response was not valid JSON. Please provide exactly {count} recipe ideas in valid JSON format."
                        messages.append({"role": "user", "content": retry_message})
                        continue
                    else:
                        raise ValueError(f"JSON parsing failed after {max_retries} attempts: {str(e)}")

                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"Recipe ideas generation failed on attempt {attempt}: {e}")
                        continue
                    else:
                        raise

            # Should never reach here
            raise ValueError("Recipe ideas generation failed after all retries")

        except RecipeRequestRefused:
            raise
        except Exception as e:
            logger.error(f"Recipe ideas generation failed: {e}")
            raise RuntimeError(f"Recipe ideas generation failed: {str(e)}")

# Global OpenAI service instance
openai_service = OpenAIService()
