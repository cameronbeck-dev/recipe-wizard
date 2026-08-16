import React, { useEffect, useMemo, useState, useRef } from 'react';
import { View, Text, ScrollView, StatusBar, TouchableOpacity, Platform, KeyboardAvoidingView, Animated } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Portal, Dialog, Button as PaperButton } from 'react-native-paper';
import { useRouter } from 'expo-router';
import { Button, TextInput, useAppTheme, ExpandableCard, PillSlider, PillSliderOption } from '../../components';
import { PremiumFeature } from '../../components/PremiumFeature';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { apiService, GuestGenerationError } from '../../services/api';
import { RecipeIdeasResponse } from '../../types/api';
import { PreferencesService } from '../../services/preferences';
import { UserPreferences } from '../../types/api';
import { useAuth } from '../../contexts/AuthContext';
import { useToast } from '../../contexts/ToastContext';
import { GuestRecipesService } from '../../services/guestRecipes';
import {
  getRandomHeroSubtitle,
  getRandomHeroTitle,
  getRandomSuggestion,
  getRandomSuggestions,
  getRandomLoadingButtonText,
  getRandomIdeaLoadingButtonText,
} from '../../constants/copy';

// Mirrors the backend's default GUEST_WEEKLY_LIMIT (see CLAUDE.md) — the
// job-creation response only tells us how many generations remain, not the
// configured total, so this is used purely for display.
const GUEST_WEEKLY_LIMIT = 10;

function formatResetIn(resetAt: string | null): string {
  if (!resetAt) return 'soon';
  const diffMs = new Date(resetAt).getTime() - Date.now();
  if (diffMs <= 0) return 'soon';
  const days = Math.floor(diffMs / (24 * 60 * 60 * 1000));
  const hours = Math.floor((diffMs % (24 * 60 * 60 * 1000)) / (60 * 60 * 1000));
  if (days >= 1) return `in ${days} day${days === 1 ? '' : 's'}`;
  if (hours >= 1) return `in ${hours} hour${hours === 1 ? '' : 's'}`;
  return 'in less than an hour';
}

