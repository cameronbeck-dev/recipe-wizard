import React, { useState } from 'react';
import { View, Text, StatusBar, TouchableOpacity, Platform, KeyboardAvoidingView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Button, useAppTheme } from '../components';
import { MaterialCommunityIcons } from '@expo/vector-icons';
import { setHasOnboarded } from '../services/onboarding';

export default function WelcomeScreen() {
  const { theme, isDark } = useAppTheme();
  const router = useRouter();
  const [continuing, setContinuing] = useState(false);

  const handleContinueAsGuest = async () => {
    setContinuing(true);
    try {
      await setHasOnboarded();
      router.replace('/(tabs)/prompt');
    } finally {
      setContinuing(false);
    }
  };

  return (
    <>
      <StatusBar
        barStyle={isDark ? 'light-content' : 'dark-content'}
        backgroundColor={theme.colors.theme.background}
        translucent
      />

      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <SafeAreaView
          style={{
            flex: 1,
            backgroundColor: theme.colors.theme.background,
          }}
          edges={['top', 'bottom']}
        >
          <View
            style={{
              flex: 1,
              justifyContent: 'center',
              paddingHorizontal: theme.spacing.xl,
            }}
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
                <View style={{ position: 'absolute', top: 10, right: 20 }}>
                  <MaterialCommunityIcons
                    name="star-four-points"
                    size={16}
                    color={theme.colors.wizard.accent}
                    style={{ opacity: 0.7 }}
                  />
                </View>

                <View style={{ position: 'absolute', bottom: 15, left: 15 }}>
                  <MaterialCommunityIcons
                    name="star-four-points"
                    size={12}
                    color={theme.colors.wizard.primaryLight}
                    style={{ opacity: 0.6 }}
                  />
                </View>

                <View style={{ position: 'absolute', top: 25, left: 25 }}>
                  <MaterialCommunityIcons
                    name="star-four-points"
                    size={14}
                    color={theme.colors.wizard.accent}
                    style={{ opacity: 0.5 }}
                  />
                </View>

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
                Recipe Wizard
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
                Turn any craving into a recipe, instantly ✨
              </Text>
            </View>

            {/* Actions */}
            <View style={{ gap: theme.spacing.md }}>
              <Button
                variant="primary"
                size="large"
                fullWidth
                onPress={() => router.push('/auth/signin')}
                rightIcon="arrow-right"
                style={{
                  minHeight: 64,
                  ...theme.shadows.wizard.glow,
                }}
              >
                Sign In
              </Button>

              <Button
                variant="outline"
                size="large"
                fullWidth
                onPress={() => router.push('/auth/signup')}
                style={{ minHeight: 64 }}
              >
                Create Account
              </Button>

              <TouchableOpacity
                onPress={handleContinueAsGuest}
                disabled={continuing}
                style={{
                  alignItems: 'center',
                  paddingVertical: theme.spacing.lg,
                  opacity: continuing ? 0.6 : 1,
                }}
              >
                <Text
                  style={{
                    fontSize: theme.typography.fontSize.bodyMedium,
                    color: theme.colors.theme.textSecondary,
                    fontFamily: theme.typography.fontFamily.body,
                    fontWeight: theme.typography.fontWeight.medium,
                  }}
                >
                  Continue without an account
                </Text>
              </TouchableOpacity>
            </View>
          </View>
        </SafeAreaView>
      </KeyboardAvoidingView>
    </>
  );
}
