import { ClerkProvider } from "@clerk/expo";
import { tokenCache } from "@clerk/expo/token-cache";
import { QueryClientProvider } from "@tanstack/react-query";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import { useFonts } from "expo-font";
import { Stack, useRouter } from "expo-router";
import * as SplashScreen from "expo-splash-screen";
import { StatusBar } from "expo-status-bar";
import { useEffect } from "react";
import { LogBox, Platform, StyleSheet } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";

import { AuthProvider } from "@/src/auth";
import { BannerProvider, useBanner } from "@/src/components/banner";
import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { useTheme } from "@/src/theme";
import { storage } from "@/src/utils/storage";

LogBox.ignoreAllLogs(true);
SplashScreen.preventAutoHideAsync().catch(() => {});

const publishableKey = process.env.EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY;
if (!publishableKey) throw new Error("Missing EXPO_PUBLIC_CLERK_PUBLISHABLE_KEY");

// Foreground notification display — module scope.
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

// Android channel — module scope so it exists before any push arrives.
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Deal alerts",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
  }).catch(() => {});
}

function NotificationRouting() {
  const router = useRouter();
  const banner = useBanner();

  useEffect(() => {
    if (Platform.OS === "web") return;
    const open = (data: Record<string, any>) => {
      const url = data?.deeplink || data?.action_url;
      if (!url) return;
      if (String(url).startsWith("http")) Linking.openURL(url);
      else router.push(url);
    };
    const tapSub = Notifications.addNotificationResponseReceivedListener((r) =>
      open(r.notification.request.content.data || {}),
    );
    Notifications.getLastNotificationResponseAsync()
      .then((r) => r && open(r.notification.request.content.data || {}))
      .catch(() => {});

    // Weekly nudge for users who blocked notifications.
    (async () => {
      try {
        const { status, canAskAgain } = await Notifications.getPermissionsAsync();
        if (status !== "denied" || canAskAgain) return;
        const last = await storage.getItem("pushNudgeAt", 0);
        if (last && Date.now() - Number(last) <= 7 * 24 * 60 * 60 * 1000) return;
        const stamp = () => storage.setItem("pushNudgeAt", Date.now());
        banner({
          title: "Deal alerts are off",
          message: "Turn on notifications to hear about price drops.",
          actionLabel: "Open Settings",
          onAction: () => {
            stamp();
            Linking.openSettings();
          },
          onDismiss: stamp,
        });
      } catch {}
    })();

    return () => tapSub.remove();
  }, [router, banner]);

  return null;
}

export default function RootLayout() {
  const { colors } = useTheme();
  const [loaded] = useFonts({
    "PlusJakartaSans-Regular": require("../assets/fonts/PlusJakartaSans-Regular.ttf"),
    "PlusJakartaSans-Medium": require("../assets/fonts/PlusJakartaSans-Medium.ttf"),
  });

  useEffect(() => {
    if (loaded) SplashScreen.hideAsync().catch(() => {});
  }, [loaded]);

  if (!loaded) return null;

  return (
    <GestureHandlerRootView style={styles.root}>
      <ErrorBoundary>
        <ClerkProvider publishableKey={publishableKey!} tokenCache={tokenCache}>
          <AuthProvider>
            <QueryClientProvider client={queryClient}>
              <KeyboardProvider>
                <BannerProvider>
                  <StatusBar style="dark" />
                  <NotificationRouting />
                  <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.surface } }}>
                    <Stack.Screen name="add-item" options={{ presentation: "modal" }} />
                    <Stack.Screen name="scan" options={{ presentation: "fullScreenModal" }} />
                    <Stack.Screen name="share-card" options={{ presentation: "modal" }} />
                  </Stack>
                </BannerProvider>
              </KeyboardProvider>
            </QueryClientProvider>
          </AuthProvider>
        </ClerkProvider>
      </ErrorBoundary>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({ root: { flex: 1 } });
