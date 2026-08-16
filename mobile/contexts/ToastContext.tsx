import React, { createContext, useCallback, useContext, useState } from 'react';
import { Portal, Snackbar, Text } from 'react-native-paper';
import { useAppTheme } from '../constants/ThemeProvider';

type ToastVariant = 'success' | 'error' | 'info';

interface ToastOptions {
  variant?: ToastVariant;
  actionLabel?: string;
  onAction?: () => void;
  duration?: number;
}

interface ToastContextType {
  show: (message: string, options?: ToastOptions) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

const DEFAULT_DURATION = 4000;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const { theme } = useAppTheme();
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState('');
  const [variant, setVariant] = useState<ToastVariant>('info');
  const [duration, setDuration] = useState(DEFAULT_DURATION);
  const [action, setAction] = useState<{ label: string; onPress: () => void } | undefined>(undefined);

  const show = useCallback((msg: string, options: ToastOptions = {}) => {
    setMessage(msg);
    setVariant(options.variant || 'info');
    setDuration(options.duration ?? DEFAULT_DURATION);
    setAction(
      options.actionLabel && options.onAction
        ? { label: options.actionLabel, onPress: options.onAction }
        : undefined
    );
    setVisible(true);
  }, []);

  const variantColor = variant === 'success'
    ? theme.colors.status.success
    : variant === 'error'
      ? theme.colors.status.error
      : theme.colors.wizard.primary;

  return (
    <ToastContext.Provider value={{ show }}>
      {children}
      <Portal>
        <Snackbar
          visible={visible}
          onDismiss={() => setVisible(false)}
          duration={duration}
          action={action}
          style={{ backgroundColor: variantColor }}
        >
          <Text style={{ color: '#ffffff' }}>{message}</Text>
        </Snackbar>
      </Portal>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (context === undefined) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
}
