// Tracks whether the user has passed through the welcome screen at least
// once, so a returning guest lands straight on the prompt tab instead of
// being shown the welcome screen again.
import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = '@recipe_wizard_has_onboarded';

export async function getHasOnboarded(): Promise<boolean> {
  try {
    const value = await AsyncStorage.getItem(STORAGE_KEY);
    return value === 'true';
  } catch (error) {
    console.error('Failed to read onboarding flag:', error);
    return false;
  }
}

export async function setHasOnboarded(): Promise<void> {
  try {
    await AsyncStorage.setItem(STORAGE_KEY, 'true');
  } catch (error) {
    console.error('Failed to set onboarding flag:', error);
  }
}
