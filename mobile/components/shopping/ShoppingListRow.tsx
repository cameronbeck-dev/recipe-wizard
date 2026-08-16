import React, { useState } from 'react';
import { TextInput as RNTextInput, TouchableOpacity, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useAppTheme } from '../../constants/ThemeProvider';
import { ShoppingListItem } from '../../types/api';
import { SwipeableRow } from './SwipeableRow';

interface ShoppingListRowProps {
  item: ShoppingListItem;
  categoryColor: string;
  expanded: boolean;
  onToggleExpanded: () => void;
  onToggleChecked: () => void;
  onRecipePress: (recipeId: string, recipeTitle: string) => void;
  onSetQuantity: (quantity: string | null) => void;
  onDelete: () => void;
}

export function ShoppingListRow({
  item,
  categoryColor,
  expanded,
  onToggleExpanded,
  onToggleChecked,
  onRecipePress,
  onSetQuantity,
  onDelete,
}: ShoppingListRowProps) {
  const { theme } = useAppTheme();
  const [editing, setEditing] = useState(false);
  const [draftQuantity, setDraftQuantity] = useState(item.consolidatedDisplay);

  const hasBreakdown = item.recipeBreakdown.length > 0;
  const isManual = item.source === 'manual';

  const commitEdit = () => {
    setEditing(false);
    const trimmed = draftQuantity.trim();
    if (trimmed && trimmed !== item.consolidatedDisplay) {
      onSetQuantity(trimmed);
    } else if (!trimmed) {
      setDraftQuantity(item.consolidatedDisplay);
    }
  };

  return (
    <SwipeableRow onDelete={onDelete}>
      <View>
        <TouchableOpacity
          onPress={onToggleChecked}
          activeOpacity={0.7}
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            paddingVertical: theme.spacing.md,
            paddingHorizontal: theme.spacing.lg,
            borderRadius: theme.borderRadius.lg,
            borderWidth: 1,
            backgroundColor: item.isChecked
              ? categoryColor + '10'
              : theme.colors.theme.backgroundSecondary,
            borderColor: item.isChecked
              ? categoryColor + '40'
              : theme.colors.theme.borderLight,
          }}
        >
          {/* Checkbox */}
          <View
            style={{
              width: 24,
              height: 24,
              borderRadius: theme.borderRadius.md,
              borderWidth: 2,
              borderColor: item.isChecked ? theme.colors.wizard.primary : theme.colors.theme.border,
              backgroundColor: item.isChecked ? theme.colors.wizard.primary : 'transparent',
              alignItems: 'center',
              justifyContent: 'center',
              marginRight: theme.spacing.lg,
            }}
          >
            {item.isChecked && <MaterialCommunityIcons name="check" size={16} color="#ffffff" />}
          </View>

          {/* Quantity + name */}
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap' }}>
              {editing ? (
                <RNTextInput
                  value={draftQuantity}
                  onChangeText={setDraftQuantity}
                  onBlur={commitEdit}
                  onSubmitEditing={commitEdit}
                  autoFocus
                  onStartShouldSetResponder={() => true}
                  style={{
                    fontSize: theme.typography.fontSize.bodyLarge,
                    fontWeight: '600',
                    color: theme.colors.theme.text,
                    borderBottomWidth: 1,
                    borderBottomColor: theme.colors.wizard.primary,
                    minWidth: 60,
                    paddingVertical: 0,
                  }}
                />
              ) : (
                <TouchableOpacity
                  onPress={(e) => {
                    e.stopPropagation();
                    setDraftQuantity(item.consolidatedDisplay);
                    setEditing(true);
                  }}
                >
                  <Text
                    style={{
                      fontSize: theme.typography.fontSize.bodyLarge,
                      fontWeight: '600',
                      color: item.isChecked ? theme.colors.theme.textSecondary : theme.colors.theme.textSecondary,
                      textDecorationLine: item.isChecked ? 'line-through' : 'none',
                    }}
                  >
                    {item.consolidatedDisplay}
                  </Text>
                </TouchableOpacity>
              )}

              <Text
                style={{
                  fontSize: theme.typography.fontSize.bodyLarge,
                  fontWeight: theme.typography.fontWeight.medium,
                  color: item.isChecked ? theme.colors.theme.textSecondary : theme.colors.theme.text,
                  textDecorationLine: item.isChecked ? 'line-through' : 'none',
                  marginLeft: theme.spacing.xs,
                }}
              >
                {item.ingredientName}
              </Text>

              {item.userQuantityOverride && (
                <MaterialCommunityIcons
                  name="pencil-circle"
                  size={14}
                  color={theme.colors.wizard.primary}
                  style={{ marginLeft: theme.spacing.xs }}
                />
              )}

              {isManual && (
                <View
                  style={{
                    marginLeft: theme.spacing.xs,
                    paddingHorizontal: 6,
                    paddingVertical: 1,
                    borderRadius: theme.borderRadius.sm,
                    backgroundColor: theme.colors.theme.backgroundTertiary,
                  }}
                >
                  <Text style={{ fontSize: theme.typography.fontSize.labelSmall, color: theme.colors.theme.textTertiary }}>
                    manual
                  </Text>
                </View>
              )}

              {item.recipeBreakdown.length > 1 && (
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodySmall,
                    color: theme.colors.theme.textSecondary,
                  }}
                >
                  {' '}(from {item.recipeBreakdown.length} recipes)
                </Text>
              )}
            </View>

            {item.overrideIsStale && (
              <TouchableOpacity
                onPress={(e) => {
                  e.stopPropagation();
                  onSetQuantity(null);
                }}
                style={{ marginTop: 4 }}
              >
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.labelSmall,
                    color: theme.colors.status.warning,
                  }}
                >
                  Recipes now need {item.autoConsolidatedDisplay} · Recalculate
                </Text>
              </TouchableOpacity>
            )}
          </View>

          {/* Dropdown arrow for recipe breakdown */}
          {hasBreakdown && (
            <TouchableOpacity
              onPress={(e) => {
                e.stopPropagation();
                onToggleExpanded();
              }}
              style={{
                padding: 8,
                borderRadius: 12,
                backgroundColor: expanded ? theme.colors.wizard.primary + '15' : 'transparent',
              }}
            >
              <MaterialCommunityIcons
                name={expanded ? 'chevron-up' : 'chevron-down'}
                size={20}
                color={expanded ? theme.colors.wizard.primary : theme.colors.theme.textTertiary}
              />
            </TouchableOpacity>
          )}
        </TouchableOpacity>

        {expanded && hasBreakdown && (
          <View
            style={{
              marginTop: 4,
              marginLeft: 40,
              paddingLeft: 16,
              paddingTop: 8,
              paddingBottom: 8,
              borderLeftWidth: 3,
              borderLeftColor: categoryColor + '30',
              backgroundColor: theme.colors.theme.backgroundTertiary,
              borderRadius: 8,
              marginRight: 8,
            }}
          >
            {item.recipeBreakdown.map((recipe, index) => (
              <View key={index} style={{ flexDirection: 'row', alignItems: 'center', paddingVertical: 2 }}>
                <MaterialCommunityIcons name="chef-hat" size={14} color={categoryColor} style={{ marginRight: 8 }} />
                <Text style={{ fontSize: theme.typography.fontSize.bodySmall, color: theme.colors.theme.text, flex: 1 }}>
                  <Text style={{ fontWeight: '600', color: theme.colors.theme.textSecondary }}>{recipe.quantity}</Text>
                  {' for '}
                  <TouchableOpacity onPress={() => onRecipePress(recipe.recipeId, recipe.recipeTitle)}>
                    <Text style={{ fontStyle: 'italic', color: theme.colors.wizard.primary, textDecorationLine: 'underline' }}>
                      {recipe.recipeTitle}
                    </Text>
                  </TouchableOpacity>
                </Text>
              </View>
            ))}
          </View>
        )}
      </View>
    </SwipeableRow>
  );
}
