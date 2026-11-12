import { Inter_400Regular } from '@expo-google-fonts/inter/400Regular';
import { Inter_600SemiBold } from '@expo-google-fonts/inter/600SemiBold';
import { Inter_700Bold } from '@expo-google-fonts/inter/700Bold';
import { useFonts } from '@expo-google-fonts/inter/useFonts';
import { focusManager, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DarkTheme, DefaultTheme, Stack, ThemeProvider } from 'expo-router';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { ToastProvider } from '@/components/Toast';
import { LiveProvider } from '@/hooks/useLive';
import { SessionProvider, useSession } from '@/hooks/useSession';
import { DialogHost } from '@/lib/dialog';
import { colors, scheme } from '@/theme';

const theme = {
  ...(scheme === 'light' ? DefaultTheme : DarkTheme),
  colors: { ...(scheme === 'light' ? DefaultTheme : DarkTheme).colors, background: colors.background, card: colors.surface, primary: colors.accent, text: colors.text, border: colors.separator },
};

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
});

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({ Inter_400Regular, Inter_600SemiBold, Inter_700Bold });

  useEffect(() => {
    // Lists refresh when the tab comes back to the front, and stop polling while it's hidden.
    const subscription = AppState.addEventListener('change', (state) => focusManager.setFocused(state === 'active'));
    // The browser's own bars and the page behind the site take the theme's colour, chosen or the phone's.
    document.body.style.backgroundColor = colors.background;
    document.querySelectorAll('meta[name="theme-color"]').forEach((meta) => {
      meta.setAttribute('content', colors.background);
      meta.removeAttribute('media');
    });
    return () => subscription.remove();
  }, []);

  if (!fontsLoaded && !fontError) return null;
  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.background }}>
      <QueryClientProvider client={queryClient}>
        <SessionProvider>
          <LiveProvider>
            <ThemeProvider value={theme}>
              <ToastProvider>
                <Screens />
                <DialogHost />
              </ToastProvider>
            </ThemeProvider>
          </LiveProvider>
        </SessionProvider>
      </QueryClientProvider>
    </GestureHandlerRootView>
  );
}

function Screens() {
  const { status } = useSession();
  if (status === 'loading') return null;

  const signedIn = status === 'signedIn';
  return (
    <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.background }, animation: 'ios_from_right' }}>
      <Stack.Protected guard={signedIn}>
        <Stack.Screen name="(tabs)" options={{ animation: 'fade' }} />
        <Stack.Screen name="project/[id]" />
        <Stack.Screen name="canvas/[id]" />
        <Stack.Screen name="skill/[id]" />
        <Stack.Screen name="chat/[id]" />
        <Stack.Screen name="activity" />
        <Stack.Screen name="account" />
        <Stack.Screen name="watch/[id]" options={{ presentation: 'fullScreenModal', animation: 'slide_from_bottom' }} />
      </Stack.Protected>
      <Stack.Protected guard={!signedIn}>
        <Stack.Screen name="(auth)/login" options={{ animation: 'fade' }} />
      </Stack.Protected>
    </Stack>
  );
}
