import React, { useState } from 'react';
import {
  View,
  Text,
  ScrollView,
  ViewStyle,
  TouchableOpacity,
} from 'react-native';
import { useAppTheme } from '../constants/ThemeProvider';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { CheckboxItem } from './CheckboxItem';
import { ExpandableCard } from './ExpandableCard';

export interface Ingredient {
  id: string;
  name: string;
  amount: string;
  unit?: string;
  category: string; // Allow any custom category string
  checked?: boolean;
}

interface IngredientsSectionProps {
  ingredients: Ingredient[];
  onIngredientToggle?: (ingredientId: string, checked: boolean) => void;
  categoryOrder?: string[]; // Custom category order from user preferences
  style?: ViewStyle;
}

const CATEGORY_CONFIG = {
  'produce': {
    name: 'Fresh Produce',
    icon: 'carrot' as const,
    color: '#10b981', // green
  },
  'butchery': {
    name: 'Meat & Fish',
    icon: 'food-steak' as const,
    color: '#ef4444', // red
  },
  'chilled': {
    name: 'Chilled',
    icon: 'fridge' as const,
    color: '#3b82f6', // blue
  },
  'frozen': {
    name: 'Frozen',
    icon: 'snowflake' as const,
    color: '#06b6d4', // cyan
  },
  'dry-goods': {
    name: 'Dry Goods',
    icon: 'sack' as const,
    color: '#f59e0b', // amber
  },
  'pantry': {
    name: 'Pantry',
    icon: 'cookie' as const,
    color: '#8b5cf6', // purple
  },
} as const;

