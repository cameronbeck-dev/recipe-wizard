import React, { useRef } from 'react';
import { Animated, PanResponder, StyleSheet, TouchableOpacity, View } from 'react-native';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { useAppTheme } from '../../constants/ThemeProvider';

const DELETE_WIDTH = 72;
const OPEN_THRESHOLD = -30;
const HORIZONTAL_DOMINANCE_RATIO = 1.5;

interface SwipeableRowProps {
  onDelete: () => void;
  children: React.ReactNode;
}

export function SwipeableRow({ onDelete, children }: SwipeableRowProps) {
  const { theme } = useAppTheme();
  const translateX = useRef(new Animated.Value(0)).current;
  const isOpen = useRef(false);

  const closeRow = () => {
    Animated.spring(translateX, {
      toValue: 0,
      useNativeDriver: true,
    }).start();
    isOpen.current = false;
  };

  const openRow = () => {
    Animated.spring(translateX, {
      toValue: -DELETE_WIDTH,
      useNativeDriver: true,
    }).start();
    isOpen.current = true;
  };

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_evt, gesture) => {
        return Math.abs(gesture.dx) > Math.abs(gesture.dy) * HORIZONTAL_DOMINANCE_RATIO && Math.abs(gesture.dx) > 8;
      },
      onPanResponderMove: (_evt, gesture) => {
        const base = isOpen.current ? -DELETE_WIDTH : 0;
        const next = base + gesture.dx;
        translateX.setValue(Math.min(0, Math.max(-DELETE_WIDTH, next)));
      },
      onPanResponderRelease: (_evt, gesture) => {
        const base = isOpen.current ? -DELETE_WIDTH : 0;
        const finalValue = base + gesture.dx;
        if (finalValue < OPEN_THRESHOLD) {
          openRow();
        } else {
          closeRow();
        }
      },
    })
  ).current;

  return (
    <View style={styles.container}>
      <View style={[styles.deleteBackground, { backgroundColor: theme.colors.status.error }]}>
        <TouchableOpacity
          onPress={() => {
            closeRow();
            onDelete();
          }}
          style={styles.deleteButton}
        >
          <MaterialCommunityIcons name="trash-can-outline" size={22} color="#ffffff" />
        </TouchableOpacity>
      </View>
      <Animated.View
        {...panResponder.panHandlers}
        style={{ transform: [{ translateX }] }}
      >
        {children}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    position: 'relative',
  },
  deleteBackground: {
    position: 'absolute',
    top: 0,
    bottom: 0,
    right: 0,
    width: DELETE_WIDTH,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 12,
  },
  deleteButton: {
    width: '100%',
    height: '100%',
    alignItems: 'center',
    justifyContent: 'center',
  },
});
