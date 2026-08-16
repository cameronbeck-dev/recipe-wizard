// API Response Types for LLM-generated recipe data

export interface APIIngredient {
  id?: string; // Will be generated on frontend if not provided
  name: string;
  amount: string;
  unit?: string;
  category: 'produce' | 'butchery' | 'dry-goods' | 'chilled' | 'frozen' | 'pantry';
}

export interface APIRecipe {
  title: string;
  description?: string;
  instructions: string[];
  prepTime?: number; // in minutes
  cookTime?: number; // in minutes
  servings?: number;
  difficulty?: 'easy' | 'medium' | 'hard';
  tips?: string[];
}

export interface RecipeGenerationRequest {
  prompt: string;
  userId?: string; // For authenticated users
  // Optional per-request overrides that do not persist
  overrides?: {
    defaultServings?: number;
    preferredDifficulty?: 'easy' | 'medium' | 'hard';
  };
}

export interface RecipeModificationRequest {
  recipeId: string;
  modificationPrompt: string;
  userId?: string; // For authenticated users
}

export interface RecipeIdeaGenerationRequest {
  prompt: string;
  count?: number; // Number of ideas to generate (default: 5)
}

export interface RecipeIdea {
  id: string;
  title: string;
  description: string;
}

export interface RecipeIdeasResponse {
  ideas: RecipeIdea[];
  generatedAt: string; // ISO timestamp
  userPrompt: string; // Original user prompt
}

export interface RecipeGenerationResponse {
  id: string; // Generated recipe ID
  recipe: APIRecipe;
  ingredients: APIIngredient[];
  generatedAt: string; // ISO timestamp
  userPrompt: string; // Original user prompt
  retryCount?: number; // Number of retries needed
  retryMessage?: string; // Message shown during retries
}

// Async Job Processing Types
export interface RecipeJobCreateResponse {
  job_id: string;
  status: string;
  message: string;
  estimated_completion: string;
  status_url: string;
  polling_interval: number; // seconds between polls
  // Present only for guest (unauthenticated) generation requests
  guest_generations_remaining?: number;
  guest_quota_reset_at?: string; // ISO timestamp
}

export interface RecipeJobStatus {
  id: string;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'cancelled';
  job_type: 'generate' | 'modify';
  prompt: string;
  progress: number; // 0-100
  recipe_id?: string;
  error_message?: string;
  retry_count?: number; // Number of retries attempted
  created_at: string;
  started_at?: string;
  completed_at?: string;
  estimated_completion?: string;
}

export interface RecipeJobResult {
  job_id: string;
  status: string;
  recipe_id: string | null; // null for guest jobs (results stored server-side without a Recipe row)
  recipe: APIRecipe;
  ingredients: APIIngredient[];
  generated_at: string;
  user_prompt: string;
  generation_metadata?: Record<string, any>;
}

export interface RecipeJobError {
  job_id: string;
  status: 'failed';
  error_message: string;
  error_type: string;
  retry_available: boolean;
}

// For saving/loading recipes
export interface SavedRecipeData extends RecipeGenerationResponse {
  savedAt: string;
  isFavorite?: boolean;
}

// For conversation history
export interface ConversationEntry {
  id: string;
  userPrompt: string;
  response: RecipeGenerationResponse;
  createdAt: string;
}

export interface PaginatedConversationResponse {
  success: boolean;
  recipes: SavedRecipeData[];
  pagination: {
    total: number;
    offset: number;
    limit: number;
    hasMore: boolean;
  };
}

// User preferences for LLM customization
export interface UserPreferences {
  id?: string;
  userId?: string;
  
  // Unit preferences
  units: 'metric' | 'imperial';
  
  // Grocery list categories (user can add/remove)
  groceryCategories: string[];
  
  // Recipe preferences
  defaultServings: number;
  preferredDifficulty?: 'easy' | 'medium' | 'hard';
  maxCookTime?: number; // in minutes
  maxPrepTime?: number; // in minutes
  
  // Dietary restrictions/preferences
  dietaryRestrictions: string[]; // ['vegetarian', 'gluten-free', 'dairy-free', etc.]
  allergens: string[]; // ['nuts', 'shellfish', 'eggs', etc.]
  dislikes: string[]; // ingredients user doesn't like
  
  // Free-text preferences
  additionalPreferences: string;
  
  // UI preferences
  themePreference: 'light' | 'dark' | 'system';
  
  updatedAt: string;
  createdAt: string;
}

// Default grocery categories
export const DEFAULT_GROCERY_CATEGORIES = [
  'produce',
  'butchery', 
  'dry-goods',
  'chilled',
  'frozen',
  'pantry',
  'bakery',
  'deli',
  'beverages',
  'spices'
] as const;

// Shopping List Types
export interface ShoppingListItem {
  id: string;
  ingredientName: string;
  category: string;
  consolidatedDisplay: string; // effective display: override if set, else auto-computed
  autoConsolidatedDisplay: string; // raw auto-computed display
  source: 'recipe' | 'manual';
  userQuantityOverride: string | null;
  overrideIsStale: boolean;
  recipeBreakdown: {
    recipeId: string;
    recipeTitle: string;
    quantity: string;
  }[];
  isChecked: boolean;
}

export interface ShoppingListResponse {
  items: ShoppingListItem[];
  lastUpdated: string;
}

export interface AddRecipeToShoppingListRequest {
  recipeId: string;
  userId?: string;
  allowDuplicate?: boolean;
}

export interface UpdateShoppingListItemRequest {
  itemId: string;
  isChecked: boolean;
}

export interface ShoppingListRecipeSummary {
  recipeId: string;
  recipeTitle: string;
  addedAt: string | null;
}

export interface ClearCheckedItemsResponse {
  success: boolean;
  removedCount: number;
  items: ShoppingListItem[];
}

export interface ShoppingListItemUpdateResponse {
  success: boolean;
  item: ShoppingListItem;
}

export interface AddManualItemRequest {
  ingredientName: string;
  quantity?: string;
  category?: string;
}

// Default user preferences
export const DEFAULT_USER_PREFERENCES: Omit<UserPreferences, 'id' | 'userId' | 'updatedAt' | 'createdAt'> = {
  units: 'metric',
  groceryCategories: [...DEFAULT_GROCERY_CATEGORIES],
  defaultServings: 4,
  dietaryRestrictions: [],
  allergens: [],
  dislikes: [],
  additionalPreferences: '',
  themePreference: 'system',
};