export function IngredientsSection({
  ingredients,
  onIngredientToggle,
  categoryOrder,
  style,
}: IngredientsSectionProps) {
  const { theme } = useAppTheme();

  // Group ingredients by category
  const ingredientsByCategory = ingredients.reduce((acc, ingredient) => {
    const category = ingredient.category;
    if (!acc[category]) {
      acc[category] = [];
    }
    acc[category].push(ingredient);
    return acc;
  }, {} as Record<string, Ingredient[]>);

  // Use custom category order from user preferences, or fall back to default
  const defaultCategoryOrder: string[] = [
    'produce',
    'butchery', 
    'chilled',
    'frozen',
    'dry-goods',
    'pantry'
  ];

  const finalCategoryOrder = categoryOrder && categoryOrder.length > 0 
    ? categoryOrder 
    : defaultCategoryOrder;

  const handleIngredientToggle = (ingredientId: string, checked: boolean) => {
    onIngredientToggle?.(ingredientId, checked);
  };

  const formatIngredientLabel = (ingredient: Ingredient): string => {
    const { amount, unit, name } = ingredient;
    
    // Check if this is a non-measurement ingredient (LLM will set unit to "N/A")
    const isNonMeasurement = !unit || unit.toLowerCase() === 'n/a';
    
    if (isNonMeasurement && amount) {
      // For non-measurement ingredients, put name first with amount in parentheses
      // e.g., "Salt (to taste)", "Parsley (to garnish)"
      return `${name} (${amount})`;
    } else if (amount && unit) {
      // Standard measurement format: amount + unit + name
      // e.g., "2 cups flour", "1 tbsp olive oil"
      return `${amount} ${unit} ${name}`;
    } else if (amount) {
      // Amount only (no unit specified)
      // e.g., "2 eggs", "1 onion"
      return `${amount} ${name}`;
    } else {
      // Fallback to just the name
      return name;
    }
  };

  const getTotalChecked = () => {
    return ingredients.filter(ing => ing.checked).length;
  };

  const getTotalCount = () => {
    return ingredients.length;
  };

  return (
    <ExpandableCard
      title="Ingredients"
      subtitle={`${getTotalChecked()}/${getTotalCount()} items collected`}
      icon="format-list-checkbox"
      defaultExpanded={false}
      style={style}
    >
      <View style={{ gap: theme.spacing.lg }}>
        {finalCategoryOrder.map(categoryKey => {
          const categoryIngredients = ingredientsByCategory[categoryKey];
          if (!categoryIngredients || categoryIngredients.length === 0) {
            return null;
          }

          const categoryConfig = CATEGORY_CONFIG[categoryKey as keyof typeof CATEGORY_CONFIG] || {
            name: categoryKey.replace('-', ' ').replace(/\b\w/g, l => l.toUpperCase()),
            icon: 'package-variant' as const,
            color: '#6b7280', // gray for unknown categories
          };
          const checkedInCategory = categoryIngredients.filter(ing => ing.checked).length;
          
          return (
            <View key={categoryKey}>
              {/* Category Header */}
              <View
                style={{
                  flexDirection: 'row',
                  alignItems: 'center',
                  marginBottom: theme.spacing.md,
                }}
              >
                <View
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 16,
                    backgroundColor: categoryConfig.color + '20',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginRight: theme.spacing.md,
                  }}
                >
                  <MaterialCommunityIcons
                    name={categoryConfig.icon}
                    size={16}
                    color={categoryConfig.color}
                  />
                </View>
                
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.titleMedium,
                    fontWeight: theme.typography.fontWeight.medium,
                    color: theme.colors.theme.text,
                    fontFamily: theme.typography.fontFamily.body,
                    flex: 1,
                  }}
                >
                  {categoryConfig.name}
                </Text>

                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textTertiary,
                    fontFamily: theme.typography.fontFamily.body,
                  }}
                >
                  {checkedInCategory}/{categoryIngredients.length}
                </Text>
              </View>

              {/* Category Items */}
              <View style={{ gap: theme.spacing.sm, marginBottom: theme.spacing.md }}>
                {categoryIngredients.map(ingredient => (
                  <CheckboxItem
                    key={ingredient.id}
                    label={formatIngredientLabel(ingredient)}
                    checked={ingredient.checked || false}
                    onPress={() => handleIngredientToggle(ingredient.id, !ingredient.checked)}
                    strikeThroughOnCheck
                    style={{
                      backgroundColor: ingredient.checked 
                        ? categoryConfig.color + '10'
                        : theme.colors.theme.backgroundSecondary,
                      borderColor: ingredient.checked 
                        ? categoryConfig.color + '40'
                        : theme.colors.theme.borderLight,
                    }}
                  />
                ))}
              </View>
            </View>
          );
        })}


        {/* Shopping Tips */}
        <View
          style={{
            backgroundColor: theme.colors.wizard.primary + '10',
            borderRadius: theme.borderRadius.lg,
            padding: theme.spacing.lg,
            borderWidth: 1,
            borderColor: theme.colors.wizard.primary + '20',
            marginTop: theme.spacing.md,
          }}
        >
          <View
            style={{
              flexDirection: 'row',
              alignItems: 'flex-start',
            }}
          >
            <MaterialCommunityIcons
              name="lightbulb-outline"
              size={20}
              color={theme.colors.wizard.primary}
              style={{ marginRight: theme.spacing.md, marginTop: 2 }}
            />
            <View style={{ flex: 1 }}>
              <Text
                style={{
                  fontSize: theme.typography.fontSize.bodyMedium,
                  fontWeight: theme.typography.fontWeight.medium,
                  color: theme.colors.theme.text,
                  fontFamily: theme.typography.fontFamily.body,
                  marginBottom: theme.spacing.xs,
                }}
              >
                Shopping Tip
              </Text>
              <Text
                style={{
                  fontSize: theme.typography.fontSize.bodySmall,
                  color: theme.colors.theme.textSecondary,
                  fontFamily: theme.typography.fontFamily.body,
                  lineHeight: theme.typography.fontSize.bodySmall * 1.4,
                }}
              >
                Items are organized by store section to make your shopping trip more efficient. Check off items as you collect them!
              </Text>
            </View>
          </View>
        </View>
      </View>
    </ExpandableCard>
  );
}
