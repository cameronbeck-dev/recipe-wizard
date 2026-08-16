// Authentication context for managing global auth state
import React, { createContext, useContext, useEffect, useState } from 'react';
import AuthService, { User, LoginCredentials, RegisterData, AuthTokens } from '../services/auth';
import { PreferencesService } from '../services/preferences';
import { purchasesService } from '../services/purchases';
import { GuestRecipesService } from '../services/guestRecipes';
import { apiService } from '../services/api';

async function identifyPurchaser(user: User) {
  try {
    await purchasesService.setUserID(String(user.id));
  } catch (error) {
    console.error('❌ Failed to identify RevenueCat user:', error);
  }
}

async function deidentifyPurchaser() {
  try {
    await purchasesService.logout();
  } catch (error) {
    console.error('❌ Failed to log out RevenueCat user:', error);
  }
}

const GUEST_IMPORT_BATCH_SIZE = 100; // matches the backend's max items per /api/recipes/import call

// Merge any locally-stored guest recipes into the now-signed-in account.
// Called on both registration and login (guest history merges either way).
// Local data is only cleared once the import call actually succeeds — a
// flaky network should never lose a guest's recipes.
async function migrateGuestData() {
  try {
    const guestRecipes = await GuestRecipesService.getAll();
    if (guestRecipes.length === 0) return;

    for (let i = 0; i < guestRecipes.length; i += GUEST_IMPORT_BATCH_SIZE) {
      await apiService.importGuestRecipes(guestRecipes.slice(i, i + GUEST_IMPORT_BATCH_SIZE));
    }

    await GuestRecipesService.clear();
  } catch (error) {
    console.error('❌ Failed to migrate guest recipes:', error);
  }
}

interface AuthContextType {
  // State
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  // True immediately after a sign-out, cleared on the next successful
  // login/register. Drives a "you're signed out" banner (see history tab).
  justSignedOut: boolean;

  // Actions
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (userData: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  deleteAccount: () => Promise<void>;
  refreshAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [justSignedOut, setJustSignedOut] = useState(false);

  const isAuthenticated = !!user;

  // Initialize authentication state on app start
  useEffect(() => {
    initializeAuth();
  }, []);

  const initializeAuth = async () => {
    try {
      // console.log('🔄 Initializing authentication...');
      
      // Check if user has stored tokens
      const isAuth = await AuthService.isAuthenticated();
      
      if (isAuth) {
        // Validate tokens with backend
        const validUser = await AuthService.validateToken();

        if (validUser) {
          setUser(validUser);
          PreferencesService.syncFromBackend().catch(() => {});
          identifyPurchaser(validUser);
        } else {
          // Tokens invalid, try refresh
          const refreshResult = await AuthService.refreshToken();

          if (refreshResult) {
            setUser(refreshResult.user);
            PreferencesService.syncFromBackend().catch(() => {});
            identifyPurchaser(refreshResult.user);
          }
        }
      } else {
        // console.log('ℹ️ No stored authentication found');
      }
      
    } catch (error) {
      console.error('❌ Auth initialization failed:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const login = async (credentials: LoginCredentials) => {
    try {
      setIsLoading(true);

      const tokens = await AuthService.login(credentials);
      setUser(tokens.user);

      // Pull server-side preferences (allergens, dietary, grocery categories) so
      // a fresh install / new device inherits the user's existing setup.
      PreferencesService.syncFromBackend().catch(() => {});
      identifyPurchaser(tokens.user);
      migrateGuestData();
      setJustSignedOut(false);
    } catch (error) {
      console.error('❌ Login failed in context:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const register = async (userData: RegisterData) => {
    try {
      setIsLoading(true);

      const tokens = await AuthService.register(userData);
      setUser(tokens.user);
      identifyPurchaser(tokens.user);

      // Push any preferences the user configured before signing up so they
      // survive reinstall. If there's no local data yet this is a no-op on
      // the backend.
      try {
        const local = await PreferencesService.loadPreferences();
        PreferencesService.saveToBackend(local).catch(() => {});
      } catch {}

      migrateGuestData();
      setJustSignedOut(false);
    } catch (error) {
      console.error('❌ Registration failed in context:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = async () => {
    try {
      setIsLoading(true);
      
      await AuthService.logout();
      setUser(null);
      deidentifyPurchaser();
      setJustSignedOut(true);

      // console.log('✅ User logged out');

    } catch (error) {
      console.error('❌ Logout failed in context:', error);
      // Even if logout API fails, clear local state
      setUser(null);
      deidentifyPurchaser();
      setJustSignedOut(true);
    } finally {
      setIsLoading(false);
    }
  };

  const deleteAccount = async () => {
    try {
      setIsLoading(true);
      await AuthService.deleteAccount();
      setUser(null);
      deidentifyPurchaser();
    } catch (error) {
      console.error('❌ Account deletion failed:', error);
      throw error;
    } finally {
      setIsLoading(false);
    }
  };

  const refreshAuth = async () => {
    try {
      const refreshResult = await AuthService.refreshToken();
      
      if (refreshResult) {
        setUser(refreshResult.user);
        identifyPurchaser(refreshResult.user);
        // console.log('✅ Auth refreshed in context');
      } else {
        setUser(null);
        deidentifyPurchaser();
        // console.log('❌ Auth refresh failed, user logged out');
      }

    } catch (error) {
      console.error('❌ Auth refresh error:', error);
      setUser(null);
      deidentifyPurchaser();
    }
  };

  const value: AuthContextType = {
    // State
    user,
    isLoading,
    isAuthenticated,
    justSignedOut,

    // Actions
    login,
    register,
    logout,
    deleteAccount,
    refreshAuth,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

// Hook to use authentication context
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  
  return context;
}

export default AuthContext;