export default function PromptScreen() {
  const { theme, isDark, setThemeMode, themeMode } = useAppTheme();
  const router = useRouter();
  const { isAuthenticated } = useAuth();
  const toast = useToast();

  const [prompt, setPrompt] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Guest quota state (only populated for unauthenticated requests)
  const [guestGenerationsRemaining, setGuestGenerationsRemaining] = useState<number | null>(null);
  const [guestQuotaResetAt, setGuestQuotaResetAt] = useState<string | null>(null);
  const [quotaExceededDialogVisible, setQuotaExceededDialogVisible] = useState(false);

  // Recipe Ideas Generation State
  const [sliderMode, setSliderMode] = useState<'preset' | 'generate'>('preset');
  const [generatedIdeas, setGeneratedIdeas] = useState<Array<{id: string; title: string; description: string}>>([]);
  const [isGeneratingIdeas, setIsGeneratingIdeas] = useState(false);
  const [ideasGenerationError, setIdeasGenerationError] = useState<string | null>(null);
  const [generateIdeasPrompt, setGenerateIdeasPrompt] = useState('');
  const [lastGeneratedPrompt, setLastGeneratedPrompt] = useState(''); // Track what prompt was used for generation
  const [generateIdeasButtonText, setGenerateIdeasButtonText] = useState('Generate Ideas');
  const [ideasGenerationAttempt, setIdeasGenerationAttempt] = useState(1);
  const [ideasSegmentProgress, setIdeasSegmentProgress] = useState(0);
  const [ideasAttemptStartTime, setIdeasAttemptStartTime] = useState<number | null>(null);
  const [isIdeasInErrorState, setIsIdeasInErrorState] = useState(false);
  const ideasProgressAnimation = useRef(new Animated.Value(0)).current;
  const ideasTextCyclingInterval = useRef<NodeJS.Timeout | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);
  const mainInputRef = useRef<View>(null);
  const [servings, setServings] = useState<number>(4);
  const [difficulty, setDifficulty] = useState<'easy' | 'medium' | 'hard' | undefined>(undefined);
  
  // Progress visualization state
  const [currentAttempt, setCurrentAttempt] = useState(1); // 1, 2, or 3
  const [segmentProgress, setSegmentProgress] = useState(0); // 0-1 progress within current segment  
  const [currentButtonText, setCurrentButtonText] = useState('Generate Recipe');
  const [attemptStartTime, setAttemptStartTime] = useState<number | null>(null);
  const [isInErrorState, setIsInErrorState] = useState(false);
  const progressAnimation = useRef(new Animated.Value(0)).current;
  const textCyclingInterval = useRef<NodeJS.Timeout | null>(null);

  // Initialize per-recipe overrides from saved preferences
  useEffect(() => {
    (async () => {
      const prefs: UserPreferences = await PreferencesService.loadPreferences();
      setServings(prefs.defaultServings || 4);
      setDifficulty(prefs.preferredDifficulty);
    })();
  }, []);

  // Cycle button text every 3 seconds during loading
  useEffect(() => {
    // Clear any existing interval
    if (textCyclingInterval.current) {
      clearInterval(textCyclingInterval.current);
      textCyclingInterval.current = null;
    }

    if (!isLoading || isInErrorState) return;

    textCyclingInterval.current = setInterval(() => {
      // Only cycle text if still loading and not in error state
      if (isLoading && !isInErrorState) {
        setCurrentButtonText(getRandomLoadingButtonText());
      }
    }, 3000);

    return () => {
      if (textCyclingInterval.current) {
        clearInterval(textCyclingInterval.current);
        textCyclingInterval.current = null;
      }
    };
  }, [isLoading, isInErrorState]);

  // Ideas progress animation within current segment (2-segment progress)
  useEffect(() => {
    if (!isGeneratingIdeas || !ideasAttemptStartTime) return;

    const interval = setInterval(() => {
      const elapsed = Date.now() - ideasAttemptStartTime;
      const maxTime = 15000; // 15 seconds max per attempt
      const progress = Math.min(elapsed / maxTime, 1);
      
      setIdeasSegmentProgress(progress);
    }, 100); // Update every 100ms for smooth animation

    return () => clearInterval(interval);
  }, [isGeneratingIdeas, ideasAttemptStartTime]);

  // Calculate total progress for ideas (2 segments) and animate
  const updateIdeasProgressAnimation = () => {
    const completedSegments = ideasGenerationAttempt - 1;
    const currentSegmentProgress = ideasSegmentProgress / 2; // Each segment is 1/2 of total
    const totalProgress = (completedSegments / 2) + currentSegmentProgress;
    
    Animated.timing(ideasProgressAnimation, {
      toValue: totalProgress,
      duration: 300, // 0.3 second smooth transition
      useNativeDriver: false, // Width animations require false
    }).start();
  };

  // Update ideas animation when progress changes
  useEffect(() => {
    if (isGeneratingIdeas) {
      updateIdeasProgressAnimation();
    } else {
      ideasProgressAnimation.setValue(0);
    }
  }, [ideasGenerationAttempt, ideasSegmentProgress, isGeneratingIdeas]);

  // Reset ideas progress state when loading starts/stops
  useEffect(() => {
    if (isGeneratingIdeas) {
      setIdeasGenerationAttempt(1);
      setIdeasSegmentProgress(0);
      setIdeasAttemptStartTime(Date.now());
      setIsIdeasInErrorState(false);
    } else {
      setIdeasGenerationAttempt(1);
      setIdeasSegmentProgress(0);
      setIdeasAttemptStartTime(null);
    }
  }, [isGeneratingIdeas]);

  // Cycle ideas button text every 3 seconds during loading
  useEffect(() => {
    // Clear any existing interval
    if (ideasTextCyclingInterval.current) {
      clearInterval(ideasTextCyclingInterval.current);
      ideasTextCyclingInterval.current = null;
    }

    if (!isGeneratingIdeas || isIdeasInErrorState) return;

    ideasTextCyclingInterval.current = setInterval(() => {
      // Only cycle text if still loading and not in error state
      if (isGeneratingIdeas && !isIdeasInErrorState) {
        setGenerateIdeasButtonText(getRandomIdeaLoadingButtonText());
      }
    }, 3000);

    return () => {
      if (ideasTextCyclingInterval.current) {
        clearInterval(ideasTextCyclingInterval.current);
        ideasTextCyclingInterval.current = null;
      }
    };
  }, [isGeneratingIdeas, isIdeasInErrorState]);

  // Progress animation within current segment
  useEffect(() => {
    if (!isLoading || !attemptStartTime) return;

    const interval = setInterval(() => {
      const elapsed = Date.now() - attemptStartTime;
      const maxTime = 20000; // 20 seconds max per attempt
      const progress = Math.min(elapsed / maxTime, 1);
      
      setSegmentProgress(progress);
    }, 100); // Update every 100ms for smooth animation

    return () => clearInterval(interval);
  }, [isLoading, attemptStartTime]);

  // Reset progress state when loading starts/stops
  useEffect(() => {
    if (isLoading) {
      setCurrentAttempt(1);
      setSegmentProgress(0);
      setAttemptStartTime(Date.now());
      setCurrentButtonText(getRandomLoadingButtonText());
      setIsInErrorState(false); // Clear error state when starting new request
    } else {
      setCurrentAttempt(1);
      setSegmentProgress(0);
      setAttemptStartTime(null);
      // Don't automatically reset button text - let success/error handlers do it
    }
  }, [isLoading]);

  // Utility function to advance to next attempt
  const advanceToNextAttempt = () => {
    setCurrentAttempt(prev => Math.min(prev + 1, 3));
    setSegmentProgress(0);
    setAttemptStartTime(Date.now());
  };

  // Calculate total progress across all segments and animate
  const updateProgressAnimation = () => {
    const completedSegments = currentAttempt - 1;
    const currentSegmentProgress = segmentProgress / 3; // Each segment is 1/3 of total
    const totalProgress = (completedSegments / 3) + currentSegmentProgress;
    
    Animated.timing(progressAnimation, {
      toValue: totalProgress,
      duration: 300, // 0.3 second smooth transition
      useNativeDriver: false, // Width animations require false
    }).start();
  };

  // Update animation when progress changes
  useEffect(() => {
    if (isLoading) {
      updateProgressAnimation();
    } else {
      progressAnimation.setValue(0);
    }
  }, [currentAttempt, segmentProgress, isLoading]);

  const handleCreateRecipe = async () => {
    if (!prompt.trim()) {
      setCurrentButtonText('Please enter a recipe description');
      setTimeout(() => setCurrentButtonText('Generate Recipe'), 3000);
      return;
    }

    setIsLoading(true);

    try {
      // Start async job
      // console.log('Creating recipe with prompt:', prompt);
      const jobResponse = await apiService.startRecipeGeneration({
        prompt,
        overrides: {
          defaultServings: servings,
          preferredDifficulty: difficulty,
        },
      });

      if (jobResponse.guest_generations_remaining !== undefined) {
        setGuestGenerationsRemaining(jobResponse.guest_generations_remaining);
        setGuestQuotaResetAt(jobResponse.guest_quota_reset_at ?? null);
      }

      // console.log('🚀 Job started:', jobResponse.job_id);

      // Poll job until completion with attempt tracking
      const recipeData = await apiService.pollJobUntilComplete(
        jobResponse.job_id,
        (status) => {
          // Track attempts based on retry_count in status
          if (status.retry_count !== undefined) {
            const newAttempt = Math.min(status.retry_count + 1, 3);
            if (newAttempt > currentAttempt) {
              advanceToNextAttempt();
            }
          }
        }
      );

      // The backend keeps no history for guests — this is the only place a
      // guest's generated recipe survives past this screen.
      if (!isAuthenticated) {
        GuestRecipesService.add(recipeData).catch(() => {});
      }

      // Success animation - quickly fill all remaining segments
      setCurrentAttempt(3);
      setSegmentProgress(1);

      // Wait for success animation, then navigate
      setTimeout(() => {
        setIsLoading(false);
        setCurrentButtonText('Generate Recipe'); // Reset on success

        // Navigate with the recipe data
        router.push({
          pathname: '/recipe-result',
          params: {
            userPrompt: prompt,
            recipeData: JSON.stringify(recipeData),
            timestamp: Date.now().toString()
          }
        });
      }, 300); // 0.3 second success animation

    } catch (error) {
      console.error('Recipe generation error:', error);

      // IMMEDIATELY stop text cycling to prevent race condition
      if (textCyclingInterval.current) {
        clearInterval(textCyclingInterval.current);
        textCyclingInterval.current = null;
      }

      if (error instanceof GuestGenerationError && error.code === 'GUEST_QUOTA_EXCEEDED') {
        setGuestGenerationsRemaining(0);
        setGuestQuotaResetAt(error.resetAt ?? null);
        setQuotaExceededDialogVisible(true);
        setIsLoading(false);
        setCurrentButtonText('Generate Recipe');
        setCurrentAttempt(1);
        setSegmentProgress(0);
        return;
      }

      if (error instanceof GuestGenerationError && error.code === 'GUEST_MODE_UNAVAILABLE') {
        toast.show('Guest generation is temporarily unavailable. Please sign in or try again shortly.', {
          variant: 'error',
        });
        setIsLoading(false);
        setCurrentButtonText('Generate Recipe');
        setCurrentAttempt(1);
        setSegmentProgress(0);
        return;
      }

      setIsLoading(false);
      setIsInErrorState(true);

      // Show error in button for retry
      if (error instanceof Error) {
        setCurrentButtonText(error.message);
      } else {
        setCurrentButtonText('Something went wrong. Tap to retry.');
      }

      // Reset progress to show error state
      setCurrentAttempt(1);
      setSegmentProgress(0);
    }
  };


  // Fresh randomized copy and suggestions per mount
  const [heroTitle, setHeroTitle] = useState<string>('What shall we cook today?');
  const [heroSubtitle, setHeroSubtitle] = useState<string>(
    "Tell me what you're craving and I'll create the perfect recipe for you ✨"
  );
  const [placeholder, setPlaceholder] = useState<string>('');
  const [suggestionPrompts, setSuggestionPrompts] = useState<
    { text: string; icon: keyof typeof MaterialCommunityIcons.glyphMap }[]
  >([]);

  const suggestionIcons = useMemo<
    ReadonlyArray<keyof typeof MaterialCommunityIcons.glyphMap>
  >(() => (
    ['lightbulb-on', 'chef-hat', 'bowl-mix', 'food-variant', 'silverware-fork-knife', 'fire', 'leaf', 'cookie']
  ), []);

  const refreshDynamicCopy = () => {
    setHeroTitle(getRandomHeroTitle());
    setHeroSubtitle(getRandomHeroSubtitle());

    const texts = getRandomSuggestions(8);
    const items = texts.map((t, idx) => ({
      text: t,
      icon: suggestionIcons[idx % suggestionIcons.length],
    }));
    setSuggestionPrompts(items);

    setPlaceholder(texts[Math.floor(Math.random() * texts.length)] || getRandomSuggestion());
  };

  useEffect(() => {
    refreshDynamicCopy();
  }, [suggestionIcons]);

  const handleSuggestionPress = (suggestion: string) => {
    setPrompt(suggestion);
  };

  // Pill slider options
  const sliderOptions: [PillSliderOption, PillSliderOption] = [
    { label: 'Preset', value: 'preset' },
    { label: 'Generate', value: 'generate' }
  ];

  const handleSliderChange = (value: string) => {
    setSliderMode(value as 'preset' | 'generate');
    // Reset ideas state when switching modes
    if (value === 'preset') {
      setGeneratedIdeas([]);
      setGenerateIdeasPrompt('');
      setLastGeneratedPrompt('');
      setIsGeneratingIdeas(false);
      setIdeasGenerationError(null);
      setIsIdeasInErrorState(false);
      setGenerateIdeasButtonText('Generate Ideas');
    }
  };

  const handleGenerateIdeas = async () => {
    // Check if this is a refresh action (button shows 'Refresh Ideas')
    const isRefreshAction = generateIdeasButtonText === 'Refresh Ideas';
    
    if (!generateIdeasPrompt.trim() && !isRefreshAction) {
      setGenerateIdeasButtonText('Please enter an idea prompt');
      setTimeout(() => setGenerateIdeasButtonText('Generate Ideas'), 3000);
      return;
    }

    setIsGeneratingIdeas(true);
    setGenerateIdeasButtonText(getRandomIdeaLoadingButtonText());
    
    try {
      // IMMEDIATELY clear text cycling interval to prevent race condition
      if (ideasTextCyclingInterval.current) {
        clearInterval(ideasTextCyclingInterval.current);
        ideasTextCyclingInterval.current = null;
      }

      // Call the real API
      const response: RecipeIdeasResponse = await apiService.generateRecipeIdeas({
        prompt: generateIdeasPrompt,
        count: 5
      });
      
      // console.log('🎯 Received recipe ideas:', response.ideas.length);
      
      // Success animation - fill remaining progress
      setIdeasGenerationAttempt(2);
      setIdeasSegmentProgress(1);
      
      // Wait for success animation, then show results
      setTimeout(() => {
        setGeneratedIdeas(response.ideas);
        // Store the prompt that was used for generation
        setLastGeneratedPrompt(generateIdeasPrompt);
        // Button should show 'Refresh Ideas' after successful generation
        setGenerateIdeasButtonText('Refresh Ideas');
      }, 300);
      
    } catch (error) {
      console.error('Ideas generation error:', error);
      
      // IMMEDIATELY stop text cycling to prevent race condition
      if (ideasTextCyclingInterval.current) {
        clearInterval(ideasTextCyclingInterval.current);
        ideasTextCyclingInterval.current = null;
      }
      
      setIsIdeasInErrorState(true);
      setIdeasGenerationError('Failed to generate ideas');
      setGenerateIdeasButtonText('Failed to generate ideas. Tap to retry.');
      
    } finally {
      setTimeout(() => {
        setIsGeneratingIdeas(false);
      }, 300); // Wait for animation before clearing loading state
    }
  };

  const handleIdeaPress = (idea: {title: string; description: string}) => {
    // Populate main prompt with the selected idea
    setPrompt(`${idea.title}: ${idea.description}`);
    
    // Scroll to main input after a short delay to allow state update
    setTimeout(() => {
      scrollToMainInput();
    }, 100);
  };

  const scrollToMainInput = () => {
    if (mainInputRef.current && scrollViewRef.current) {
      mainInputRef.current.measureLayout(
        scrollViewRef.current as any,
        (x, y) => {
          scrollViewRef.current?.scrollTo({
            y: y - 100, // Offset to show some space above the input
            animated: true,
          });
        },
        () => {
          // console.log('Failed to measure main input position');
        }
      );
    }
  };

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
          style={{ flex: 1 }}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 20}
        >
          <ScrollView
            ref={scrollViewRef}
            contentContainerStyle={{
              paddingHorizontal: theme.spacing.xl,
              paddingTop: theme.spacing.xl,
              paddingBottom: theme.spacing.xl,
            }}
            style={{ flex: 1 }}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            keyboardDismissMode="interactive"
            contentInsetAdjustmentBehavior="automatic"
          >
          {/* Hero Section */}
          <View
            style={{
              alignItems: 'center',
              marginBottom: theme.spacing['4xl'],
            }}
          >
            {/* Magical Circle with Chef Hat */}
            <View
              style={{
                width: 140,
                height: 140,
                borderRadius: 70,
                backgroundColor: theme.colors.wizard.primary + '15',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: theme.spacing['2xl'],
                position: 'relative',
              }}
            >
              {/* Animated sparkles around the circle */}
              <View
                style={{
                  position: 'absolute',
                  top: 10,
                  right: 20,
                }}
              >
                <MaterialCommunityIcons
                  name="star-four-points"
                  size={16}
                  color={theme.colors.wizard.accent}
                  style={{ opacity: 0.7 }}
                />
              </View>
              
              <View
                style={{
                  position: 'absolute',
                  bottom: 15,
                  left: 15,
                }}
              >
                <MaterialCommunityIcons
                  name="star-four-points"
                  size={12}
                  color={theme.colors.wizard.primaryLight}
                  style={{ opacity: 0.6 }}
                />
              </View>

              <View
                style={{
                  position: 'absolute',
                  top: 25,
                  left: 25,
                }}
              >
                <MaterialCommunityIcons
                  name="star-four-points"
                  size={14}
                  color={theme.colors.wizard.accent}
                  style={{ opacity: 0.5 }}
                />
              </View>

              {/* Main Chef Hat Icon */}
              <MaterialCommunityIcons
                name="chef-hat"
                size={60}
                color={theme.colors.wizard.primary}
              />
            </View>

            <Text
              style={{
                fontSize: theme.typography.fontSize.displaySmall,
                fontWeight: theme.typography.fontWeight.bold,
                color: theme.colors.theme.text,
                fontFamily: theme.typography.fontFamily.heading,
                textAlign: 'center',
                marginBottom: theme.spacing.md,
                lineHeight: theme.typography.fontSize.displaySmall * 1.2,
              }}
            >
              {heroTitle}
            </Text>
            
            <Text
              style={{
                fontSize: theme.typography.fontSize.bodyLarge,
                color: theme.colors.theme.textSecondary,
                fontFamily: theme.typography.fontFamily.body,
                textAlign: 'center',
                lineHeight: theme.typography.fontSize.bodyLarge * 1.4,
              }}
            >
              {heroSubtitle}
            </Text>

            {!isAuthenticated && guestGenerationsRemaining !== null && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  marginTop: theme.spacing.lg,
                  paddingHorizontal: theme.spacing.md,
                  paddingVertical: theme.spacing.sm,
                  borderRadius: theme.borderRadius.full,
                  backgroundColor: theme.colors.wizard.primary + '15',
                }}
              >
                <MaterialCommunityIcons
                  name="star-four-points"
                  size={16}
                  color={theme.colors.wizard.primary}
                  style={{ marginRight: theme.spacing.sm }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.wizard.primary,
                    fontFamily: theme.typography.fontFamily.body,
                    fontWeight: theme.typography.fontWeight.medium,
                  }}
                >
                  {guestGenerationsRemaining} of {GUEST_WEEKLY_LIMIT} free recipes left this week
                </Text>
              </View>
            )}
          </View>

          {/* Enhanced Input Section */}
          <View
            ref={mainInputRef}
            style={{
              marginBottom: theme.spacing['3xl'],
              position: 'relative',
            }}
          >
            {/* Floating label */}
            {prompt.length > 0 && (
              <View
                style={{
                  position: 'absolute',
                  top: -8,
                  left: theme.spacing.lg,
                  zIndex: 1,
                  backgroundColor: theme.colors.theme.background,
                  paddingHorizontal: theme.spacing.sm,
                }}
              >
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.wizard.primary,
                    fontWeight: theme.typography.fontWeight.medium,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  Your recipe idea
                </Text>
              </View>
            )}

            <View
              style={{
                borderRadius: theme.borderRadius['2xl'],
                borderWidth: 2,
                borderColor: prompt.length > 0 
                  ? theme.colors.wizard.primary 
                  : theme.colors.theme.border,
                backgroundColor: theme.colors.theme.surface,
                ...theme.shadows.surface,
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              {/* Gradient border effect when focused */}
              {prompt.length > 0 && (
                <View
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    right: 0,
                    height: 2,
                    backgroundColor: `linear-gradient(90deg, ${theme.colors.wizard.primary}, ${theme.colors.wizard.accent})`,
                  }}
                />
              )}

              <TextInput
                placeholder={placeholder || 'What sounds good today?'}
                value={prompt}
                onChangeText={(text) => {
                  setPrompt(text);
                  if (error) setError(null);
                  
                  // Reset error state when user starts editing
                  if (isInErrorState) {
                    setIsInErrorState(false);
                    setCurrentButtonText('Generate Recipe');
                  }
                }}
                multiline
                style={{
                  minHeight: 140,
                  fontSize: theme.typography.fontSize.bodyLarge,
                  textAlignVertical: 'top',
                  paddingTop: theme.spacing.xl,
                  paddingBottom: theme.spacing['4xl'],
                  lineHeight: theme.typography.fontSize.bodyLarge * 1.5,
                }}
                containerStyle={{ marginBottom: 0 }}
              />
              
              {/* Magic indicators */}
              <View
                style={{
                  position: 'absolute',
                  bottom: theme.spacing.lg,
                  right: theme.spacing.lg,
                  flexDirection: 'row',
                  alignItems: 'center',
                }}
              >
                <MaterialCommunityIcons
                  name="auto-fix"
                  size={24}
                  color={theme.colors.wizard.primary}
                  style={{
                    opacity: prompt ? 1 : 0.3,
                    marginRight: theme.spacing.sm,
                  }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textTertiary,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  {prompt.length}/500
                </Text>
              </View>
            </View>
          </View>


          {/* Recipe Options (non-persistent, collapsed by default) */}
          <ExpandableCard
            title="Recipe Options"
            subtitle={`${servings} servings${difficulty ? ` • ${difficulty}` : ''}`}
            icon="tune"
            defaultExpanded={false}
            compact
            style={{ marginBottom: theme.spacing.xl }}
          >
            {/* Servings selector */}
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: theme.spacing.lg,
                backgroundColor: theme.colors.theme.backgroundSecondary,
                borderRadius: theme.borderRadius.xl,
                paddingHorizontal: theme.spacing.lg,
                paddingVertical: theme.spacing.md,
                borderWidth: 1,
                borderColor: theme.colors.theme.borderLight,
              }}
            >
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <MaterialCommunityIcons name="account-group" size={18} color={theme.colors.theme.textSecondary} />
                <Text
                  style={{
                    marginLeft: theme.spacing.sm,
                    fontSize: theme.typography.fontSize.bodyLarge,
                    color: theme.colors.theme.text,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  Servings
                </Text>
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <TouchableOpacity
                  onPress={() => setServings(prev => Math.max(1, prev - 1))}
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 18,
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: theme.colors.theme.surface,
                    borderWidth: 1,
                    borderColor: theme.colors.theme.border,
                    marginRight: theme.spacing.md,
                  }}
                >
                  <MaterialCommunityIcons name="minus" size={18} color={theme.colors.theme.text} />
                </TouchableOpacity>
                <Text
                  style={{
                    minWidth: 36,
                    textAlign: 'center',
                    fontSize: theme.typography.fontSize.titleMedium,
                    color: theme.colors.theme.text,
                    fontFamily: theme.typography.fontFamily.body,
                    fontWeight: theme.typography.fontWeight.semibold,
                  }}
                >
                  {servings}
                </Text>
                <TouchableOpacity
                  onPress={() => setServings(prev => Math.min(24, prev + 1))}
                  style={{
                    width: 36,
                    height: 36,
                    borderRadius: 18,
                    alignItems: 'center',
                    justifyContent: 'center',
                    backgroundColor: theme.colors.wizard.primary + '25',
                    marginLeft: theme.spacing.md,
                  }}
                >
                  <MaterialCommunityIcons name="plus" size={18} color={theme.colors.wizard.primary} />
                </TouchableOpacity>
              </View>
            </View>

            {/* Difficulty selector */}
            <View
              style={{
                backgroundColor: theme.colors.theme.backgroundSecondary,
                borderRadius: theme.borderRadius.xl,
                padding: theme.spacing.sm,
                borderWidth: 1,
                borderColor: theme.colors.theme.borderLight,
              }}
            >
              <Text
                style={{
                  fontSize: theme.typography.fontSize.bodyLarge,
                  color: theme.colors.theme.text,
                  fontFamily: theme.typography.fontFamily.body,
                  marginBottom: theme.spacing.sm,
                  marginLeft: theme.spacing.sm,
                }}
              >
                Difficulty
              </Text>
              <View style={{ flexDirection: 'row', gap: theme.spacing.sm }}>
                {(['easy', 'medium', 'hard'] as const).map(level => {
                  const active = difficulty === level;
                  return (
                    <TouchableOpacity
                      key={level}
                      onPress={() => setDifficulty(level)}
                      style={{
                        flex: 1,
                        flexDirection: 'row',
                        alignItems: 'center',
                        justifyContent: 'center',
                        paddingVertical: theme.spacing.md,
                        borderRadius: theme.borderRadius.lg,
                        backgroundColor: active
                          ? theme.colors.wizard.primary + '25'
                          : theme.colors.theme.surface,
                        borderWidth: 1,
                        borderColor: active
                          ? theme.colors.wizard.primary
                          : theme.colors.theme.border,
                      }}
                    >
                      <MaterialCommunityIcons
                        name={level === 'easy' ? 'star-outline' : level === 'medium' ? 'star-half-full' : 'star'}
                        size={16}
                        color={active ? theme.colors.wizard.primary : theme.colors.theme.textSecondary}
                        style={{ marginRight: theme.spacing.xs }}
                      />
                      <Text
                        style={{
                          fontSize: theme.typography.fontSize.bodyMedium,
                          color: active ? theme.colors.wizard.primary : theme.colors.theme.text,
                          fontFamily: theme.typography.fontFamily.body,
                          fontWeight: active ? theme.typography.fontWeight.semibold : theme.typography.fontWeight.medium,
                          textTransform: 'capitalize',
                        }}
                      >
                        {level}
                      </Text>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          </ExpandableCard>

          {/* Enhanced Create Button with Progress Bar */}
          <View style={{ marginBottom: theme.spacing['3xl'] }}>
            <TouchableOpacity
              onPress={handleCreateRecipe}
              disabled={(!prompt.trim() && currentButtonText === 'Generate Recipe') || 
                       (isLoading && !currentButtonText.includes('Tap to retry'))}
              style={{
                minHeight: 64,
                borderRadius: theme.borderRadius['2xl'],
                backgroundColor: !prompt.trim() 
                  ? theme.colors.theme.border 
                  : currentButtonText.includes('failed') || currentButtonText.includes('retry')
                    ? theme.colors.theme.surface // Neutral background for error state
                    : isLoading 
                      ? theme.colors.wizard.primary + '30' // Lighter background when loading
                      : theme.colors.wizard.primary,
                borderWidth: currentButtonText.includes('failed') || currentButtonText.includes('retry') ? 2 : 0,
                borderColor: currentButtonText.includes('failed') || currentButtonText.includes('retry') ? '#f59e0b' : 'transparent', // Orange border instead of red
                overflow: 'hidden',
                position: 'relative',
              }}
            >
              
              {/* Progress Bar Fill */}
              {isLoading && (
                <Animated.View
                  style={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    bottom: 0,
                    width: progressAnimation.interpolate({
                      inputRange: [0, 1],
                      outputRange: ['0%', '100%'],
                    }),
                    backgroundColor: theme.colors.wizard.primary,
                  }}
                />
              )}
              
              {/* Button Content */}
              <View
                style={{
                  flex: 1,
                  flexDirection: 'row',
                  alignItems: 'center',
                  justifyContent: 'center',
                  paddingHorizontal: theme.spacing.xl,
                  paddingVertical: theme.spacing.lg,
                }}
              >
                {!isLoading && (
                  <MaterialCommunityIcons
                    name={currentButtonText.includes('failed') || currentButtonText.includes('retry') 
                      ? "refresh" 
                      : "auto-fix"}
                    size={24}
                    color={!prompt.trim() 
                      ? theme.colors.theme.textTertiary 
                      : currentButtonText.includes('failed') || currentButtonText.includes('retry')
                        ? '#f59e0b' // Orange icon for retry
                        : 'white'}
                    style={{ marginRight: theme.spacing.md }}
                  />
                )}
                
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.titleMedium,
                    fontWeight: theme.typography.fontWeight.semibold,
                    color: !prompt.trim() 
                      ? theme.colors.theme.textTertiary 
                      : currentButtonText.includes('failed') || currentButtonText.includes('retry')
                        ? '#f59e0b' // Orange text for retry state
                        : 'white',
                    fontFamily: theme.typography.fontFamily.body,
                    textAlign: 'center',
                  }}
                >
                  {currentButtonText}
                </Text>
              </View>
            </TouchableOpacity>
          </View>

          {/* Recipe Ideas Section */}
          <View>
            <Text
              style={{
                fontSize: theme.typography.fontSize.titleLarge,
                fontWeight: theme.typography.fontWeight.semibold,
                color: theme.colors.theme.text,
                fontFamily: theme.typography.fontFamily.body,
                marginBottom: theme.spacing.lg,
                textAlign: 'center',
              }}
            >
              Or try one of these ideas
            </Text>
            
            {/* Pill Slider for mode selection */}
            <View style={{ marginBottom: theme.spacing.xl, alignItems: 'center' }}>
              <PillSlider
                options={sliderOptions}
                selectedValue={sliderMode}
                onValueChange={handleSliderChange}
              />
            </View>

            {/* Conditional content based on slider mode */}
            {sliderMode === 'preset' ? (
              /* Preset Suggestions */
              <View style={{ gap: theme.spacing.md }}>
                {suggestionPrompts.map((suggestion, index) => (
                  <TouchableOpacity
                    key={index}
                    onPress={() => handleSuggestionPress(suggestion.text)}
                    style={{
                      flexDirection: 'row',
                      alignItems: 'center',
                      backgroundColor: theme.colors.theme.backgroundSecondary,
                      borderRadius: theme.borderRadius.xl,
                      padding: theme.spacing.lg,
                      borderWidth: 1,
                      borderColor: theme.colors.theme.borderLight,
                    }}
                  >
                    <View
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: 20,
                        backgroundColor: theme.colors.wizard.primary + '20',
                        alignItems: 'center',
                        justifyContent: 'center',
                        marginRight: theme.spacing.lg,
                      }}
                    >
                      <MaterialCommunityIcons
                        name={suggestion.icon}
                        size={20}
                        color={theme.colors.wizard.primary}
                      />
                    </View>
                    
                    <Text
                      style={{
                        flex: 1,
                        fontSize: theme.typography.fontSize.bodyLarge,
                        color: theme.colors.theme.text,
                        fontFamily: theme.typography.fontFamily.body,
                        fontWeight: theme.typography.fontWeight.medium,
                      }}
                    >
                      {suggestion.text}
                    </Text>

                    <MaterialCommunityIcons
                      name="chevron-right"
                      size={20}
                      color={theme.colors.theme.textTertiary}
                    />
                  </TouchableOpacity>
                ))}
                <View style={{ marginTop: theme.spacing.lg }}>
                  <Button
                    variant="secondary"
                    fullWidth
                    leftIcon="refresh"
                    onPress={refreshDynamicCopy}
                  >
                    Refresh ideas
                  </Button>
                </View>
              </View>
            ) : (
              /* Generate Ideas Mode */
              <PremiumFeature
                featureName="AI Recipe Ideas"
                description="Get creative recipe suggestions based on your preferences and dietary needs. Perfect for discovering new dishes!"
                size="medium"
              >
                <View>
                  {/* Generate Ideas Prompt Input */}
                  <View style={{ marginBottom: theme.spacing.lg }}>
                    <View
                      style={{
                        borderRadius: theme.borderRadius.xl,
                        borderWidth: 2,
                        borderColor: generateIdeasPrompt.length > 0
                          ? theme.colors.wizard.primary
                          : theme.colors.theme.border,
                        backgroundColor: theme.colors.theme.surface,
                        ...theme.shadows.surface,
                        position: 'relative',
                        overflow: 'hidden',
                      }}
                    >
                      <TextInput
                        placeholder={getRandomSuggestion()}
                        value={generateIdeasPrompt}
                        onChangeText={(text) => {
                          setGenerateIdeasPrompt(text);
                          // Reset error state when user starts editing
                          if (isIdeasInErrorState) {
                            setIsIdeasInErrorState(false);
                            setGenerateIdeasButtonText('Generate Ideas');
                          }
                          // Update button text based on whether text has changed from last generation
                          if (generatedIdeas.length > 0) {
                            if (text !== lastGeneratedPrompt) {
                              setGenerateIdeasButtonText('Generate Ideas');
                            } else {
                              setGenerateIdeasButtonText('Refresh Ideas');
                            }
                          }
                        }}
                        style={{
                          minHeight: 80,
                          fontSize: theme.typography.fontSize.bodyLarge,
                          textAlignVertical: 'top',
                          paddingTop: theme.spacing.lg,
                          paddingBottom: theme.spacing.lg,
                          lineHeight: theme.typography.fontSize.bodyLarge * 1.4,
                        }}
                        containerStyle={{ marginBottom: 0 }}
                      />
                    </View>
                  </View>

                  {/* Generate Ideas Button with 2-segment progress */}
                <TouchableOpacity
                  onPress={handleGenerateIdeas}
                  disabled={(!generateIdeasPrompt.trim() && generateIdeasButtonText !== 'Refresh Ideas') || 
                           (isGeneratingIdeas && !generateIdeasButtonText.includes('Tap to retry'))}
                  style={{
                    minHeight: 48,
                    borderRadius: theme.borderRadius.xl,
                    backgroundColor: (!generateIdeasPrompt.trim() && generatedIdeas.length === 0) 
                      ? theme.colors.theme.border 
                      : generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry')
                        ? theme.colors.theme.surface 
                        : isGeneratingIdeas 
                          ? theme.colors.wizard.primary + '30' 
                          : theme.colors.wizard.primary,
                    borderWidth: generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry') ? 2 : 0,
                    borderColor: generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry') ? '#f59e0b' : 'transparent',
                    overflow: 'hidden',
                    position: 'relative',
                    marginBottom: theme.spacing.lg,
                  }}
                >
                  {/* Progress Bar Fill (2-segment) */}
                  {isGeneratingIdeas && (
                    <Animated.View
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        bottom: 0,
                        width: ideasProgressAnimation.interpolate({
                          inputRange: [0, 1],
                          outputRange: ['0%', '100%'],
                        }),
                        backgroundColor: theme.colors.wizard.primary,
                      }}
                    />
                  )}

                  <View
                    style={{
                      flex: 1,
                      flexDirection: 'row',
                      alignItems: 'center',
                      justifyContent: 'center',
                      paddingHorizontal: theme.spacing.lg,
                      paddingVertical: theme.spacing.md,
                    }}
                  >
                    {!isGeneratingIdeas && (
                      <MaterialCommunityIcons
                        name={generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry') 
                          ? "refresh" 
                          : generateIdeasButtonText === 'Refresh Ideas'
                            ? "refresh"
                            : "lightbulb-on"}
                        size={20}
                        color={(!generateIdeasPrompt.trim() && generatedIdeas.length === 0) 
                          ? theme.colors.theme.textTertiary 
                          : generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry')
                            ? '#f59e0b' 
                            : 'white'}
                        style={{ marginRight: theme.spacing.sm }}
                      />
                    )}
                    
                    <Text
                      style={{
                        fontSize: theme.typography.fontSize.bodyLarge,
                        fontWeight: theme.typography.fontWeight.semibold,
                        color: (!generateIdeasPrompt.trim() && generatedIdeas.length === 0) 
                          ? theme.colors.theme.textTertiary 
                          : generateIdeasButtonText.includes('failed') || generateIdeasButtonText.includes('retry')
                            ? '#f59e0b' 
                            : 'white',
                        fontFamily: theme.typography.fontFamily.body,
                        textAlign: 'center',
                      }}
                    >
                      {generateIdeasButtonText}
                    </Text>
                  </View>
                </TouchableOpacity>

                {/* Generated Ideas Display Cards */}
                {generatedIdeas.length > 0 && (
                  <View>
                    <View style={{ gap: theme.spacing.md }}>
                      {generatedIdeas.map((idea, index) => (
                        <TouchableOpacity
                          key={idea.id}
                          onPress={() => handleIdeaPress(idea)}
                          style={{
                            flexDirection: 'row',
                            alignItems: 'flex-start',
                            backgroundColor: theme.colors.theme.surface,
                            borderRadius: theme.borderRadius.xl,
                            padding: theme.spacing.lg,
                            borderWidth: 1,
                            borderColor: theme.colors.theme.borderLight,
                            ...theme.shadows.surface,
                          }}
                        >
                          {/* Numbered indicator */}
                          <View
                            style={{
                              width: 32,
                              height: 32,
                              borderRadius: 16,
                              backgroundColor: theme.colors.wizard.primary + '20',
                              alignItems: 'center',
                              justifyContent: 'center',
                              marginRight: theme.spacing.md,
                              marginTop: 2, // Slight alignment with text
                            }}
                          >
                            <Text
                              style={{
                                fontSize: theme.typography.fontSize.bodySmall,
                                fontWeight: theme.typography.fontWeight.bold,
                                color: theme.colors.wizard.primary,
                                fontFamily: theme.typography.fontFamily.body,
                              }}
                            >
                              {index + 1}
                            </Text>
                          </View>

                          {/* Content */}
                          <View style={{ flex: 1 }}>
                            <Text
                              style={{
                                fontSize: theme.typography.fontSize.titleSmall,
                                fontWeight: theme.typography.fontWeight.semibold,
                                color: theme.colors.theme.text,
                                fontFamily: theme.typography.fontFamily.body,
                                marginBottom: theme.spacing.xs,
                                lineHeight: theme.typography.fontSize.titleSmall * 1.3,
                              }}
                            >
                              {idea.title}
                            </Text>
                            <Text
                              style={{
                                fontSize: theme.typography.fontSize.bodyMedium,
                                color: theme.colors.theme.textSecondary,
                                fontFamily: theme.typography.fontFamily.body,
                                lineHeight: theme.typography.fontSize.bodyMedium * 1.4,
                              }}
                            >
                              {idea.description}
                            </Text>
                          </View>

                          {/* Arrow indicator */}
                          <View style={{ marginLeft: theme.spacing.sm, marginTop: 2 }}>
                            <MaterialCommunityIcons
                              name="arrow-right-circle"
                              size={20}
                              color={theme.colors.wizard.primary}
                              style={{ opacity: 0.7 }}
                            />
                          </View>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                )}
                </View>
              </PremiumFeature>
            )}
          </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>

      {/* Guest weekly quota exceeded */}
      <Portal>
        <Dialog visible={quotaExceededDialogVisible} onDismiss={() => setQuotaExceededDialogVisible(false)}>
          <Dialog.Icon icon="crown-outline" />
          <Dialog.Title>Weekly limit reached</Dialog.Title>
          <Dialog.Content>
            <Text
              style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium,
                lineHeight: theme.typography.fontSize.bodyMedium * 1.4,
              }}
            >
              You've used all your free recipe generations for this week. Your free recipes reset {formatResetIn(guestQuotaResetAt)}.
              {'\n\n'}Sign up for extra generations and a better model — it only takes a minute.
            </Text>
          </Dialog.Content>
          <Dialog.Actions>
            <PaperButton onPress={() => setQuotaExceededDialogVisible(false)}>Maybe later</PaperButton>
            <PaperButton
              onPress={() => {
                setQuotaExceededDialogVisible(false);
                router.push('/auth/signup');
              }}
            >
              Sign Up
            </PaperButton>
          </Dialog.Actions>
        </Dialog>
      </Portal>
    </>
  );
}
