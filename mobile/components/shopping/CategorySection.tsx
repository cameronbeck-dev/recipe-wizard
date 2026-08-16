import React from 'react';
import { TouchableOpacity, View } from 'react-native';
import { Text } from 'react-native-paper';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useAppTheme } from '../../constants/ThemeProvider';
import { getCategoryIcon, getCategoryColor, getCategoryLabel } from '../../constants/categories';

interface CategorySectionProps {
  category: string;
  checkedCount: number;
  totalCount: number;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  children: React.ReactNode;
}

export function CategorySection({
  category,
  checkedCount,
  totalCount,
  collapsed,
  onToggleCollapsed,
  children,
}: CategorySectionProps) {
  const { theme } = useAppTheme();
  const categoryColor = getCategoryColor(category);

  return (
    <View style={{ marginBottom: 32 }}>
      <TouchableOpacity
        onPress={onToggleCollapsed}
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          marginBottom: collapsed ? 0 : 16,
        }}
      >
        <View
          style={{
            width: 32,
            height: 32,
            borderRadius: 16,
            backgroundColor: categoryColor + '20',
            alignItems: 'center',
            justifyContent: 'center',
            marginRight: 12,
          }}
        >
          <MaterialCommunityIcons name={getCategoryIcon(category)} size={16} color={categoryColor} />
        </View>

        <Text
          style={{
            fontSize: theme.typography.fontSize.titleMedium,
            fontWeight: theme.typography.fontWeight.medium,
            color: theme.colors.theme.text,
            flex: 1,
          }}
        >
          {getCategoryLabel(category)}
        </Text>

        <Text style={{ fontSize: theme.typography.fontSize.bodySmall, color: theme.colors.theme.textTertiary, marginRight: 8 }}>
          {checkedCount}/{totalCount}
        </Text>

        <MaterialCommunityIcons
          name={collapsed ? 'chevron-down' : 'chevron-up'}
          size={20}
          color={theme.colors.theme.textTertiary}
        />
      </TouchableOpacity>

      {!collapsed && <View style={{ gap: 8 }}>{children}</View>}
    </View>
  );
}
