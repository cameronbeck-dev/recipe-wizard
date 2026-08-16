import React, { useEffect, useState } from 'react';
import { View, ActivityIndicator } from 'react-native';
import { Redirect } from 'expo-router';
import { useAuth } from '../contexts/AuthContext';
import { useAppTheme } from '../constants/ThemeProvider';
import { getHasOnboarded } from '../services/onboarding';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuth();
  const { theme } = useAppTheme();
  const [hasOnboarded, setHasOnboarded] = useState<boolean | null>(null);

  useEffect(() => {
    getHasOnboarded().then(setHasOnboarded);
  }, []);

  // Show loading spinner while checking authentication (and, for
  // unauthenticated users, while we check the onboarding flag)
  if (isLoading || (!isAuthenticated && hasOnboarded === null)) {
    return (
      <View
        style={{
          flex: 1,
          justifyContent: 'center',
          alignItems: 'center',
          backgroundColor: theme.colors.theme.background
        }}
      >
        <ActivityIndicator
          size="large"
          color={theme.colors.wizard.primary}
        />
      </View>
    );
  }

  // Signed-in users always go straight to the app, regardless of onboarding
  // state — existing users upgrading the app must never be bounced to the
  // welcome screen.
  if (isAuthenticated) {
    return <Redirect href="/(tabs)/prompt" />;
  }

  // Returning guest who has already been through the welcome screen
  if (hasOnboarded) {
    return <Redirect href="/(tabs)/prompt" />;
  }

  return <Redirect href="/welcome" />;
}
