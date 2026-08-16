// Authentication service for handling user login/registration
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { API_BASE_URL } from './config';

// SecureStore has no working implementation on web (expo-secure-store's web
// shim is a stub and throws). Prefer SecureStore everywhere; fall back to
// AsyncStorage only when it's unavailable, mirroring deviceId.ts.
async function secureSetItem(key: string, value: string): Promise<void> {
  try {
    await SecureStore.setItemAsync(key, value);
  } catch (error) {
    console.warn(`⚠️ SecureStore unavailable for "${key}", falling back to AsyncStorage:`, error);
    await AsyncStorage.setItem(key, value);
  }
}

async function secureGetItem(key: string): Promise<string | null> {
  try {
    return await SecureStore.getItemAsync(key);
  } catch (error) {
    console.warn(`⚠️ SecureStore unavailable for "${key}", falling back to AsyncStorage:`, error);
    return await AsyncStorage.getItem(key);
  }
}

async function secureDeleteItem(key: string): Promise<void> {
  try {
    await SecureStore.deleteItemAsync(key);
  } catch (error) {
    console.warn(`⚠️ SecureStore unavailable for "${key}", falling back to AsyncStorage:`, error);
  }
  await AsyncStorage.removeItem(key);
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  username?: string;
  firstName?: string;
  lastName?: string;
}

export interface User {
  id: number;
  email: string;
  username?: string;
  firstName?: string;
  lastName?: string;
  isActive: boolean;
}

export interface AuthTokens {
  accessToken: string;
  tokenType: string;
  user: User;
}

// Backend response format
interface BackendTokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: {
    id: number;
    email: string;
    username?: string;
    firstName?: string;
    lastName?: string;
    isActive: boolean;
  };
}

// Secure storage keys
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';
const CREDENTIALS_KEY = 'auth_credentials';

// Helper function to transform backend response to frontend format
function transformTokenResponse(backendResponse: BackendTokenResponse): AuthTokens {
  return {
    accessToken: backendResponse.access_token,
    tokenType: backendResponse.token_type,
    user: {
      id: backendResponse.user.id,
      email: backendResponse.user.email,
      username: backendResponse.user.username,
      firstName: backendResponse.user.firstName,
      lastName: backendResponse.user.lastName,
      isActive: backendResponse.user.isActive,
    },
  };
}

export class AuthService {
  /**
   * Login with email and password
   */
  static async login(credentials: LoginCredentials): Promise<AuthTokens> {
    try {
      // console.log('🔐 Attempting login for:', credentials.email);
      
      const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Login failed' }));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const backendTokens: BackendTokenResponse = await response.json();
      const tokens = transformTokenResponse(backendTokens);
      
      // Store tokens and credentials securely for refresh
      await this.storeTokens(tokens);
      await secureSetItem(CREDENTIALS_KEY, JSON.stringify(credentials));

      // console.log('✅ Login successful for:', tokens.user.email);
      return tokens;
      
    } catch (error) {
      console.error('❌ Login failed:', error);
      throw error;
    }
  }

  /**
   * Register new user account
   */
  static async register(userData: RegisterData): Promise<AuthTokens> {
    try {
      // console.log('📝 Attempting registration for:', userData.email);
      
      const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(userData),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Registration failed' }));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }

      const backendTokens: BackendTokenResponse = await response.json();
      const tokens = transformTokenResponse(backendTokens);
      
      // Store tokens and credentials securely for refresh
      await this.storeTokens(tokens);
      await secureSetItem(CREDENTIALS_KEY, JSON.stringify({
        email: userData.email,
        password: userData.password
      }));

      // console.log('✅ Registration successful for:', tokens.user.email);
      return tokens;
      
    } catch (error) {
      console.error('❌ Registration failed:', error);
      throw error;
    }
  }

  /**
   * Logout user and clear stored tokens
   */
  static async logout(): Promise<void> {
    try {
      // Call logout endpoint if user is authenticated
      const token = await this.getStoredToken();
      if (token) {
        try {
          await fetch(`${API_BASE_URL}/api/auth/logout`, {
            method: 'POST',
            headers: {
              'Authorization': `Bearer ${token}`,
            },
          });
        } catch (error) {
          console.warn('⚠️ Logout API call failed, continuing with local cleanup:', error);
        }
      }

      // Clear stored data
      await this.clearTokens();
      // console.log('✅ Logout successful');
      
    } catch (error) {
      console.error('❌ Logout failed:', error);
      throw error;
    }
  }

