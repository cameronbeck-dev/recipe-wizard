import React, { createContext, useContext, useEffect, useState } from 'react';
import { useColorScheme, Appearance } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MD3Theme } from 'react-native-paper';
import { PreferencesService } from '../services/preferences';
import { 
  BRAND_COLORS, 
  LIGHT_THEME, 
  DARK_THEME,
  TYPOGRAPHY,
  SPACING,
  BORDER_RADIUS,
  SHADOWS
} from './theme';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeContextType {
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
  theme: {
    colors: {
      wizard: typeof BRAND_COLORS.wizard;
      status: typeof BRAND_COLORS.status;
      theme: typeof LIGHT_THEME | typeof DARK_THEME;
    };
    typography: typeof TYPOGRAPHY;
    spacing: typeof SPACING;
    borderRadius: typeof BORDER_RADIUS;
    shadows: typeof SHADOWS;
  };
  isDark: boolean;
  isLight: boolean;
}

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

const THEME_STORAGE_KEY = '@RecipeWizard:theme';

interface ThemeProviderProps {
  children: React.ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const systemColorScheme = useColorScheme();
  const [themeMode, setThemeModeState] = useState<ThemeMode>('system');
  const [isLoading, setIsLoading] = useState(true);
  const [forcedSystemScheme, setForcedSystemScheme] = useState<'light' | 'dark' | null>(null);
  
  // Determine the effective theme based on mode and system preference
  const getEffectiveTheme = (mode: ThemeMode, systemScheme: 'light' | 'dark' | null | undefined, forced: 'light' | 'dark' | null): 'light' | 'dark' => {
    if (mode === 'system') {
      // Use forced scheme if available (for Expo Go workaround), otherwise use detected system scheme
      return forced || systemScheme || 'dark'; // Default to dark if system scheme is null/undefined
    }
    return mode;
  };

  const effectiveTheme = getEffectiveTheme(themeMode, systemColorScheme, forcedSystemScheme);
  const isDark = effectiveTheme === 'dark';

  
  // Build the theme object with the correct colors
  const theme = {
    colors: {
      wizard: BRAND_COLORS.wizard,
      status: BRAND_COLORS.status,
      theme: isDark ? DARK_THEME : LIGHT_THEME,
    },
    typography: TYPOGRAPHY,
    spacing: SPACING,
    borderRadius: BORDER_RADIUS,
    shadows: SHADOWS,
  };
  
  // Load saved theme preference on mount
  useEffect(() => {
    const loadThemePreference = async () => {
      try {
        // First try to load from preferences service (unified approach)
        const themePreference = await PreferencesService.getThemePreference();
        setThemeModeState(themePreference);
      } catch (error) {
        // Fallback to old storage method
        try {
          const savedTheme = await AsyncStorage.getItem(THEME_STORAGE_KEY);
          if (savedTheme && ['light', 'dark', 'system'].includes(savedTheme)) {
            setThemeModeState(savedTheme as ThemeMode);
          }
        } catch (fallbackError) {
        }
      } finally {
        setIsLoading(false);
      }
    };
    
    loadThemePreference();
  }, []);

  // Listen for system appearance changes as a fallback for Expo Go issues
  useEffect(() => {
    const subscription = Appearance.addChangeListener(({ colorScheme }) => {

      // Force update the system scheme when Appearance API detects changes
      // This helps with Expo Go where useColorScheme() might not update immediately
      if (colorScheme && colorScheme !== systemColorScheme) {
        setForcedSystemScheme(colorScheme);

        // Clear the forced scheme after a short delay to let useColorScheme catch up
        setTimeout(() => {
          setForcedSystemScheme(null);
        }, 1000);
      }
    });

    return () => subscription?.remove();
  }, [systemColorScheme]);
  
