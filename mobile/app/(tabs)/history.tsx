import React, { useState, useEffect } from 'react';
import { View, Text, StatusBar, Platform, KeyboardAvoidingView, ScrollView, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useFocusEffect } from '@react-navigation/native';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useAppTheme } from '../../constants/ThemeProvider';
import { useAuth } from '../../contexts/AuthContext';
import { SavedRecipeData } from '../../types/api';
import { apiService } from '../../services/api';
import { GuestRecipesService } from '../../services/guestRecipes';
import { SavedRecipesSection } from '../../components/SavedRecipesSection';
import { AllHistorySection } from '../../components/AllHistorySection';
import { HeaderComponent } from '../../components/HeaderComponent';
import { PremiumBadge } from '../../components/PremiumBadge';

export default function HistoryScreen() {
  const { theme, isDark } = useAppTheme();
  const router = useRouter();
  const { isAuthenticated, justSignedOut } = useAuth();

  const [savedRecipes, setSavedRecipes] = useState<SavedRecipeData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [bannerDismissed, setBannerDismissed] = useState(false);

  // Load saved recipes function
  const loadSavedRecipes = async () => {
    try {
      setIsLoading(true);

      if (isAuthenticated) {
        const recipes = await apiService.getSavedRecipes();
        setSavedRecipes(recipes || []);
      } else {
        const guestRecipes = await GuestRecipesService.getAll();
        setSavedRecipes(
          guestRecipes.map(recipe => ({
            ...recipe,
            id: recipe.localId,
            savedAt: recipe.createdAt,
            isFavorite: true,
          }))
        );
      }

      setError(null);
    } catch (error) {
      console.error('Error loading saved recipes:', error);
      setError('Failed to load saved recipes');
      setSavedRecipes([]);
    } finally {
      setIsLoading(false);
    }
  };

  // Load on component mount
  useEffect(() => {
    loadSavedRecipes();
  }, [isAuthenticated]);

  // Also reload whenever the screen gains focus
  useFocusEffect(
    React.useCallback(() => {
      loadSavedRecipes();
      setBannerDismissed(false);
    }, [isAuthenticated])
  );

  const handleDeleteRecipe = async (recipeId: string) => {
    try {
      if (isAuthenticated) {
        await apiService.unsaveRecipe(recipeId);
      } else {
        await GuestRecipesService.remove(recipeId);
      }
      setSavedRecipes(prev => prev.filter(recipe => recipe.id !== recipeId));
    } catch (error) {
      console.error('Error removing saved recipe:', error);
      // Could add error toast here
    }
  };

  // Loading screen
  if (isLoading) {
    return (
      <>
        <StatusBar
          barStyle={isDark ? 'light-content' : 'dark-content'}
          backgroundColor={theme.colors.theme.background}
          translucent
        />
        <SafeAreaView
          style={{
            flex: 1,
            backgroundColor: theme.colors.theme.background,
          }}
          edges={['top']}
        >
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <MaterialCommunityIcons
              name="book-open-variant"
              size={64}
              color={theme.colors.wizard.primary}
              style={{ marginBottom: 16 }}
            />
            <Text
              style={{
                fontSize: theme.typography.fontSize.headlineSmall,
                fontWeight: theme.typography.fontWeight.semibold,
                color: theme.colors.theme.text,
                marginBottom: 8,
              }}
            >
              Loading Recipe History
            </Text>
            <Text
              style={{
                fontSize: theme.typography.fontSize.bodyMedium,
                color: theme.colors.theme.textSecondary,
                textAlign: 'center',
              }}
            >
              Gathering your saved recipes...
            </Text>
          </View>
        </SafeAreaView>
      </>
    );
  }

  return (
    <>
      <StatusBar
        barStyle={isDark ? 'light-content' : 'dark-content'}
        backgroundColor={theme.colors.theme.background}
        translucent
      />

      <SafeAreaView
        style={{
          flex: 1,
          backgroundColor: theme.colors.theme.background,
        }}
        edges={['top']}
      >
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={{ flex: 1 }}
          keyboardVerticalOffset={0}
        >
          <HeaderComponent
            title="Recipe History"
            subtitle="Your saved recipes and cooking history"
            rightContent={<PremiumBadge size="small" />}
          />

          {/* Content */}
          <ScrollView
            style={{ flex: 1 }}
            contentContainerStyle={{
              paddingHorizontal: theme.spacing.xl,
              paddingTop: theme.spacing.xl,
              paddingBottom: theme.spacing.xl,
              gap: theme.spacing.xl,
            }}
            showsVerticalScrollIndicator={false}
          >
            {!isAuthenticated && !bannerDismissed && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: theme.colors.wizard.primary + '15',
                  borderRadius: theme.borderRadius.xl,
                  padding: theme.spacing.lg,
                }}
              >
                <MaterialCommunityIcons
                  name={justSignedOut ? 'logout' : 'account-plus'}
                  size={24}
                  color={theme.colors.wizard.primary}
                  style={{ marginRight: theme.spacing.md }}
                />
                <View style={{ flex: 1 }}>
                  <Text
                    style={{
                      fontSize: theme.typography.fontSize.bodyMedium,
                      color: theme.colors.theme.text,
                      fontFamily: theme.typography.fontFamily.body,
                      fontWeight: theme.typography.fontWeight.medium,
                      marginBottom: theme.spacing.sm,
                    }}
                  >
                    {justSignedOut
                      ? "You're signed out — sign back in to see your saved recipes."
                      : 'Sign in to save your recipes permanently'}
                  </Text>
                  <TouchableOpacity onPress={() => router.push(justSignedOut ? '/auth/signin' : '/auth/signup')}>
                    <Text
                      style={{
                        fontSize: theme.typography.fontSize.bodySmall,
                        color: theme.colors.wizard.primary,
                        fontFamily: theme.typography.fontFamily.body,
                        fontWeight: theme.typography.fontWeight.semibold,
                      }}
                    >
                      {justSignedOut ? 'Sign In' : 'Create Account'}
                    </Text>
                  </TouchableOpacity>
                </View>
                <TouchableOpacity onPress={() => setBannerDismissed(true)} hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}>
                  <MaterialCommunityIcons name="close" size={18} color={theme.colors.theme.textSecondary} />
                </TouchableOpacity>
              </View>
            )}

            {/* Saved Recipes Section */}
            <SavedRecipesSection
              savedRecipes={savedRecipes}
              onDeleteRecipe={handleDeleteRecipe}
              isLoading={isLoading}
              error={error}
            />

            {/* All History Section (server-side pagination — signed-in users only) */}
            {isAuthenticated && <AllHistorySection />}
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </>
  );
}
