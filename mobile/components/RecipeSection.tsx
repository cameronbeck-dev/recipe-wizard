import React, { useState } from 'react';
import {
  View,
  Text,
  ViewStyle,
} from 'react-native';
import { useAppTheme } from '../constants/ThemeProvider';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { InstructionStep } from './InstructionStep';
import { ExpandableCard } from './ExpandableCard';

export interface Recipe {
  title: string;
  description?: string;
  instructions: string[];
  prepTime?: number; // in minutes
  cookTime?: number; // in minutes
  servings?: number;
  difficulty?: 'easy' | 'medium' | 'hard';
  tips?: string[];
}

interface RecipeSectionProps {
  recipe: Recipe;
  style?: ViewStyle;
}

export function RecipeSection({ recipe, style }: RecipeSectionProps) {
  const { theme } = useAppTheme();

  // Early return if recipe is malformed
  if (!recipe || typeof recipe !== 'object') {
    return null;
  }

  const getDifficultyColor = (difficulty?: string) => {
    switch (difficulty) {
      case 'easy':
        return theme.colors.status.success;
      case 'medium':
        return theme.colors.status.warning;
      case 'hard':
        return theme.colors.status.error;
      default:
        return theme.colors.theme.textTertiary;
    }
  };

  const getDifficultyIcon = (difficulty?: string) => {
    switch (difficulty) {
      case 'easy':
        return 'star-outline';
      case 'medium':
        return 'star-half-full';
      case 'hard':
        return 'star';
      default:
        return 'help-circle-outline';
    }
  };

  const formatTime = (minutes?: number) => {
    if (!minutes || minutes <= 0) return '0m';
    if (minutes < 60) return `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  const getTotalTime = () => {
    const total = (recipe.prepTime || 0) + (recipe.cookTime || 0);
    return total > 0 ? formatTime(total) : undefined;
  };

  // Ensure we have a safe string title
  const safeTitle = typeof recipe.title === 'string' && recipe.title.trim()
    ? recipe.title
    : 'Recipe';

  // Drop blank steps (the model occasionally returns a trailing empty string)
  const steps = (recipe.instructions || []).filter(
    (instruction) => typeof instruction === 'string' && instruction.trim().length > 0
  );

  const subtitle = `${steps.length} steps${getTotalTime() ? ` • ${getTotalTime()}` : ''}`;

  return (
    <ExpandableCard
      title={String(safeTitle)}
      subtitle={String(subtitle)}
      icon="chef-hat"
      defaultExpanded={true}
      style={style}
    >
      <View style={{ gap: theme.spacing.lg }}>
        {/* Recipe Info */}
        <View>
          {recipe.description && typeof recipe.description === 'string' && (
            <Text
              style={{
                fontSize: theme.typography.fontSize.bodyLarge,
                color: theme.colors.theme.textSecondary,
                fontFamily: theme.typography.fontFamily.body,
                lineHeight: theme.typography.fontSize.bodyLarge * 1.4,
                marginBottom: theme.spacing.lg,
              }}
            >
              {String(recipe.description)}
            </Text>
          )}

          {/* Recipe Stats */}
          <View
            style={{
              flexDirection: 'row',
              flexWrap: 'wrap',
              gap: theme.spacing.md,
              marginBottom: theme.spacing.lg,
            }}
          >
            {(() => { const servings = recipe.servings ?? 0; return servings > 0; })() && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: theme.colors.theme.backgroundSecondary,
                  paddingHorizontal: theme.spacing.md,
                  paddingVertical: theme.spacing.sm,
                  borderRadius: theme.borderRadius.md,
                }}
              >
                <MaterialCommunityIcons
                  name="account-group"
                  size={16}
                  color={theme.colors.theme.textTertiary}
                  style={{ marginRight: theme.spacing.xs }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  {recipe.servings ?? 0} serving{(recipe.servings ?? 0) > 1 ? 's' : ''}
                </Text>
              </View>
            )}

            {(recipe.prepTime ?? 0) > 0 && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: theme.colors.theme.backgroundSecondary,
                  paddingHorizontal: theme.spacing.md,
                  paddingVertical: theme.spacing.sm,
                  borderRadius: theme.borderRadius.md,
                }}
              >
                <MaterialCommunityIcons
                  name="clock-outline"
                  size={16}
                  color={theme.colors.theme.textTertiary}
                  style={{ marginRight: theme.spacing.xs }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  {formatTime(recipe.prepTime)} prep
                </Text>
              </View>
            )}

            {(recipe.cookTime ?? 0) > 0 && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: theme.colors.theme.backgroundSecondary,
                  paddingHorizontal: theme.spacing.md,
                  paddingVertical: theme.spacing.sm,
                  borderRadius: theme.borderRadius.md,
                }}
              >
                <MaterialCommunityIcons
                  name="fire"
                  size={16}
                  color={theme.colors.status.warning}
                  style={{ marginRight: theme.spacing.xs }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  {formatTime(recipe.cookTime)} cook
                </Text>
              </View>
            )}

            {recipe.difficulty && (
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  backgroundColor: getDifficultyColor(recipe.difficulty) + '20',
                  paddingHorizontal: theme.spacing.md,
                  paddingVertical: theme.spacing.sm,
                  borderRadius: theme.borderRadius.md,
                  borderWidth: 1,
                  borderColor: getDifficultyColor(recipe.difficulty) + '30',
                }}
              >
                <MaterialCommunityIcons
                  name={getDifficultyIcon(recipe.difficulty) as any}
                  size={16}
                  color={getDifficultyColor(recipe.difficulty)}
                  style={{ marginRight: theme.spacing.xs }}
                />
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: getDifficultyColor(recipe.difficulty),
                    fontFamily: theme.typography.fontFamily.body,
                    fontWeight: theme.typography.fontWeight.medium,
                  }}
                >
                  {recipe.difficulty}
                </Text>
              </View>
            )}
          </View>
        </View>

        {/* Instructions */}
        <View>
          <Text
            style={{
              fontSize: theme.typography.fontSize.titleMedium,
              fontWeight: theme.typography.fontWeight.semibold,
              color: theme.colors.theme.text,
              fontFamily: theme.typography.fontFamily.body,
              marginBottom: theme.spacing.lg,
            }}
          >
            Instructions
          </Text>

          <View style={{ gap: theme.spacing.lg }}>
            {steps.map((instruction, index) => (
              <InstructionStep
                key={index}
                stepNumber={index + 1}
                instruction={instruction}
              />
            ))}
          </View>
        </View>

        {/* Tips */}
        {Array.isArray(recipe.tips) && recipe.tips.length > 0 && (
          <View
            style={{
              backgroundColor: theme.colors.wizard.accent + '10',
              borderRadius: theme.borderRadius.lg,
              padding: theme.spacing.lg,
              borderWidth: 1,
              borderColor: theme.colors.wizard.accent + '20',
            }}
          >
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                marginBottom: theme.spacing.md,
              }}
            >
              <MaterialCommunityIcons
                name="chef-hat"
                size={20}
                color={theme.colors.wizard.accent}
                style={{ marginRight: theme.spacing.md }}
              />
              <Text
                style={{
                  fontSize: theme.typography.fontSize.titleSmall,
                  fontWeight: theme.typography.fontWeight.medium,
                  color: theme.colors.theme.text,
                  fontFamily: theme.typography.fontFamily.body,
                }}
              >
                Chef's Tips
              </Text>
            </View>
            
            <View style={{ gap: theme.spacing.sm }}>
              {recipe.tips.map((tip, index) => (
                <View
                  key={index}
                  style={{
                    flexDirection: 'row',
                    alignItems: 'flex-start',
                  }}
                >
                  <MaterialCommunityIcons
                    name="circle-small"
                    size={16}
                    color={theme.colors.wizard.accent}
                    style={{ marginRight: theme.spacing.sm, marginTop: 2 }}
                  />
                  <Text
                    style={{
                      flex: 1,
                      fontSize: theme.typography.fontSize.bodySmall,
                      color: theme.colors.theme.textSecondary,
                      fontFamily: theme.typography.fontFamily.body,
                      lineHeight: theme.typography.fontSize.bodySmall * 1.4,
                    }}
                  >
                    {typeof tip === 'string' ? tip : `Tip ${index + 1}`}
                  </Text>
                </View>
              ))}
            </View>
          </View>
        )}
      </View>
    </ExpandableCard>
  );
}