  // Save theme preference when it changes
  const setThemeMode = async (mode: ThemeMode) => {
    try {
      // Use the preferences service for unified theme management
      await PreferencesService.updateThemePreference(mode);
      setThemeModeState(mode);
    } catch (error) {
      // Fallback to old storage method
      try {
        await AsyncStorage.setItem(THEME_STORAGE_KEY, mode);
        setThemeModeState(mode);
      } catch (fallbackError) {
      }
    }
  };
  
  // Don't render children until theme is loaded
  if (isLoading) {
    return null; // or a loading screen if desired
  }
  
  const contextValue: ThemeContextType = {
    themeMode,
    setThemeMode,
    theme,
    isDark,
    isLight: !isDark,
  };
  
  return (
    <ThemeContext.Provider value={contextValue}>
      {children}
    </ThemeContext.Provider>
  );
}

// Custom hook to use theme context
export function useAppTheme() {
  const context = useContext(ThemeContext);
  
  if (context === undefined) {
    throw new Error('useAppTheme must be used within a ThemeProvider');
  }
  
  return context;
}

// Utility hook for components that just need colors and basic theme info
export function useThemeColors() {
  const { theme, isDark, isLight } = useAppTheme();
  
  return {
    ...theme.colors,
    isDark,
    isLight,
  };
}

// Helper hook for creating theme-aware styles
export function useThemedStyles<T extends Record<string, any>>(
  styleFactory: (theme: ThemeContextType['theme'], isDark: boolean) => T
): T {
  const { theme, isDark } = useAppTheme();
  return styleFactory(theme, isDark);
}

// Builds a react-native-paper MD3 theme from the app's own theme, so Paper
// components (Portal, Snackbar, Dialog, etc.) match the app's brand colors
// instead of Paper's default purple.
export function usePaperTheme(): MD3Theme {
  const { theme, isDark } = useAppTheme();

  return {
    dark: isDark,
    version: 3,
    mode: 'adaptive',
    colors: {
      primary: theme.colors.wizard.primary,
      onPrimary: '#ffffff',
      primaryContainer: theme.colors.wizard.primary + '20',
      onPrimaryContainer: theme.colors.wizard.primary,
      secondary: theme.colors.wizard.accent,
      onSecondary: '#ffffff',
      secondaryContainer: theme.colors.wizard.accent + '20',
      onSecondaryContainer: theme.colors.wizard.accent,
      tertiary: theme.colors.wizard.accent,
      onTertiary: '#ffffff',
      tertiaryContainer: theme.colors.wizard.accent + '20',
      onTertiaryContainer: theme.colors.wizard.accent,
      error: theme.colors.status.error,
      onError: '#ffffff',
      errorContainer: theme.colors.status.error + '20',
      onErrorContainer: theme.colors.status.error,
      background: theme.colors.theme.background,
      onBackground: theme.colors.theme.text,
      surface: theme.colors.theme.surface,
      onSurface: theme.colors.theme.text,
      surfaceVariant: theme.colors.theme.backgroundSecondary,
      onSurfaceVariant: theme.colors.theme.textSecondary,
      outline: theme.colors.theme.border,
      outlineVariant: theme.colors.theme.borderLight,
      shadow: '#000000',
      scrim: '#000000',
      inverseSurface: isDark ? '#ffffff' : '#000000',
      inverseOnSurface: isDark ? '#000000' : '#ffffff',
      inversePrimary: theme.colors.wizard.primaryLight,
      elevation: {
        level0: 'transparent',
        level1: theme.colors.theme.backgroundSecondary,
        level2: theme.colors.theme.backgroundTertiary,
        level3: theme.colors.theme.surface,
        level4: theme.colors.theme.surface,
        level5: theme.colors.theme.surface,
      },
      surfaceDisabled: theme.colors.theme.textDisabled + '12',
      onSurfaceDisabled: theme.colors.theme.textDisabled,
      backdrop: 'rgba(0, 0, 0, 0.5)',
    } as any,
  } as MD3Theme;
}