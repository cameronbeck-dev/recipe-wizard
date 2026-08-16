import React, { useState, useEffect } from 'react';
import { ScrollView, View, RefreshControl, TouchableOpacity, TextInput as RNTextInput } from 'react-native';
import { Text, Portal, Dialog, Button, Menu } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useAppTheme } from '../../constants/ThemeProvider';
import { useNetworkStatus } from '../../hooks/useNetworkStatus';
import { ShoppingListItem, SavedRecipeData } from '../../types/api';
import { apiService } from '../../services/api';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useFocusEffect } from '@react-navigation/native';
import { router } from 'expo-router';
import { HeaderComponent } from '../../components/HeaderComponent';
import { SafeAreaView } from 'react-native-safe-area-context';
import { PremiumFeature } from '../../components/PremiumFeature';
import { usePremium } from '../../contexts/PremiumContext';
import { PremiumBadge } from '../../components/PremiumBadge';
import { useToast } from '../../contexts/ToastContext';
import { PreferencesService } from '../../services/preferences';
import { CategorySection } from '../../components/shopping/CategorySection';
import { ShoppingListRow } from '../../components/shopping/ShoppingListRow';
import { AddManualItemSheet } from '../../components/shopping/AddManualItemSheet';
import { getCategoryColor } from '../../constants/categories';

const COLLAPSED_CATEGORIES_KEY = '@RecipeWizard:collapsedShoppingCategories';