  /**
   * Permanently delete the current user's account and all associated data.
   * The backend cascade-deletes recipes, shopping lists, saved items, and jobs.
   * Local tokens are cleared on success regardless of server response.
   */
  static async deleteAccount(): Promise<void> {
    const token = await this.getStoredToken();
    if (!token) {
      throw new Error('You must be signed in to delete your account.');
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/users/account`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Account deletion failed' }));
        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
      }
    } finally {
      // Always clear local credentials so the app returns to a signed-out
      // state even if the server response was lost mid-flight.
      await this.clearTokens();
    }
  }

  /**
   * Store authentication tokens securely
   */
  static async storeTokens(tokens: AuthTokens): Promise<void> {
    await secureSetItem(TOKEN_KEY, tokens.accessToken);
    await secureSetItem(USER_KEY, JSON.stringify(tokens.user));
  }

  /**
   * Clear stored authentication data
   */
  static async clearTokens(): Promise<void> {
    await secureDeleteItem(TOKEN_KEY);
    await secureDeleteItem(USER_KEY);
    await secureDeleteItem(CREDENTIALS_KEY);
  }

  /**
   * Get stored authentication token
   */
  static async getStoredToken(): Promise<string | null> {
    return await secureGetItem(TOKEN_KEY);
  }

  /**
   * Get stored user data
   */
  static async getStoredUser(): Promise<User | null> {
    const userJson = await secureGetItem(USER_KEY);
    if (userJson) {
      try {
        return JSON.parse(userJson);
      } catch (error) {
        console.error('❌ Error parsing stored user data:', error);
        return null;
      }
    }
    return null;
  }

  /**
   * Check if user is currently authenticated
   */
  static async isAuthenticated(): Promise<boolean> {
    const token = await this.getStoredToken();
    const user = await this.getStoredUser();
    return !!(token && user);
  }

  /**
   * Refresh authentication token.
   *
   * Token/credentials are only cleared when the server explicitly rejects auth
   * (HTTP 401/403). Transient network errors (offline, DNS, timeouts) return
   * null without touching SecureStore so the user stays signed in across
   * flaky connectivity.
   */
  static async refreshToken(): Promise<AuthTokens | null> {
    const token = await this.getStoredToken();
    if (!token) {
      return null;
    }

    // First try JWT refresh
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
    } catch (error) {
      console.warn('⚠️ Token refresh network error, keeping stored tokens:', error);
      return null;
    }

    if (response.ok) {
      try {
        const backendTokens: BackendTokenResponse = await response.json();
        const newTokens = transformTokenResponse(backendTokens);
        await this.storeTokens(newTokens);
        return newTokens;
      } catch (error) {
        console.warn('⚠️ Failed to parse refresh response, keeping stored tokens:', error);
        return null;
      }
    }

    // Only server-side rejection of the JWT should fall through to credentials
    const jwtRejected = response.status === 401 || response.status === 403;
    if (!jwtRejected) {
      console.warn(`⚠️ Token refresh returned ${response.status}; keeping stored tokens`);
      return null;
    }

    // JWT rejected: try credential-based re-authentication
    const credentialsJson = await secureGetItem(CREDENTIALS_KEY);
    if (!credentialsJson) {
      await this.clearTokens();
      return null;
    }

    let credentials: LoginCredentials;
    try {
      credentials = JSON.parse(credentialsJson);
    } catch {
      await this.clearTokens();
      return null;
    }

    let loginResponse: Response;
    try {
      loginResponse = await fetch(`${API_BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(credentials),
      });
    } catch (error) {
      console.warn('⚠️ Credential re-auth network error, keeping stored tokens:', error);
      return null;
    }

    if (loginResponse.ok) {
      try {
        const backendTokens: BackendTokenResponse = await loginResponse.json();
        const newTokens = transformTokenResponse(backendTokens);
        await this.storeTokens(newTokens);
        return newTokens;
      } catch (error) {
        console.warn('⚠️ Failed to parse credential re-auth response:', error);
        return null;
      }
    }

    // Server explicitly rejected the stored credentials — now it's safe to clear
    if (loginResponse.status === 401 || loginResponse.status === 403) {
      await this.clearTokens();
      return null;
    }

    console.warn(`⚠️ Credential re-auth returned ${loginResponse.status}; keeping stored tokens`);
    return null;
  }

  /**
   * Validate current token with backend.
   *
   * On network errors we optimistically return the locally-stored user so the
   * app works offline. Tokens are only cleared when the server returns 401/403
   * or explicitly says the token is invalid.
   */
  static async validateToken(): Promise<User | null> {
    const token = await this.getStoredToken();
    if (!token) {
      return null;
    }

    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/api/auth/verify-token`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });
    } catch (error) {
      console.warn('⚠️ Token validation network error, trusting stored user:', error);
      return await this.getStoredUser();
    }

    if (response.status === 401 || response.status === 403) {
      await this.clearTokens();
      return null;
    }

    if (!response.ok) {
      // Other server errors (5xx etc.) — don't clear, fall back to stored user
      console.warn(`⚠️ Token validation returned ${response.status}; trusting stored user`);
      return await this.getStoredUser();
    }

    try {
      const result = await response.json();
      if (result.valid) {
        return result.user;
      }
      await this.clearTokens();
      return null;
    } catch (error) {
      console.warn('⚠️ Failed to parse validation response, trusting stored user:', error);
      return await this.getStoredUser();
    }
  }
}

export default AuthService;