// API service for handling recipe generation and data persistence
import {
  RecipeGenerationRequest, RecipeGenerationResponse, RecipeModificationRequest,
  RecipeIdeaGenerationRequest, RecipeIdeasResponse,
  SavedRecipeData, ConversationEntry, RecipeJobCreateResponse, RecipeJobStatus,
  RecipeJobResult, RecipeJobError, PaginatedConversationResponse,
  ShoppingListResponse, AddRecipeToShoppingListRequest, UpdateShoppingListItemRequest,
  ShoppingListRecipeSummary, ClearCheckedItemsResponse, ShoppingListItemUpdateResponse,
  AddManualItemRequest
} from '../types/api';
import { PreferencesService } from './preferences';
import AuthService from './auth';
import { API_BASE_URL } from './config';
import { getDeviceId } from './deviceId';
import { GuestRecipe } from './guestRecipes';

export class ApiError extends Error {
  status: number;
  code?: string;
  data?: any;

  constructor(message: string, status: number, code?: string, data?: any) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.data = data;
  }
}

export type GuestErrorCode = 'GUEST_QUOTA_EXCEEDED' | 'GUEST_MODE_UNAVAILABLE' | 'INVALID_DEVICE_ID';

// Thrown by startRecipeGeneration when the backend rejects a guest request
// for a guest-specific reason (quota exhausted, rate limiter unavailable, or
// a malformed device id). Lets callers branch on `.code` instead of parsing
// the error message.
export class GuestGenerationError extends Error {
  code: GuestErrorCode;
  resetAt?: string;

  constructor(message: string, code: GuestErrorCode, resetAt?: string) {
    super(message);
    this.name = 'GuestGenerationError';
    this.code = code;
    this.resetAt = resetAt;
  }
}

function parseGuestError(status: number, errorData: any): GuestGenerationError | null {
  if (status === 429 && errorData?.code === 'GUEST_QUOTA_EXCEEDED') {
    return new GuestGenerationError(
      errorData.detail || "You've used all your free recipe generations for this week.",
      'GUEST_QUOTA_EXCEEDED',
      errorData.reset_at
    );
  }

  const detail = typeof errorData?.detail === 'string' ? errorData.detail : '';
  if (detail.startsWith('GUEST_MODE_UNAVAILABLE')) {
    return new GuestGenerationError(detail, 'GUEST_MODE_UNAVAILABLE');
  }
  if (detail.startsWith('INVALID_DEVICE_ID')) {
    return new GuestGenerationError(detail, 'INVALID_DEVICE_ID');
  }

  return null;
}

class APIService {
  public baseUrl: string;  // Made public so AuthService can access it

  constructor(baseUrl: string = API_BASE_URL) {
    this.baseUrl = baseUrl;
    // console.log('🔧 API Service initialized with URL:', this.baseUrl);
  }

  /**
   * Get authentication headers for API requests with automatic token refresh
   */
  private async getAuthHeaders(): Promise<Record<string, string>> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    try {
      const token = await AuthService.getStoredToken();
      
      if (token) {
        headers['Authorization'] = `Bearer ${token}`;
      }
    } catch (error) {
      console.warn('⚠️ Could not retrieve auth token:', error);
    }