export default function ShoppingListScreen() {
  const { theme } = useAppTheme();
  const { isOnline } = useNetworkStatus();
  const { isPremium } = usePremium();
  const toast = useToast();

  const [shoppingList, setShoppingList] = useState<ShoppingListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [clearDialogVisible, setClearDialogVisible] = useState(false);
  const [clearCheckedDialogVisible, setClearCheckedDialogVisible] = useState(false);
  const [menuVisible, setMenuVisible] = useState(false);
  const [expandedItems, setExpandedItems] = useState<Set<string>>(new Set());
  const [collapsedCategories, setCollapsedCategories] = useState<Set<string>>(new Set());
  const [refreshing, setRefreshing] = useState(false);
  const [savedRecipes, setSavedRecipes] = useState<SavedRecipeData[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [addSheetVisible, setAddSheetVisible] = useState(false);
  const [groceryCategories, setGroceryCategories] = useState<string[]>([]);

  // Load persisted collapsed-category state
  useEffect(() => {
    AsyncStorage.getItem(COLLAPSED_CATEGORIES_KEY).then(raw => {
      if (raw) {
        try {
          setCollapsedCategories(new Set(JSON.parse(raw)));
        } catch {}
      }
    });
    PreferencesService.loadPreferences().then(prefs => {
      setGroceryCategories(prefs.groceryCategories);
    }).catch(() => {});
  }, []);

  const isSearching = searchQuery.trim().length > 0;

  // Filter by search, then group by category
  const filteredList = isSearching
    ? shoppingList.filter(item => item.ingredientName.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : shoppingList;

  const itemsByCategory = filteredList.reduce((acc, item) => {
    if (!acc[item.category]) {
      acc[item.category] = [];
    }
    acc[item.category].push(item);
    return acc;
  }, {} as Record<string, ShoppingListItem[]>);

  const categories = Object.keys(itemsByCategory).sort();
  const totalItems = shoppingList.length;
  const completedItems = shoppingList.filter(item => item.isChecked).length;
  const checkedCount = shoppingList.filter(item => item.isChecked).length;

  const toggleItemExpanded = (itemId: string) => {
    const newExpanded = new Set(expandedItems);
    if (newExpanded.has(itemId)) {
      newExpanded.delete(itemId);
    } else {
      newExpanded.add(itemId);
    }
    setExpandedItems(newExpanded);
  };

  const toggleCategoryCollapsed = (category: string) => {
    const next = new Set(collapsedCategories);
    if (next.has(category)) {
      next.delete(category);
    } else {
      next.add(category);
    }
    setCollapsedCategories(next);
    AsyncStorage.setItem(COLLAPSED_CATEGORIES_KEY, JSON.stringify(Array.from(next))).catch(() => {});
  };

  const handleRecipePress = async (recipeId: string, recipeTitle: string) => {
    try {
      const savedRecipe = savedRecipes.find(recipe => recipe.id === recipeId);

      if (savedRecipe) {
        router.push({
          pathname: '/recipe-result',
          params: {
            recipeData: JSON.stringify(savedRecipe),
            fromShoppingList: 'true'
          }
        });
        return;
      }

      const conversationHistory = await apiService.getConversationHistory(50);
      const historyRecipe = conversationHistory.find(entry => entry.response.id === recipeId);

      if (historyRecipe) {
        router.push({
          pathname: '/recipe-result',
          params: {
            recipeData: JSON.stringify(historyRecipe.response),
            fromShoppingList: 'true'
          }
        });
        return;
      }

      console.warn('Recipe not found in local data:', recipeId, recipeTitle);
      toast.show(`Sorry, the recipe "${recipeTitle}" could not be found.`, { variant: 'error' });

    } catch (error) {
      console.error('Error navigating to recipe:', error);
      toast.show(`Sorry, there was an error loading the recipe "${recipeTitle}".`, { variant: 'error' });
    }
  };

  const toggleItemChecked = async (itemId: string) => {
    const updatedItems = shoppingList.map(item =>
      item.id === itemId ? { ...item, isChecked: !item.isChecked } : item
    );
    setShoppingList(updatedItems);

    if (isOnline) {
      try {
        const item = updatedItems.find(i => i.id === itemId);
        if (item) {
          await apiService.updateShoppingListItem(itemId, item.isChecked);
        }
      } catch (error) {
        console.error('Error syncing item check status:', error);
        setShoppingList(prev => prev.map(item =>
          item.id === itemId ? { ...item, isChecked: !item.isChecked } : item
        ));
      }
    }

    try {
      await AsyncStorage.setItem('cached_shopping_list', JSON.stringify(updatedItems));
    } catch (error) {
      console.error('Error updating cached shopping list:', error);
    }
  };

  const handleSetItemQuantity = async (itemId: string, quantity: string | null) => {
    const previous = shoppingList;
    try {
      const response = await apiService.setItemQuantity(itemId, quantity);
      setShoppingList(prev => prev.map(item => (item.id === itemId ? response.item : item)));
    } catch (error) {
      console.error('Error setting item quantity:', error);
      setShoppingList(previous);
      toast.show('Failed to update quantity. Please try again.', { variant: 'error' });
    }
  };

  const handleDeleteItem = async (itemId: string) => {
    const previous = shoppingList;
    setShoppingList(prev => prev.filter(item => item.id !== itemId));
    try {
      await apiService.deleteShoppingListItem(itemId);
    } catch (error) {
      console.error('Error deleting item:', error);
      setShoppingList(previous);
      toast.show('Failed to delete item. Please try again.', { variant: 'error' });
    }
  };

  const handleAddManualItem = async (data: { ingredientName: string; quantity?: string; category: string }) => {
    try {
      const response = await apiService.addManualItem(data);
      setShoppingList(prev => {
        const existingIndex = prev.findIndex(i => i.id === response.item.id);
        if (existingIndex >= 0) {
          const copy = [...prev];
          copy[existingIndex] = response.item;
          return copy;
        }
        return [...prev, response.item];
      });
      toast.show(`Added "${data.ingredientName}" to your shopping list`, { variant: 'success' });
    } catch (error) {
      console.error('Error adding manual item:', error);
      toast.show('Failed to add item. Please try again.', { variant: 'error' });
    }
  };

  const clearShoppingList = async () => {
    try {
      setClearDialogVisible(false);

      if (isOnline) {
        await apiService.clearShoppingList();
      }

      setShoppingList([]);
      await AsyncStorage.removeItem('cached_shopping_list');
    } catch (error) {
      console.error('Error clearing shopping list:', error);
      toast.show('Failed to clear shopping list. Please try again.', { variant: 'error' });
    }
  };

  const clearCheckedItems = async () => {
    try {
      setClearCheckedDialogVisible(false);
      const response = await apiService.clearCheckedItems();
      setShoppingList(response.items);
      await AsyncStorage.setItem('cached_shopping_list', JSON.stringify(response.items));
      toast.show(`Removed ${response.removedCount} checked item${response.removedCount === 1 ? '' : 's'}`, { variant: 'success' });
    } catch (error) {
      console.error('Error clearing checked items:', error);
      toast.show('Failed to clear checked items. Please try again.', { variant: 'error' });
    }
  };

  // Load shopping list from API/cache
  useEffect(() => {
    loadShoppingList();
  }, []);

  useFocusEffect(
    React.useCallback(() => {
      loadShoppingList();
    }, [isOnline])
  );

  const loadShoppingList = async () => {
    try {
      setLoading(true);

      if (isOnline) {
        const [shoppingResponse, savedRecipesData] = await Promise.all([
          apiService.getShoppingList(),
          apiService.getSavedRecipes().catch(() => [])
        ]);

        setShoppingList(shoppingResponse.items);
        setSavedRecipes(savedRecipesData);

        await AsyncStorage.setItem('cached_shopping_list', JSON.stringify(shoppingResponse.items));
        await AsyncStorage.setItem('cached_saved_recipes', JSON.stringify(savedRecipesData));
      } else {
        const [cachedShoppingList, cachedSavedRecipes] = await Promise.all([
          AsyncStorage.getItem('cached_shopping_list'),
          AsyncStorage.getItem('cached_saved_recipes')
        ]);

        if (cachedShoppingList) {
          setShoppingList(JSON.parse(cachedShoppingList));
        }
        if (cachedSavedRecipes) {
          setSavedRecipes(JSON.parse(cachedSavedRecipes));
        }
      }
    } catch (error) {
      console.error('Error loading shopping list:', error);

      try {
        const [cachedShoppingList, cachedSavedRecipes] = await Promise.all([
          AsyncStorage.getItem('cached_shopping_list'),
          AsyncStorage.getItem('cached_saved_recipes')
        ]);

        if (cachedShoppingList) {
          setShoppingList(JSON.parse(cachedShoppingList));
        }
        if (cachedSavedRecipes) {
          setSavedRecipes(JSON.parse(cachedSavedRecipes));
        }
      } catch (cacheError) {
        console.error('Error loading cached data:', cacheError);
      }
    } finally {
      setLoading(false);
    }
  };

  const onRefresh = async () => {
    setRefreshing(true);
    try {
      await loadShoppingList();
    } finally {
      setRefreshing(false);
    }
  };

  if (loading) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.theme.background }} edges={['top']}>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <MaterialCommunityIcons
            name="cart-outline"
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
            Loading Shopping List
          </Text>
          <Text
            style={{
              fontSize: theme.typography.fontSize.bodyMedium,
              color: theme.colors.theme.textSecondary,
              textAlign: 'center',
            }}
          >
            Getting your ingredients ready...
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  // Show premium lock screen for non-premium users
  if (!isPremium) {
    return (
      <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.theme.background }} edges={['top']}>
        <HeaderComponent
          title="Shopping List"
          subtitle="Premium Feature"
          rightContent={
            <MaterialCommunityIcons
              name="crown"
              size={24}
              color={theme.colors.wizard.primary}
            />
          }
        />

        <PremiumFeature
          featureName="Smart Shopping Lists"
          description="Automatically combine ingredients from multiple recipes, organize by store categories, and keep track of what you need to buy. Never forget ingredients again!"
          size="large"
          style={{ margin: theme.spacing.lg, flex: 1 }}
        >
          <View />
        </PremiumFeature>
      </SafeAreaView>
    );
  }

  const renderEmptyState = () => (
    <View style={{
      flex: 1,
      justifyContent: 'center',
      alignItems: 'center',
      paddingHorizontal: 32
    }}>
      <MaterialCommunityIcons
        name="cart-outline"
        size={80}
        color={theme.colors.theme.textSecondary}
      />
      <Text
        style={{
          fontSize: theme.typography.fontSize.headlineMedium,
          fontWeight: theme.typography.fontWeight.bold,
          color: theme.colors.theme.text,
          textAlign: 'center',
          marginTop: 16,
          marginBottom: 8
        }}
      >
        Your Shopping List is Empty
      </Text>
      <Text
        style={{
          fontSize: theme.typography.fontSize.bodyLarge,
          color: theme.colors.theme.textSecondary,
          textAlign: 'center',
          lineHeight: 24
        }}
      >
        Add recipes to your shopping list from the recipe screen to get started!
      </Text>
    </View>
  );

  const renderNoMatchesState = () => (
    <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 32 }}>
      <MaterialCommunityIcons name="magnify" size={64} color={theme.colors.theme.textSecondary} />
      <Text
        style={{
          fontSize: theme.typography.fontSize.titleMedium,
          fontWeight: theme.typography.fontWeight.semibold,
          color: theme.colors.theme.text,
          textAlign: 'center',
          marginTop: 16,
        }}
      >
        No items match "{searchQuery}"
      </Text>
    </View>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: theme.colors.theme.background }} edges={['top']}>
        <HeaderComponent
          title="Shopping List"
          subtitle={shoppingList.length === 0 ? "Empty" : `${completedItems}/${totalItems} items completed`}
          rightContent={
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <PremiumBadge size="small" style={{ marginRight: theme.spacing.sm }} />
              {!isOnline && (
                <MaterialCommunityIcons
                  name="wifi-off"
                  size={20}
                  color={theme.colors.theme.textSecondary}
                  style={{ marginRight: 16 }}
                />
              )}
              <TouchableOpacity onPress={() => setAddSheetVisible(true)} style={{ marginRight: 16 }}>
                <MaterialCommunityIcons name="plus-circle-outline" size={24} color={theme.colors.theme.textSecondary} />
              </TouchableOpacity>
              {shoppingList.length > 0 && (
                <Menu
                  visible={menuVisible}
                  onDismiss={() => setMenuVisible(false)}
                  anchor={
                    <TouchableOpacity onPress={() => setMenuVisible(true)}>
                      <MaterialCommunityIcons
                        name="delete-sweep"
                        size={24}
                        color={theme.colors.theme.textSecondary}
                      />
                    </TouchableOpacity>
                  }
                >
                  <Menu.Item
                    onPress={() => {
                      setMenuVisible(false);
                      setClearCheckedDialogVisible(true);
                    }}
                    title="Clear checked items"
                    disabled={checkedCount === 0}
                    leadingIcon="check-circle-outline"
                  />
                  <Menu.Item
                    onPress={() => {
                      setMenuVisible(false);
                      setClearDialogVisible(true);
                    }}
                    title="Clear all"
                    leadingIcon="delete-sweep"
                  />
                </Menu>
              )}
            </View>
          }
        />

        {shoppingList.length > 0 && (
          <View style={{ paddingHorizontal: 20, paddingTop: 12 }}>
            <View
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                backgroundColor: theme.colors.theme.backgroundSecondary,
                borderRadius: theme.borderRadius.lg,
                paddingHorizontal: theme.spacing.md,
              }}
            >
              <MaterialCommunityIcons name="magnify" size={20} color={theme.colors.theme.textTertiary} />
              <RNTextInput
                value={searchQuery}
                onChangeText={setSearchQuery}
                placeholder="Search ingredients..."
                placeholderTextColor={theme.colors.theme.textTertiary}
                style={{
                  flex: 1,
                  paddingVertical: theme.spacing.sm,
                  paddingHorizontal: theme.spacing.sm,
                  color: theme.colors.theme.text,
                }}
              />
              {isSearching && (
                <TouchableOpacity onPress={() => setSearchQuery('')}>
                  <MaterialCommunityIcons name="close-circle" size={18} color={theme.colors.theme.textTertiary} />
                </TouchableOpacity>
              )}
            </View>
          </View>
        )}

        {shoppingList.length === 0 ? renderEmptyState() : (
          categories.length === 0 ? renderNoMatchesState() : (
          <ScrollView
            style={{ flex: 1 }}
            contentContainerStyle={{ padding: 20 }}
            showsVerticalScrollIndicator={false}
            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                tintColor={theme.colors.wizard.primary}
              />
            }
          >
            {categories.map(category => {
            const categoryItems = itemsByCategory[category];
            const checkedInCategory = categoryItems.filter(item => item.isChecked).length;
            const collapsed = !isSearching && collapsedCategories.has(category);

            return (
              <CategorySection
                key={category}
                category={category}
                checkedCount={checkedInCategory}
                totalCount={categoryItems.length}
                collapsed={collapsed}
                onToggleCollapsed={() => toggleCategoryCollapsed(category)}
              >
                {categoryItems.map(item => (
                  <ShoppingListRow
                    key={item.id}
                    item={item}
                    categoryColor={getCategoryColor(category)}
                    expanded={expandedItems.has(item.id)}
                    onToggleExpanded={() => toggleItemExpanded(item.id)}
                    onToggleChecked={() => toggleItemChecked(item.id)}
                    onRecipePress={handleRecipePress}
                    onSetQuantity={(quantity) => handleSetItemQuantity(item.id, quantity)}
                    onDelete={() => handleDeleteItem(item.id)}
                  />
                ))}
              </CategorySection>
            );
          })}
          </ScrollView>
          )
        )}

        {/* Clear All Confirmation Dialog */}
        <Portal>
          <Dialog visible={clearDialogVisible} onDismiss={() => setClearDialogVisible(false)}>
            <Dialog.Title>Clear Shopping List</Dialog.Title>
            <Dialog.Content>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium
              }}>
                Are you sure you want to clear all {totalItems} items from your shopping list? This action cannot be undone.
              </Text>
            </Dialog.Content>
            <Dialog.Actions>
              <Button onPress={() => setClearDialogVisible(false)}>Cancel</Button>
              <Button onPress={clearShoppingList}>Clear All</Button>
            </Dialog.Actions>
          </Dialog>
        </Portal>

        {/* Clear Checked Confirmation Dialog */}
        <Portal>
          <Dialog visible={clearCheckedDialogVisible} onDismiss={() => setClearCheckedDialogVisible(false)}>
            <Dialog.Title>Clear Checked Items</Dialog.Title>
            <Dialog.Content>
              <Text style={{
                color: theme.colors.theme.textSecondary,
                fontSize: theme.typography.fontSize.bodyMedium
              }}>
                Remove {checkedCount} checked item{checkedCount === 1 ? '' : 's'} from your shopping list? This action cannot be undone.
              </Text>
            </Dialog.Content>
            <Dialog.Actions>
              <Button onPress={() => setClearCheckedDialogVisible(false)}>Cancel</Button>
              <Button onPress={clearCheckedItems}>Clear Checked</Button>
            </Dialog.Actions>
          </Dialog>
        </Portal>

        <AddManualItemSheet
          visible={addSheetVisible}
          categories={groceryCategories.length > 0 ? groceryCategories : ['pantry']}
          onDismiss={() => setAddSheetVisible(false)}
          onSubmit={handleAddManualItem}
        />
      </SafeAreaView>
  );
}
