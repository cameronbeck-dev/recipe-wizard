import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  ScrollView,
  Alert,
  KeyboardAvoidingView,
  Platform,
  TouchableOpacity,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import DragList, { DragListRenderItemInfo } from 'react-native-draglist';

import { useAppTheme } from '../../constants/ThemeProvider';
import { useAuth } from '../../contexts/AuthContext';
import { usePremium } from '../../contexts/PremiumContext';
import { PreferencesService } from '../../services/preferences';
import { Button } from '../../components/Button';
import { TextInput } from '../../components/TextInput';
import { HeaderComponent } from '../../components/HeaderComponent';
import { PremiumBadge } from '../../components/PremiumBadge';
import { ExpandableCard } from '../../components/ExpandableCard';
import { CheckboxItem } from '../../components/CheckboxItem';
import {
  UserPreferences,
  DEFAULT_USER_PREFERENCES,
  DEFAULT_GROCERY_CATEGORIES
} from '../../types/api';

const STORAGE_KEY = '@recipe_wizard_preferences';

// Simple debounce utility
function debounce<T extends (...args: any[]) => void>(func: T, delay: number): (...args: Parameters<T>) => void {
  let timeoutId: NodeJS.Timeout;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => func(...args), delay);
  };
}

// Common dietary restrictions and allergens
const COMMON_DIETARY_RESTRICTIONS = [
  'vegetarian', 'vegan', 'pescatarian', 'gluten-free', 'dairy-free', 
  'nut-free', 'low-carb', 'keto', 'paleo', 'halal', 'kosher'
];

const COMMON_ALLERGENS = [
  'nuts', 'peanuts', 'shellfish', 'fish', 'eggs', 'dairy', 'soy', 'gluten', 'sesame'
];

