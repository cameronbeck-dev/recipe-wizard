import React, { useState } from 'react';
import { ScrollView, TextInput as RNTextInput, TouchableOpacity, View } from 'react-native';
import { Portal, Dialog, Text, Button as PaperButton } from 'react-native-paper';
import { useAppTheme } from '../../constants/ThemeProvider';
import { getCategoryLabel } from '../../constants/categories';

interface AddManualItemSheetProps {
  visible: boolean;
  categories: string[];
  onDismiss: () => void;
  onSubmit: (data: { ingredientName: string; quantity?: string; category: string }) => Promise<void> | void;
}

export function AddManualItemSheet({ visible, categories, onDismiss, onSubmit }: AddManualItemSheetProps) {
  const { theme } = useAppTheme();
  const [ingredientName, setIngredientName] = useState('');
  const [quantity, setQuantity] = useState('');
  const [category, setCategory] = useState(categories[0] || 'pantry');
  const [submitting, setSubmitting] = useState(false);

  const reset = () => {
    setIngredientName('');
    setQuantity('');
    setCategory(categories[0] || 'pantry');
  };

  const handleDismiss = () => {
    reset();
    onDismiss();
  };

  const handleSubmit = async () => {
    if (!ingredientName.trim()) return;
    setSubmitting(true);
    try {
      await onSubmit({
        ingredientName: ingredientName.trim(),
        quantity: quantity.trim() || undefined,
        category,
      });
      reset();
      onDismiss();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Portal>
      <Dialog visible={visible} onDismiss={handleDismiss}>
        <Dialog.Title>Add Item</Dialog.Title>
        <Dialog.Content>
          <RNTextInput
            placeholder="Ingredient name"
            value={ingredientName}
            onChangeText={setIngredientName}
            placeholderTextColor={theme.colors.theme.textTertiary}
            style={{
              borderWidth: 1,
              borderColor: theme.colors.theme.border,
              borderRadius: theme.borderRadius.md,
              paddingHorizontal: theme.spacing.md,
              paddingVertical: theme.spacing.sm,
              color: theme.colors.theme.text,
              marginBottom: theme.spacing.md,
            }}
          />
          <RNTextInput
            placeholder="Quantity (optional, e.g. 2 rolls)"
            value={quantity}
            onChangeText={setQuantity}
            placeholderTextColor={theme.colors.theme.textTertiary}
            style={{
              borderWidth: 1,
              borderColor: theme.colors.theme.border,
              borderRadius: theme.borderRadius.md,
              paddingHorizontal: theme.spacing.md,
              paddingVertical: theme.spacing.sm,
              color: theme.colors.theme.text,
              marginBottom: theme.spacing.md,
            }}
          />
          <Text style={{ marginBottom: theme.spacing.sm, color: theme.colors.theme.textSecondary }}>Category</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              {categories.map(cat => (
                <TouchableOpacity
                  key={cat}
                  onPress={() => setCategory(cat)}
                  style={{
                    paddingHorizontal: theme.spacing.md,
                    paddingVertical: theme.spacing.sm,
                    borderRadius: theme.borderRadius.full,
                    backgroundColor: category === cat ? theme.colors.wizard.primary : theme.colors.theme.backgroundSecondary,
                  }}
                >
                  <Text style={{ color: category === cat ? '#ffffff' : theme.colors.theme.text }}>
                    {getCategoryLabel(cat)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </ScrollView>
        </Dialog.Content>
        <Dialog.Actions>
          <PaperButton onPress={handleDismiss}>Cancel</PaperButton>
          <PaperButton onPress={handleSubmit} disabled={!ingredientName.trim() || submitting} loading={submitting}>
            Add
          </PaperButton>
        </Dialog.Actions>
      </Dialog>
    </Portal>
  );
}
