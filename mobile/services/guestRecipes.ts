// Local-first storage for recipes generated while browsing as a guest.
// The backend keeps no history for guests, so this is the only place a
// guest's generated recipes survive past the current screen.
import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { RecipeGenerationResponse } from '../types/api';

export interface GuestRecipe extends RecipeGenerationResponse {
  localId: string;
  createdAt: string;
}

const MAX_STORED_RECIPES = 200;

export class GuestRecipesService {
  private static readonly STORAGE_KEY = '@recipe_wizard_guest_recipes';

  /**
   * Get all locally stored guest recipes, newest first.
   */
  static async getAll(): Promise<GuestRecipe[]> {
    try {
      const stored = await AsyncStorage.getItem(this.STORAGE_KEY);
      return stored ? (JSON.parse(stored) as GuestRecipe[]) : [];
    } catch (error) {
      console.error('Failed to load guest recipes:', error);
      throw new Error('Failed to load guest recipes');
    }
  }

  /**
   * Add a newly generated recipe to local guest storage. Caps stored entries
   * at MAX_STORED_RECIPES, dropping the oldest (FIFO) on overflow.
   */
  static async add(recipe: RecipeGenerationResponse): Promise<void> {
    try {
      const existing = await this.getAll();
      const newRecipe: GuestRecipe = {
        ...recipe,
        localId: Crypto.randomUUID(),
        createdAt: new Date().toISOString(),
      };
      const updated = [newRecipe, ...existing].slice(0, MAX_STORED_RECIPES);
      await AsyncStorage.setItem(this.STORAGE_KEY, JSON.stringify(updated));
    } catch (error) {
      console.error('Failed to add guest recipe:', error);
      throw new Error('Failed to add guest recipe');
    }
  }

  /**
   * Remove a single guest recipe by its local id.
   */
  static async remove(localId: string): Promise<void> {
    try {
      const existing = await this.getAll();
      const updated = existing.filter(recipe => recipe.localId !== localId);
      await AsyncStorage.setItem(this.STORAGE_KEY, JSON.stringify(updated));
    } catch (error) {
      console.error('Failed to remove guest recipe:', error);
      throw new Error('Failed to remove guest recipe');
    }
  }

  /**
   * Clear all locally stored guest recipes (e.g. after a successful
   * migration to a real account on sign-up/login).
   */
  static async clear(): Promise<void> {
    try {
      await AsyncStorage.removeItem(this.STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear guest recipes:', error);
      throw new Error('Failed to clear guest recipes');
    }
  }

  /**
   * Get the count of locally stored guest recipes.
   */
  static async count(): Promise<number> {
    try {
      const existing = await this.getAll();
      return existing.length;
    } catch (error) {
      console.error('Failed to count guest recipes:', error);
      return 0;
    }
  }
}

export default GuestRecipesService;