export default function ProfileScreen() {
  const { theme, themeMode, setThemeMode, isDark } = useAppTheme();
  const router = useRouter();
  const { logout, deleteAccount, user } = useAuth();
  const { isPremium, isLoading: premiumLoading, setPremiumStatus } = usePremium();
  
  // Refs for clearing TextInputs
  const categoryInputRef = useRef<any>(null);
  const dietaryInputRef = useRef<any>(null);
  const allergenInputRef = useRef<any>(null);
  
  const [preferences, setPreferences] = useState<UserPreferences>({
    ...DEFAULT_USER_PREFERENCES,
    updatedAt: new Date().toISOString(),
    createdAt: new Date().toISOString(),
  });
  const [loading, setLoading] = useState(true);
  const [signingOut, setSigningOut] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [autoSaving, setAutoSaving] = useState(false);
  const [lastSaved, setLastSaved] = useState<Date | null>(null);

  // Load preferences from storage, then refresh from backend in the background
  useEffect(() => {
    loadPreferences();
  }, []);

  const loadPreferences = async () => {
    try {
      const stored = await AsyncStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsedPreferences = JSON.parse(stored);
        setPreferences({
          ...DEFAULT_USER_PREFERENCES,
          ...parsedPreferences,
          updatedAt: new Date().toISOString(),
        });
      }
    } catch (error) {
      console.error('Failed to load preferences:', error);
    } finally {
      setLoading(false);
    }

    // Pull latest from backend (no-op if offline/unauthenticated) and reflect
    // any server-side changes in the UI without blocking initial render.
    try {
      const synced = await PreferencesService.syncFromBackend();
      if (synced) {
        setPreferences(synced);
      }
    } catch {}
  };


  // Auto-save preferences with debouncing
  const autoSavePreferences = useCallback(async (preferencesToSave: UserPreferences) => {
    try {
      setAutoSaving(true);
      const updatedPreferences = {
        ...preferencesToSave,
        updatedAt: new Date().toISOString(),
      };
      await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(updatedPreferences));
      setLastSaved(new Date());

      // Mirror to the backend so preferences (especially allergens) survive
      // reinstall and sync across devices. Fire-and-forget; local write is the
      // source of truth for this UI.
      PreferencesService.saveToBackend(updatedPreferences).catch(() => {});
    } catch (error) {
      console.error('❌ Failed to auto-save preferences:', error);
      // Don't show alert for auto-save failures - just log
    } finally {
      setAutoSaving(false);
    }
  }, []);

  // Debounced auto-save to avoid too many saves
  const debouncedAutoSave = useCallback(
    debounce((prefs: UserPreferences) => autoSavePreferences(prefs), 1000),
    [autoSavePreferences]
  );

  const handleSignOut = async () => {
    Alert.alert(
      'Sign Out', 
      'Are you sure you want to sign out?',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Sign Out', 
          style: 'destructive',
          onPress: async () => {
            try {
              setSigningOut(true);
              await logout();
              // Land in guest mode, not a sign-in wall — the user has
              // already onboarded, so index.tsx's routing sends them
              // straight back to the prompt tab.
              router.replace('/(tabs)/prompt');
            } catch (error) {
              console.error('Sign out error:', error);
              Alert.alert('Error', 'Failed to sign out. Please try again.');
            } finally {
              setSigningOut(false);
            }
          }
        }
      ]
    );
  };

  const handleDeleteAccount = () => {
    Alert.alert(
      'Delete Account?',
      'This will permanently delete your account, all your saved recipes, your shopping list, preferences, and recipe history. This cannot be undone.\n\nIf you have an active subscription, cancel it in your device Subscription settings before deleting, otherwise you will continue to be billed.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Delete Forever',
          style: 'destructive',
          onPress: () => {
            Alert.alert(
              'Are you absolutely sure?',
              'Last chance. Your account and all associated data will be deleted immediately.',
              [
                { text: 'Cancel', style: 'cancel' },
                {
                  text: 'Yes, delete my account',
                  style: 'destructive',
                  onPress: async () => {
                    try {
                      setDeletingAccount(true);
                      await deleteAccount();
                      // Land in guest mode, not a sign-in wall, matching
                      // sign-out — the account is gone, not "signed out",
                      // so we don't set justSignedOut (its "sign back in to
                      // see your saved recipes" banner would be misleading
                      // here: there's nothing left to sign back in to).
                      router.replace('/(tabs)/prompt');
                    } catch (error) {
                      console.error('Delete account error:', error);
                      Alert.alert(
                        'Deletion failed',
                        error instanceof Error ? error.message : 'Could not delete your account. Please try again or email privacy@cameronbeck.dev.'
                      );
                    } finally {
                      setDeletingAccount(false);
                    }
                  },
                },
              ]
            );
          },
        },
      ]
    );
  };

  const updatePreference = useCallback(<K extends keyof UserPreferences>(
    key: K,
    value: UserPreferences[K]
  ) => {
    setPreferences(prev => {
      const updated = { ...prev, [key]: value };
      debouncedAutoSave(updated);
      return updated;
    });
  }, [debouncedAutoSave]);

  const toggleArrayItem = useCallback((
    key: keyof Pick<UserPreferences, 'dietaryRestrictions' | 'allergens' | 'dislikes' | 'groceryCategories'>,
    item: string
  ) => {
    setPreferences(prev => {
      const updated = {
        ...prev,
        [key]: prev[key].includes(item)
          ? prev[key].filter(i => i !== item)
          : [...prev[key], item]
      };
      debouncedAutoSave(updated);
      return updated;
    });
  }, [debouncedAutoSave]);

  const addCustomItem = (
    key: keyof Pick<UserPreferences, 'dietaryRestrictions' | 'allergens' | 'dislikes' | 'groceryCategories'>,
    item: string
  ) => {
    if (item.trim() && !preferences[key].includes(item.trim())) {
      setPreferences(prev => {
        const updated = {
          ...prev,
          [key]: [...prev[key], item.trim()]
        };
        debouncedAutoSave(updated);
        return updated;
      });
    }
  };

  const removeCustomItem = (
    key: keyof Pick<UserPreferences, 'dietaryRestrictions' | 'allergens' | 'dislikes' | 'groceryCategories'>,
    item: string
  ) => {
    setPreferences(prev => {
      const updated = {
        ...prev,
        [key]: prev[key].filter(i => i !== item)
      };
      debouncedAutoSave(updated);
      return updated;
    });
  };

  const onCategoriesReordered = useCallback((fromIndex: number, toIndex: number) => {
    setPreferences(prev => {
      const newOrder = [...prev.groceryCategories];
      const [removed] = newOrder.splice(fromIndex, 1);
      newOrder.splice(toIndex, 0, removed);
      const updated = { ...prev, groceryCategories: newOrder };
      debouncedAutoSave(updated);
      return updated;
    });
  }, [debouncedAutoSave]);

  const renderCategoryItem = useCallback((
    info: DragListRenderItemInfo<string>
  ) => {
    const { item: category, onDragStart, onDragEnd, isActive } = info;
    
    return (
      <TouchableOpacity
        onPressIn={onDragStart}
        onPressOut={onDragEnd}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingVertical: theme.spacing.md,
          paddingHorizontal: theme.spacing.md,
          backgroundColor: isActive 
            ? theme.colors.wizard.primary + '20'
            : theme.colors.theme.surface,
          borderRadius: theme.borderRadius.md,
          marginBottom: theme.spacing.sm,
          elevation: isActive ? 4 : 0,
          shadowColor: '#000',
          shadowOffset: { width: 0, height: 2 },
          shadowOpacity: isActive ? 0.15 : 0,
          shadowRadius: 4,
          borderWidth: isActive ? 2 : 1,
          borderColor: isActive 
            ? theme.colors.wizard.primary
            : theme.colors.theme.border,
        }}
      >
        {/* Drag Handle */}
        <View style={{ marginRight: theme.spacing.sm }}>
          <MaterialCommunityIcons
            name="drag-horizontal"
            size={20}
            color={isActive 
              ? theme.colors.wizard.primary
              : theme.colors.theme.textTertiary
            }
          />
        </View>
        
        <Text style={{
          color: isActive 
            ? theme.colors.wizard.primary
            : theme.colors.theme.text,
          fontSize: theme.typography.fontSize.bodyLarge,
          flex: 1,
          textTransform: 'capitalize',
          fontWeight: isActive ? '600' : '400',
        }}>
          {category.replace('-', ' ')}
        </Text>
        
        <TouchableOpacity
          onPress={() => removeCustomItem('groceryCategories', category)}
          style={{ 
            padding: theme.spacing.xs,
            marginLeft: theme.spacing.sm,
          }}
          hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        >
          <MaterialCommunityIcons 
            name="close-circle" 
            size={20} 
            color={theme.colors.status.error} 
          />
        </TouchableOpacity>
      </TouchableOpacity>
    );
  }, [theme, removeCustomItem]);

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.theme.background }} edges={['top']}>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <Text style={{ color: theme.colors.theme.text, fontSize: 16 }}>
            Loading preferences...
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.theme.background }} edges={['top']}>
      <HeaderComponent
        title="Profile & Settings"
        subtitle="Customize your cooking experience"
        rightContent={<PremiumBadge size="small" />}
      />
      
      <KeyboardAvoidingView 
        style={{ flex: 1, backgroundColor: theme.colors.theme.background }}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        <ScrollView 
          style={{ flex: 1, backgroundColor: theme.colors.theme.background }}
          contentContainerStyle={{ 
            padding: theme.spacing.lg,
            backgroundColor: theme.colors.theme.background,
          }}
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {/* Units Preference */}
          <ExpandableCard
            title="Measurement Units"
            subtitle={preferences.units === 'metric' ? 'Metric (kg, ml, °C)' : 'Imperial (lbs, cups, °F)'}
            icon="scale-balance"
            defaultExpanded={false}
          >
            <View style={{ gap: theme.spacing.md }}>
              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  padding: theme.spacing.md,
                  backgroundColor: preferences.units === 'metric' 
                    ? theme.colors.wizard.primary + '20' 
                    : theme.colors.theme.surface,
                  borderRadius: theme.borderRadius.lg,
                  borderWidth: preferences.units === 'metric' ? 2 : 1,
                  borderColor: preferences.units === 'metric' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.border,
                }}
                onPress={() => updatePreference('units', 'metric')}
              >
                <MaterialCommunityIcons 
                  name="scale-balance" 
                  size={24} 
                  color={preferences.units === 'metric' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.textSecondary
                  } 
                />
                <Text style={{
                  marginLeft: theme.spacing.md,
                  color: preferences.units === 'metric' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.text,
                  fontSize: theme.typography.fontSize.bodyLarge,
                  fontWeight: preferences.units === 'metric' ? '600' : '400',
                }}>
                  Metric (kg, ml, °C)
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  padding: theme.spacing.md,
                  backgroundColor: preferences.units === 'imperial' 
                    ? theme.colors.wizard.primary + '20' 
                    : theme.colors.theme.surface,
                  borderRadius: theme.borderRadius.lg,
                  borderWidth: preferences.units === 'imperial' ? 2 : 1,
                  borderColor: preferences.units === 'imperial' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.border,
                }}
                onPress={() => updatePreference('units', 'imperial')}
              >
                <MaterialCommunityIcons 
                  name="scale-balance" 
                  size={24} 
                  color={preferences.units === 'imperial' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.textSecondary
                  } 
                />
                <Text style={{
                  marginLeft: theme.spacing.md,
                  color: preferences.units === 'imperial' 
                    ? theme.colors.wizard.primary 
                    : theme.colors.theme.text,
                  fontSize: theme.typography.fontSize.bodyLarge,
                  fontWeight: preferences.units === 'imperial' ? '600' : '400',
                }}>
                  Imperial (lbs, cups, °F)
                </Text>
              </TouchableOpacity>
            </View>
          </ExpandableCard>

          {/* Theme Preference */}
          <ExpandableCard
            title="App Theme"
            subtitle={
              themeMode === 'system'
                ? `System (currently ${isDark ? 'dark' : 'light'})`
                : themeMode.charAt(0).toUpperCase() + themeMode.slice(1)
            }
            icon="palette"
            defaultExpanded={false}
          >
            <View style={{ gap: theme.spacing.md }}>
              {/* Light Theme Option */}
              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  padding: theme.spacing.md,
                  backgroundColor: themeMode === 'light'
                    ? theme.colors.wizard.primary + '20'
                    : theme.colors.theme.surface,
                  borderRadius: theme.borderRadius.lg,
                  borderWidth: themeMode === 'light' ? 2 : 1,
                  borderColor: themeMode === 'light'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.border,
                }}
                onPress={() => setThemeMode('light')}
              >
                <MaterialCommunityIcons
                  name="weather-sunny"
                  size={24}
                  color={themeMode === 'light'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.textSecondary
                  }
                  style={{ marginRight: theme.spacing.md }}
                />
                <View style={{ flex: 1 }}>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodyLarge,
                    fontWeight: theme.typography.fontWeight.medium,
                    color: themeMode === 'light'
                      ? theme.colors.wizard.primary
                      : theme.colors.theme.text,
                  }}>
                    Light
                  </Text>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                  }}>
                    Bright colors and white backgrounds
                  </Text>
                </View>
              </TouchableOpacity>

              {/* Dark Theme Option */}
              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  padding: theme.spacing.md,
                  backgroundColor: themeMode === 'dark'
                    ? theme.colors.wizard.primary + '20'
                    : theme.colors.theme.surface,
                  borderRadius: theme.borderRadius.lg,
                  borderWidth: themeMode === 'dark' ? 2 : 1,
                  borderColor: themeMode === 'dark'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.border,
                }}
                onPress={() => setThemeMode('dark')}
              >
                <MaterialCommunityIcons
                  name="weather-night"
                  size={24}
                  color={themeMode === 'dark'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.textSecondary
                  }
                  style={{ marginRight: theme.spacing.md }}
                />
                <View style={{ flex: 1 }}>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodyLarge,
                    fontWeight: theme.typography.fontWeight.medium,
                    color: themeMode === 'dark'
                      ? theme.colors.wizard.primary
                      : theme.colors.theme.text,
                  }}>
                    Dark
                  </Text>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                  }}>
                    Easy on the eyes with dark colors
                  </Text>
                </View>
              </TouchableOpacity>

              {/* System Theme Option */}
              <TouchableOpacity
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  padding: theme.spacing.md,
                  backgroundColor: themeMode === 'system'
                    ? theme.colors.wizard.primary + '20'
                    : theme.colors.theme.surface,
                  borderRadius: theme.borderRadius.lg,
                  borderWidth: themeMode === 'system' ? 2 : 1,
                  borderColor: themeMode === 'system'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.border,
                }}
                onPress={() => setThemeMode('system')}
              >
                <MaterialCommunityIcons
                  name="theme-light-dark"
                  size={24}
                  color={themeMode === 'system'
                    ? theme.colors.wizard.primary
                    : theme.colors.theme.textSecondary
                  }
                  style={{ marginRight: theme.spacing.md }}
                />
                <View style={{ flex: 1 }}>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodyLarge,
                    fontWeight: theme.typography.fontWeight.medium,
                    color: themeMode === 'system'
                      ? theme.colors.wizard.primary
                      : theme.colors.theme.text,
                  }}>
                    System
                  </Text>
                  <Text style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                  }}>
                    Follow your device's theme setting
                  </Text>
                </View>
              </TouchableOpacity>
            </View>
          </ExpandableCard>

          {/* Grocery Categories */}
          <ExpandableCard
            title="Grocery Categories"
            subtitle={`${preferences.groceryCategories.length} categories`}
            icon="format-list-bulleted"
            defaultExpanded={false}
          >
            <View>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium,
                marginBottom: theme.spacing.md,
              }}>
                Customize how ingredients are organized in your grocery lists. Drag to reorder.
              </Text>
              
              {preferences.groceryCategories.length > 0 && (
                <View style={{ marginBottom: theme.spacing.md }}>
                  <DragList
                    data={preferences.groceryCategories}
                    keyExtractor={(item, index) => `${item}-${index}`}
                    onReordered={onCategoriesReordered}
                    renderItem={renderCategoryItem}
                    scrollEnabled={false}
                  />
                </View>
              )}
              
              <TextInput
                ref={categoryInputRef}
                placeholder="Add custom category..."
                onSubmitEditing={(e) => {
                  addCustomItem('groceryCategories', e.nativeEvent.text);
                  categoryInputRef.current?.clear();
                }}
                style={{ marginTop: theme.spacing.md }}
              />
            </View>
          </ExpandableCard>

          {/* Recipe Preferences */}
          <ExpandableCard
            title="Recipe Preferences"
            subtitle={`${preferences.defaultServings} servings default`}
            icon="chef-hat"
            defaultExpanded={false}
          >
            <View style={{ gap: theme.spacing.lg }}>
              <View>
                <Text style={{
                  color: theme.colors.theme.text,
                  fontSize: theme.typography.fontSize.bodyLarge,
                  fontWeight: '600',
                  marginBottom: theme.spacing.sm,
                }}>
                  Default Servings: {preferences.defaultServings}
                </Text>
                <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
                  {[1, 2, 4, 6, 8].map(num => (
                    <TouchableOpacity
                      key={num}
                      style={{
                        paddingHorizontal: theme.spacing.md,
                        paddingVertical: theme.spacing.sm,
                        backgroundColor: preferences.defaultServings === num 
                          ? theme.colors.wizard.primary 
                          : theme.colors.theme.surface,
                        borderRadius: theme.borderRadius.md,
                        borderWidth: 1,
                        borderColor: preferences.defaultServings === num 
                          ? theme.colors.wizard.primary 
                          : theme.colors.theme.border,
                      }}
                      onPress={() => updatePreference('defaultServings', num)}
                    >
                      <Text style={{
                        color: preferences.defaultServings === num 
                          ? '#ffffff' 
                          : theme.colors.theme.text,
                        fontWeight: '600',
                      }}>
                        {num}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <View>
                <Text style={{
                  color: theme.colors.theme.text,
                  fontSize: theme.typography.fontSize.bodyLarge,
                  fontWeight: '600',
                  marginBottom: theme.spacing.sm,
                }}>
                  Preferred Difficulty
                </Text>
                <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
                  {(['easy', 'medium', 'hard'] as const).map(difficulty => (
                    <TouchableOpacity
                      key={difficulty}
                      style={{
                        paddingHorizontal: theme.spacing.md,
                        paddingVertical: theme.spacing.sm,
                        backgroundColor: preferences.preferredDifficulty === difficulty 
                          ? theme.colors.wizard.primary 
                          : theme.colors.theme.surface,
                        borderRadius: theme.borderRadius.md,
                        borderWidth: 1,
                        borderColor: preferences.preferredDifficulty === difficulty 
                          ? theme.colors.wizard.primary 
                          : theme.colors.theme.border,
                        flex: 1,
                        alignItems: 'center',
                      }}
                      onPress={() => updatePreference('preferredDifficulty', difficulty)}
                    >
                      <Text style={{
                        color: preferences.preferredDifficulty === difficulty 
                          ? '#ffffff' 
                          : theme.colors.theme.text,
                        fontWeight: '600',
                        textTransform: 'capitalize',
                      }}>
                        {difficulty}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            </View>
          </ExpandableCard>

          {/* Dietary Restrictions */}
          <ExpandableCard
            title="Dietary Restrictions"
            subtitle={preferences.dietaryRestrictions.length > 0 
              ? preferences.dietaryRestrictions.join(', ') 
              : 'None selected'
            }
            icon="food-apple"
            defaultExpanded={false}
          >
            <View>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium,
                marginBottom: theme.spacing.md,
              }}>
                Select all that apply to your diet
              </Text>
              
              {COMMON_DIETARY_RESTRICTIONS.map(restriction => (
                <CheckboxItem
                  key={restriction}
                  label={restriction.charAt(0).toUpperCase() + restriction.slice(1).replace('-', ' ')}
                  checked={preferences.dietaryRestrictions.includes(restriction)}
                  onPress={() => toggleArrayItem('dietaryRestrictions', restriction)}
                />
              ))}
              
              {preferences.dietaryRestrictions
                .filter(item => !COMMON_DIETARY_RESTRICTIONS.includes(item))
                .map(restriction => (
                  <View
                    key={restriction}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      paddingVertical: theme.spacing.sm,
                    }}
                  >
                    <CheckboxItem
                      label={restriction}
                      checked={true}
                      onPress={() => removeCustomItem('dietaryRestrictions', restriction)}
                      style={{ flex: 1 }}
                    />
                    <TouchableOpacity
                      onPress={() => removeCustomItem('dietaryRestrictions', restriction)}
                      style={{ padding: theme.spacing.xs, marginLeft: theme.spacing.sm }}
                    >
                      <MaterialCommunityIcons 
                        name="close-circle" 
                        size={20} 
                        color={theme.colors.status.error} 
                      />
                    </TouchableOpacity>
                  </View>
                ))}
              
              <TextInput
                ref={dietaryInputRef}
                placeholder="Add custom dietary restriction..."
                onSubmitEditing={(e) => {
                  addCustomItem('dietaryRestrictions', e.nativeEvent.text);
                  dietaryInputRef.current?.clear();
                }}
                style={{ marginTop: theme.spacing.md }}
              />
            </View>
          </ExpandableCard>

          {/* Allergens */}
          <ExpandableCard
            title="Allergens"
            subtitle={preferences.allergens.length > 0 
              ? preferences.allergens.join(', ') 
              : 'None selected'
            }
            icon="alert-circle"
            defaultExpanded={false}
          >
            <View>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium,
                marginBottom: theme.spacing.md,
              }}>
                Ingredients to avoid due to allergies
              </Text>
              
              {COMMON_ALLERGENS.map(allergen => (
                <CheckboxItem
                  key={allergen}
                  label={allergen.charAt(0).toUpperCase() + allergen.slice(1)}
                  checked={preferences.allergens.includes(allergen)}
                  onPress={() => toggleArrayItem('allergens', allergen)}
                />
              ))}
              
              {preferences.allergens
                .filter(item => !COMMON_ALLERGENS.includes(item))
                .map(allergen => (
                  <View
                    key={allergen}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      paddingVertical: theme.spacing.sm,
                    }}
                  >
                    <CheckboxItem
                      label={allergen}
                      checked={true}
                      onPress={() => removeCustomItem('allergens', allergen)}
                      style={{ flex: 1 }}
                    />
                    <TouchableOpacity
                      onPress={() => removeCustomItem('allergens', allergen)}
                      style={{ padding: theme.spacing.xs, marginLeft: theme.spacing.sm }}
                    >
                      <MaterialCommunityIcons 
                        name="close-circle" 
                        size={20} 
                        color={theme.colors.status.error} 
                      />
                    </TouchableOpacity>
                  </View>
                ))}
              
              <TextInput
                ref={allergenInputRef}
                placeholder="Add custom allergen..."
                onSubmitEditing={(e) => {
                  addCustomItem('allergens', e.nativeEvent.text);
                  allergenInputRef.current?.clear();
                }}
                style={{ marginTop: theme.spacing.md }}
              />
            </View>
          </ExpandableCard>

          {/* Additional Preferences */}
          <ExpandableCard
            title="Additional Preferences"
            subtitle={preferences.additionalPreferences ? 
              preferences.additionalPreferences.substring(0, 50) + '...' : 
              'Add custom instructions'
            }
            icon="text-box"
            defaultExpanded={false}
          >
            <View>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium,
                marginBottom: theme.spacing.md,
              }}>
                Add any additional preferences, cooking styles, or instructions for the AI
              </Text>
              
              <TextInput
                placeholder="e.g., I prefer one-pot meals, low sodium recipes, or Mediterranean flavors..."
                value={preferences.additionalPreferences}
                onChangeText={(text) => updatePreference('additionalPreferences', text)}
                multiline
                numberOfLines={4}
                textAlignVertical="top"
                style={{ 
                  height: 120,
                  paddingTop: theme.spacing.md,
                }}
              />
              
              <Text style={{
                color: theme.colors.theme.textTertiary,
                fontSize: theme.typography.fontSize.bodySmall,
                marginTop: theme.spacing.sm,
                fontStyle: 'italic',
              }}>
                These preferences will be included in every recipe generation to personalize your results
              </Text>
            </View>
          </ExpandableCard>

          {/* Auto-save Status */}
          <View style={{
            marginTop: theme.spacing.lg,
            alignItems: 'center',
            paddingVertical: theme.spacing.sm,
          }}>
            {autoSaving ? (
              <View style={{
                flexDirection: 'row',
                alignItems: 'center',
                opacity: 0.7,
              }}>
                <MaterialCommunityIcons
                  name="loading"
                  size={16}
                  color={theme.colors.wizard.primary}
                  style={{
                    marginRight: theme.spacing.sm,
                    transform: [{ rotate: autoSaving ? '360deg' : '0deg' }]
                  }}
                />
                <Text style={{
                  fontSize: theme.typography.fontSize.bodySmall,
                  color: theme.colors.theme.textSecondary,
                  fontWeight: theme.typography.fontWeight.medium,
                }}>
                  Saving preferences...
                </Text>
              </View>
            ) : lastSaved && (
              <View style={{
                flexDirection: 'row',
                alignItems: 'center',
                opacity: 0.6,
              }}>
                <MaterialCommunityIcons
                  name="check-circle"
                  size={16}
                  color={theme.colors.status.success}
                  style={{ marginRight: theme.spacing.sm }}
                />
                <Text style={{
                  fontSize: theme.typography.fontSize.bodySmall,
                  color: theme.colors.theme.textSecondary,
                }}>
                  Preferences saved automatically
                </Text>
              </View>
            )}
          </View>

          {/* Premium Status */}
          <ExpandableCard
            title="Premium Status"
            subtitle={isPremium ? 'Premium Active' : 'Free Plan'}
            icon={isPremium ? "crown" : "crown-outline"}
            defaultExpanded={false}
          >
            <View style={{ gap: theme.spacing.lg }}>
              {/* Premium Benefits List */}
              <View>
                <Text style={{
                  fontSize: theme.typography.fontSize.bodyMedium,
                  fontWeight: theme.typography.fontWeight.medium,
                  color: theme.colors.theme.text,
                  marginBottom: theme.spacing.md,
                }}>
                  Premium Features:
                </Text>

                {[
                  {
                    icon: 'lightbulb',
                    title: 'AI Recipe Ideas',
                    description: 'Get personalized recipe suggestions based on your preferences'
                  },
                  {
                    icon: 'cart',
                    title: 'Smart Shopping Lists',
                    description: 'Organized grocery lists with categories and checkboxes'
                  },
                  {
                    icon: 'history',
                    title: 'Complete Recipe History',
                    description: 'Access all your previous recipes and cooking history'
                  },
                  {
                    icon: 'pencil',
                    title: 'Recipe Modification',
                    description: 'Edit and customize recipes to match your taste'
                  }
                ].map((benefit, index) => (
                  <View
                    key={index}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      paddingVertical: theme.spacing.sm,
                      paddingHorizontal: theme.spacing.md,
                      backgroundColor: isPremium
                        ? theme.colors.wizard.primary + '10'
                        : theme.colors.theme.surface + '80',
                      borderRadius: theme.borderRadius.md,
                      marginBottom: theme.spacing.sm,
                      opacity: isPremium ? 1 : 0.7,
                    }}
                  >
                    <MaterialCommunityIcons
                      name={benefit.icon as any}
                      size={20}
                      color={isPremium
                        ? theme.colors.wizard.primary
                        : theme.colors.theme.textSecondary
                      }
                      style={{ marginRight: theme.spacing.md }}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={{
                        fontSize: theme.typography.fontSize.bodyMedium,
                        fontWeight: theme.typography.fontWeight.medium,
                        color: isPremium
                          ? theme.colors.theme.text
                          : theme.colors.theme.textSecondary,
                        marginBottom: theme.spacing.xs,
                      }}>
                        {benefit.title}
                      </Text>
                      <Text style={{
                        fontSize: theme.typography.fontSize.bodySmall,
                        color: theme.colors.theme.textTertiary,
                        lineHeight: 18,
                      }}>
                        {benefit.description}
                      </Text>
                    </View>
                    {isPremium && (
                      <MaterialCommunityIcons
                        name="check-circle"
                        size={16}
                        color={theme.colors.status.success}
                        style={{ marginLeft: theme.spacing.sm }}
                      />
                    )}
                  </View>
                ))}
              </View>

              {/* Subscription Management */}
              <View style={{ gap: theme.spacing.md }}>
                <TouchableOpacity
                  onPress={() => router.push('/subscription/manage')}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    padding: theme.spacing.md,
                    backgroundColor: theme.colors.theme.surface,
                    borderRadius: theme.borderRadius.lg,
                    borderWidth: 1,
                    borderColor: theme.colors.theme.border,
                  }}
                >
                  <View style={{ flexDirection: 'row', alignItems: 'center', flex: 1 }}>
                    <MaterialCommunityIcons
                      name="cog"
                      size={20}
                      color={theme.colors.theme.textSecondary}
                      style={{ marginRight: theme.spacing.md }}
                    />
                    <View style={{ flex: 1 }}>
                      <Text style={{
                        fontSize: theme.typography.fontSize.bodyMedium,
                        fontWeight: theme.typography.fontWeight.medium,
                        color: theme.colors.theme.text,
                        marginBottom: theme.spacing.xs,
                      }}>
                        Manage Subscription
                      </Text>
                      <Text style={{
                        fontSize: theme.typography.fontSize.bodySmall,
                        color: theme.colors.theme.textSecondary,
                      }}>
                        {isPremium ? 'View billing, change plan, or cancel' : 'View available premium plans'}
                      </Text>
                    </View>
                  </View>
                  <MaterialCommunityIcons
                    name="chevron-right"
                    size={20}
                    color={theme.colors.theme.textTertiary}
                  />
                </TouchableOpacity>

                {!isPremium && (
                  <TouchableOpacity
                    onPress={() => router.push('/subscription/plans')}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'center',
                      padding: theme.spacing.md,
                      backgroundColor: theme.colors.wizard.primary,
                      borderRadius: theme.borderRadius.lg,
                    }}
                  >
                    <MaterialCommunityIcons
                      name="crown"
                      size={20}
                      color="#ffffff"
                      style={{ marginRight: theme.spacing.sm }}
                    />
                    <Text style={{
                      fontSize: theme.typography.fontSize.bodyLarge,
                      fontWeight: theme.typography.fontWeight.semibold,
                      color: '#ffffff',
                    }}>
                      Upgrade to Premium
                    </Text>
                  </TouchableOpacity>
                )}
              </View>

              {/* Development Notice */}
              <View style={{
                padding: theme.spacing.md,
                backgroundColor: theme.colors.theme.surface,
                borderRadius: theme.borderRadius.lg,
                borderWidth: 1,
                borderColor: theme.colors.theme.border,
              }}>
                <Text style={{
                  fontSize: theme.typography.fontSize.bodySmall,
                  color: theme.colors.theme.textSecondary,
                  fontStyle: 'italic',
                  textAlign: 'center',
                  lineHeight: 18,
                }}>
                  Development Mode: This toggle allows testing premium features. In production, premium status will be managed through in-app purchases.
                </Text>
              </View>
            </View>
          </ExpandableCard>

          {/* Account Section */}
          <ExpandableCard
            title="Account"
            subtitle={user?.email || 'Guest'}
            icon="account"
            defaultExpanded={false}
            style={{ marginTop: theme.spacing.lg }}
          >
            <View>
              {user ? (
                <View style={{ marginBottom: theme.spacing.lg }}>
                  <Text style={{
                    color: theme.colors.theme.textSecondary,
                    fontSize: theme.typography.fontSize.bodyMedium,
                    marginBottom: theme.spacing.sm,
                  }}>
                    Signed in as:
                  </Text>
                  <Text style={{
                    color: theme.colors.theme.text,
                    fontSize: theme.typography.fontSize.bodyLarge,
                    fontWeight: '600',
                    marginBottom: theme.spacing.xs,
                  }}>
                    {user.firstName && user.lastName ? `${user.firstName} ${user.lastName}` : user.username || 'User'}
                  </Text>
                  <Text style={{
                    color: theme.colors.theme.textSecondary,
                    fontSize: theme.typography.fontSize.bodyMedium,
                  }}>
                    {user.email}
                  </Text>
                </View>
              ) : (
                <View style={{ marginBottom: theme.spacing.lg }}>
                  <Text style={{
                    color: theme.colors.theme.textSecondary,
                    fontSize: theme.typography.fontSize.bodyMedium,
                    marginBottom: theme.spacing.lg,
                    lineHeight: 20,
                  }}>
                    You're using Recipe Wizard as a guest. Create an account to save your recipes permanently, unlock premium features, and sync across devices.
                  </Text>
                  <Button
                    onPress={() => router.push('/auth/signup')}
                    variant="primary"
                    leftIcon="account-plus"
                    style={{ marginBottom: theme.spacing.md }}
                  >
                    Create an Account
                  </Button>
                  <Button
                    onPress={() => router.push('/auth/signin')}
                    variant="outline"
                    leftIcon="login"
                  >
                    Sign In
                  </Button>
                </View>
              )}

              {user && (
                <Button
                  onPress={handleSignOut}
                  variant="outline"
                  disabled={signingOut || deletingAccount}
                  loading={signingOut}
                  leftIcon="logout"
                  style={{
                    borderColor: theme.colors.status.error,
                  }}
                  textStyle={{
                    color: theme.colors.status.error,
                  }}
                >
                  {signingOut ? "Signing Out..." : "Sign Out"}
                </Button>
              )}

              {user && (
                <View style={{ marginTop: theme.spacing['2xl'] }}>
                  <View
                    style={{
                      height: 1,
                      backgroundColor: theme.colors.theme.border,
                      marginBottom: theme.spacing.lg,
                    }}
                  />
                  <Text
                    style={{
                      fontSize: theme.typography.fontSize.bodySmall,
                      color: theme.colors.theme.textTertiary,
                      marginBottom: theme.spacing.md,
                      lineHeight: 18,
                    }}
                  >
                    Danger zone. Deleting your account permanently removes your recipes, shopping list, preferences and history. This cannot be undone.
                  </Text>
                  <Button
                    onPress={handleDeleteAccount}
                    variant="outline"
                    disabled={signingOut || deletingAccount}
                    loading={deletingAccount}
                    leftIcon="delete-forever"
                    style={{
                      borderColor: theme.colors.status.error,
                      backgroundColor: theme.colors.status.error + '10',
                    }}
                    textStyle={{
                      color: theme.colors.status.error,
                    }}
                  >
                    {deletingAccount ? 'Deleting account...' : 'Delete Account'}
                  </Button>
                </View>
              )}
            </View>
          </ExpandableCard>

          <View style={{ marginBottom: theme.spacing['2xl'] }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
