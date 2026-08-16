import { MaterialCommunityIcons } from '@expo/vector-icons';

type IconName = keyof typeof MaterialCommunityIcons.glyphMap;

export function getCategoryIcon(category: string): IconName {
  const categoryLower = category.toLowerCase();
  if (categoryLower.includes('produce') || categoryLower.includes('fruit') || categoryLower.includes('vegetable')) {
    return 'carrot';
  } else if (categoryLower.includes('meat') || categoryLower.includes('protein') || categoryLower.includes('butchery')) {
    return 'food-steak';
  } else if (categoryLower.includes('dairy') || categoryLower.includes('chilled')) {
    return 'fridge';
  } else if (categoryLower.includes('bakery') || categoryLower.includes('bread')) {
    return 'bread-slice';
  } else if (categoryLower.includes('frozen')) {
    return 'snowflake';
  } else if (categoryLower.includes('pantry') || categoryLower.includes('canned') || categoryLower.includes('dry-goods')) {
    return 'sack';
  } else if (categoryLower.includes('spice') || categoryLower.includes('seasoning')) {
    return 'shaker';
  } else if (categoryLower.includes('beverage') || categoryLower.includes('drink')) {
    return 'cup';
  } else {
    return 'cart-outline';
  }
}

export function getCategoryColor(category: string): string {
  const categoryLower = category.toLowerCase();
  if (categoryLower.includes('produce') || categoryLower.includes('fruit') || categoryLower.includes('vegetable')) {
    return '#10b981'; // green
  } else if (categoryLower.includes('meat') || categoryLower.includes('protein') || categoryLower.includes('butchery')) {
    return '#ef4444'; // red
  } else if (categoryLower.includes('dairy') || categoryLower.includes('chilled')) {
    return '#3b82f6'; // blue
  } else if (categoryLower.includes('frozen')) {
    return '#06b6d4'; // cyan
  } else if (categoryLower.includes('pantry') || categoryLower.includes('canned') || categoryLower.includes('dry-goods')) {
    return '#8b5cf6'; // purple
  } else {
    return '#6b7280'; // gray for unknown categories
  }
}

export function getCategoryLabel(category: string): string {
  return category.charAt(0).toUpperCase() + category.slice(1).replace('-', ' ');
}