    return headers;
  }

  /**
   * Make authenticated request with automatic token refresh on 401
   */
  private async makeAuthenticatedRequest(
    url: string,
    options: RequestInit = {}
  ): Promise<Response> {
    let headers = await this.getAuthHeaders();
    const hadToken = !!headers['Authorization'];

    try {
      headers['X-Device-Id'] = await getDeviceId();
    } catch (error) {
      console.warn('⚠️ Could not retrieve device id:', error);
    }

    // Merge with provided headers
    if (options.headers) {
      const provided = options.headers as any;
      headers = { ...headers, ...(provided || {}) } as Record<string, string>;
    }

    let response = await fetch(url, {
      ...options,
      headers,
    });

    // If 401, try to refresh token and retry once. Skip entirely for guests
    // (no stored token) — there's no refresh token to retry with.
    if (response.status === 401 && hadToken) {
      // console.log('🔄 Received 401, attempting token refresh...');

      const refreshResult = await AuthService.refreshToken();

      if (refreshResult) {
        // console.log('✅ Token refreshed, retrying request');

        // Update headers with new token
        headers['Authorization'] = `Bearer ${refreshResult.accessToken}`;

        // Retry the request with new token
        response = await fetch(url, {
          ...options,
          headers,
        });
      } else {
        // console.log('❌ Token refresh failed');
        throw new Error('Authentication expired. Please log in again.');
      }
    }

    return response;
  }

  /**
   * Generate a new recipe from user prompt
   */
  async generateRecipe(request: RecipeGenerationRequest): Promise<RecipeGenerationResponse> {
    try {
      // Load user preferences and send them to backend for LLM processing
      const preferences = await PreferencesService.loadPreferences();

      // Merge prompt-level overrides without persisting changes
      const { overrides, ...rest } = request as RecipeGenerationRequest & { overrides?: any };
      const mergedPreferences = {
        ...preferences,
        ...(overrides?.defaultServings !== undefined
          ? { defaultServings: overrides.defaultServings }
          : {}),
        ...(overrides?.preferredDifficulty !== undefined
          ? { preferredDifficulty: overrides.preferredDifficulty }
          : {}),
      };

      // Final payload sent to backend
      const enhancedRequest = {
        ...rest,
        preferences: mergedPreferences,
      };

      const url = `${this.baseUrl}/api/recipes/generate`;

      const response = await this.makeAuthenticatedRequest(url, {
        method: 'POST',
        body: JSON.stringify(enhancedRequest),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error generating recipe:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to generate recipe. Please try again.');
    }
  }

  /**
   * Modify an existing recipe based on user feedback
   */
  async modifyRecipe(recipeId: string, modificationPrompt: string): Promise<RecipeGenerationResponse> {
    try {
      // Load user preferences for context
      const preferences = await PreferencesService.loadPreferences();

      const request: RecipeModificationRequest = {
        recipeId,
        modificationPrompt,
      };

      // Enhanced request with preferences for better LLM context
      const enhancedRequest = {
        ...request,
        preferences,
      };

      const url = `${this.baseUrl}/api/recipes/modify`;

      const response = await this.makeAuthenticatedRequest(url, {
        method: 'POST',
        body: JSON.stringify(enhancedRequest),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(`HTTP ${response.status}: ${errorData.detail || errorData.error || response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error modifying recipe:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to modify recipe. Please try again.');
    }
  }

  /**
   * Get a specific recipe by ID
   */
  async getRecipe(recipeId: string): Promise<RecipeGenerationResponse> {
    try {
      // console.log('🔍 Fetching recipe by ID:', recipeId);

      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/${recipeId}`, {
        method: 'GET',
      });

      // console.log('📡 Get recipe response status:', response.status, response.statusText);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`HTTP ${response.status}: ${errorData.error || response.statusText}`);
      }

      const data = await response.json();
      // console.log('✅ Recipe fetched successfully:', data.id || 'no-id');
      return data;
    } catch (error) {
      console.error('Error fetching recipe:', error);
      throw new Error('Failed to load recipe. Please try again.');
    }
  }

  /**
   * Save a recipe to user's favorites
   */
  async saveRecipe(recipeData: RecipeGenerationResponse): Promise<SavedRecipeData> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/save/${recipeData.id}`, {
        method: 'POST',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const result = await response.json();

      // Return the recipe data with saved metadata
      return {
        ...recipeData,
        savedAt: new Date().toISOString(),
        isFavorite: true
      };
    } catch (error) {
      console.error('Error saving recipe:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to save recipe. Please try again.');
    }
  }

  /**
   * Remove a recipe from user's favorites
   */
  async unsaveRecipe(recipeId: string): Promise<void> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/saved/${recipeId}`, {
        method: 'DELETE',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
    } catch (error) {
      console.error('Error unsaving recipe:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to unsave recipe. Please try again.');
    }
  }

  /**
   * Check if a recipe is saved
   */
  async isRecipeSaved(recipeId: string): Promise<boolean> {
    try {
      const savedRecipes = await this.getSavedRecipes();
      return savedRecipes.some(recipe => recipe.id === recipeId);
    } catch (error) {
      console.error('Error checking if recipe is saved:', error);
      return false;
    }
  }

  /**
   * Get all saved recipes
   */
  async getSavedRecipes(): Promise<SavedRecipeData[]> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/saved`, {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data.recipes || [];
    } catch (error) {
      console.error('Error fetching saved recipes:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to load saved recipes. Please try again.');
    }
  }

  /**
   * Get user's conversation history
   */
  async getConversationHistory(limit: number = 20, offset: number = 0): Promise<ConversationEntry[]> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/history?limit=${limit}&offset=${offset}`, {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data.recipes || [];
    } catch (error) {
      console.error('Error fetching conversation history:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to load conversation history. Please try again.');
    }
  }

  /**
   * Get user's conversation history with pagination info
   */
  async getConversationHistoryWithPagination(limit: number = 20, offset: number = 0): Promise<PaginatedConversationResponse> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/history?limit=${limit}&offset=${offset}`, {
        method: 'GET',
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error fetching conversation history with pagination:', error);
      if (error instanceof Error) throw error;
      throw new Error('Failed to load conversation history. Please try again.');
    }
  }

  /**
   * Check API health/connectivity
   */
  async checkHealth(): Promise<boolean> {
    try {
      const response = await fetch(`${this.baseUrl}/health`, {
        method: 'GET',
        timeout: 5000, // 5 second timeout
      } as any);
      
      return response.ok;
    } catch (error) {
      console.warn('API health check failed:', error);
      return false;
    }
  }

  /**
   * Generate recipe ideas based on user prompt
   */
  async generateRecipeIdeas(request: RecipeIdeaGenerationRequest): Promise<RecipeIdeasResponse> {
    try {
      // Load user preferences and include them in request
      const preferences = await PreferencesService.loadPreferences();

      const enhancedRequest = {
        ...request,
        preferences,
        count: request.count || 5
      };

      const url = `${this.baseUrl}/api/recipes/generate-ideas`;
      // console.log('🚀 Making recipe ideas request to:', url);
      // console.log('📝 Request payload:', JSON.stringify(enhancedRequest, null, 2));
      
      const response = await this.makeAuthenticatedRequest(url, {
        method: 'POST',
        body: JSON.stringify(enhancedRequest),
      });
      
      // console.log('📡 Ideas response status:', response.status, response.statusText);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ error: 'Unknown error' }));
        throw new Error(`HTTP ${response.status}: ${errorData.error || response.statusText}`);
      }

      const data = await response.json();
      return data;
    } catch (error) {
      console.error('Error generating recipe ideas:', error);
      throw new Error('Failed to generate recipe ideas. Please try again.');
    }
  }

  // ========================================
  // Async Job Processing Methods
  // ========================================

  /**
   * Start async recipe generation job
   */
  async startRecipeGeneration(request: RecipeGenerationRequest): Promise<RecipeJobCreateResponse> {
    try {
      const preferences = await PreferencesService.loadPreferences();

      // Merge prompt-level overrides without persisting changes (same logic as generateRecipe)
      const { overrides, ...rest } = request as RecipeGenerationRequest & { overrides?: any };
      const mergedPreferences = {
        ...preferences,
        ...(overrides?.defaultServings !== undefined
          ? { defaultServings: overrides.defaultServings }
          : {}),
        ...(overrides?.preferredDifficulty !== undefined
          ? { preferredDifficulty: overrides.preferredDifficulty }
          : {}),
      };

      const requestWithPrefs = { ...rest, preferences: mergedPreferences };

      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/jobs/recipes/generate`, {
        method: 'POST',
        body: JSON.stringify(requestWithPrefs),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const guestError = parseGuestError(response.status, errorData);
        if (guestError) throw guestError;
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const jobResponse: RecipeJobCreateResponse = await response.json();
      // console.log('🚀 Started recipe generation job:', jobResponse.job_id);
      return jobResponse;
    } catch (error) {
      console.error('Error starting recipe generation job:', error);
      if (error instanceof GuestGenerationError) throw error;
      throw new Error('Failed to start recipe generation. Please try again.');
    }
  }

  /**
   * Get job status
   */
  async getJobStatus(jobId: string): Promise<RecipeJobStatus> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/jobs/recipes/${jobId}/status`, {
        method: 'GET',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error getting job status:', error);
      throw new Error('Failed to get job status. Please try again.');
    }
  }

  /**
   * Get completed job result
   */
  async getJobResult(jobId: string): Promise<RecipeJobResult> {
    try {
      const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/jobs/recipes/${jobId}/result`, {
        method: 'GET',
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      console.error('Error getting job result:', error);
      throw new Error('Failed to get job result. Please try again.');
    }
  }

  /**
   * Poll job until completion with automatic retries
   * Returns the final recipe when ready
   */
  async pollJobUntilComplete(
    jobId: string, 
    onProgress?: (status: RecipeJobStatus) => void,
    timeoutMs: number = 300000 // 5 minutes default
  ): Promise<RecipeGenerationResponse> {
    const startTime = Date.now();
    const pollInterval = 3000; // 3 seconds
    
    while (true) {
      try {
        // Check for timeout
        if (Date.now() - startTime > timeoutMs) {
          throw new Error('Job polling timeout - recipe generation is taking longer than expected');
        }

        // Get current status
        const status = await this.getJobStatus(jobId);
        
        // Call progress callback if provided
        if (onProgress) {
          onProgress(status);
        }

        // Handle completed job
        if (status.status === 'completed') {
          // console.log('✅ Job completed:', jobId);
          const result = await this.getJobResult(jobId);
          
          // Convert to RecipeGenerationResponse format. Guest jobs have no
          // recipe_id (no Recipe row is created server-side) — fall back to
          // the job id so callers always have a stable local identifier.
          return {
            id: result.recipe_id ?? jobId,
            recipe: result.recipe,
            ingredients: result.ingredients,
            generatedAt: result.generated_at,
            userPrompt: result.user_prompt,
            retryCount: result.generation_metadata?.retry_count,
            retryMessage: result.generation_metadata?.retry_message
          };
        }

        // Handle failed job
        if (status.status === 'failed') {
          console.error('❌ Job failed:', status.error_message);
          throw new Error(status.error_message || 'Recipe generation failed');
        }

        // Handle cancelled job
        if (status.status === 'cancelled') {
          throw new Error('Recipe generation was cancelled');
        }

        // Continue polling for pending/processing jobs
        // console.log(`⏳ Job ${status.status} (${status.progress}%)`);
        await new Promise(resolve => setTimeout(resolve, pollInterval));

      } catch (error) {
        console.error('Error during job polling:', error);
        throw error;
      }
    }
  }

  /**
   * Import locally-stored guest recipes into the signed-in account. Called
   * on both registration and login so guest history merges either way.
   * Requires an authenticated session — dedupes server-side by normalized title.
   */
  async importGuestRecipes(recipes: GuestRecipe[]): Promise<{ imported: number; skipped: number }> {
    const payload = {
      recipes: recipes.map(r => ({
        recipe: r.recipe,
        ingredients: r.ingredients,
        userPrompt: r.userPrompt,
      })),
    };

    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/recipes/import`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  // ========================================
  // Shopping List Methods
  // ========================================

  /**
   * Add a recipe to the user's shopping list
   */
  async addRecipeToShoppingList(recipeId: string, options?: { allowDuplicate?: boolean }): Promise<ShoppingListResponse> {
    const request: AddRecipeToShoppingListRequest = {
      recipeId,
      allowDuplicate: options?.allowDuplicate,
    };

    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/add-recipe`, {
      method: 'POST',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code,
        errorData
      );
    }

    return await response.json();
  }

  /**
   * List the recipes currently contributing to the user's shopping list
   */
  async getShoppingListRecipes(): Promise<ShoppingListRecipeSummary[]> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/recipes`, {
      method: 'GET',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Delete only the checked-off items from the shopping list
   */
  async clearCheckedItems(): Promise<ClearCheckedItemsResponse> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/checked`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Delete a single shopping list item
   */
  async deleteShoppingListItem(itemId: string): Promise<ShoppingListResponse> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/items/${itemId}`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Set or clear (pass null) a manual quantity override on an item
   */
  async setItemQuantity(itemId: string, quantity: string | null): Promise<ShoppingListItemUpdateResponse> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/items/${itemId}/quantity`, {
      method: 'PATCH',
      body: JSON.stringify({ quantity }),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Add a manual (non-recipe) item to the shopping list
   */
  async addManualItem(request: AddManualItemRequest): Promise<ShoppingListItemUpdateResponse> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/items`, {
      method: 'POST',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Get the user's shopping list
   */
  async getShoppingList(): Promise<ShoppingListResponse> {
    // Use trailing slash to avoid redirects that can drop auth headers on some platforms
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/`, {
      method: 'GET',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }

    return await response.json();
  }

  /**
   * Update a shopping list item's checked status
   */
  async updateShoppingListItem(itemId: string, isChecked: boolean): Promise<void> {
    const request: UpdateShoppingListItemRequest = {
      itemId,
      isChecked
    };

    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/items/${itemId}`, {
      method: 'PUT',
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }
  }

  /**
   * Clear all items from the shopping list
   */
  async clearShoppingList(): Promise<void> {
    const response = await this.makeAuthenticatedRequest(`${this.baseUrl}/api/shopping-list/clear`, {
      method: 'DELETE',
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new ApiError(
        errorData.detail || `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        errorData.code
      );
    }
  }
}

// Export singleton instance
export const apiService = new APIService();

// Export class for testing or custom instances
export default APIService;
