import { Redirect, Tabs, useRouter } from "expo-router";
import { NativeTabs } from "expo-router/unstable-native-tabs";
import { ListChecks, PiggyBank, Tag, UserCircle } from "phosphor-react-native";
import { useEffect, useRef } from "react";
import { Platform } from "react-native";

import { useAlerts, useApi } from "@/src/api";
import { useSession } from "@/src/auth";
import { useBanner } from "@/src/components/banner";
import { usesNativeTabs } from "@/src/navigation";
import { registerForPush } from "@/src/push";
import { fonts, useTheme } from "@/src/theme";

function AlertWatcher() {
  const alerts = useAlerts();
  const banner = useBanner();
  const router = useRouter();
  const api = useApi();
  const seen = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (!alerts.data) return;
    const unread = alerts.data.filter((a) => !a.read);
    if (seen.current === null) {
      seen.current = new Set();
    }
    const fresh = unread.filter((a) => !seen.current!.has(a.id));
    fresh.forEach((a) => seen.current!.add(a.id));
    if (!fresh.length) return;
    const first = fresh[0];
    banner({
      tone: "deal",
      title: fresh.length === 1 ? first.title : `${fresh.length} new deals on your list`,
      message: fresh.length === 1 ? first.message : first.title,
      onPress: () => router.navigate("/(tabs)/deals"),
      onDismiss: () => api("/alerts/read-all", { method: "POST" }).catch(() => {}),
    });
  }, [alerts.data, banner, router, api]);

  return null;
}

export default function TabsLayout() {
  const { colors } = useTheme();
  const { ready, signedIn } = useSession();
  const api = useApi();

  useEffect(() => {
    if (signedIn) registerForPush(api, false).catch(() => {});
  }, [signedIn, api]);

  if (ready && !signedIn) return <Redirect href="/sign-in" />;

  if (usesNativeTabs) {
    return (
      <>
        <AlertWatcher />
        <NativeTabs tintColor={colors.brandPrimary}>
          <NativeTabs.Trigger name="deals">
            <NativeTabs.Trigger.Icon sf="tag.fill" />
            <NativeTabs.Trigger.Label>Deals</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
          <NativeTabs.Trigger name="watchlist">
            <NativeTabs.Trigger.Icon sf="checklist" />
            <NativeTabs.Trigger.Label>Watchlist</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
          <NativeTabs.Trigger name="savings">
            <NativeTabs.Trigger.Icon sf="dollarsign.circle.fill" />
            <NativeTabs.Trigger.Label>Savings</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
          <NativeTabs.Trigger name="profile">
            <NativeTabs.Trigger.Icon sf="person.crop.circle" />
            <NativeTabs.Trigger.Label>Profile</NativeTabs.Trigger.Label>
          </NativeTabs.Trigger>
        </NativeTabs>
      </>
    );
  }

  const icon = (Icon: typeof Tag) =>
    function TabIcon({ color, focused }: { color: string; focused: boolean }) {
      return <Icon size={24} color={color} weight={focused ? "fill" : "regular"} />;
    };

  return (
    <>
      <AlertWatcher />
      <Tabs
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: colors.brandPrimary,
          tabBarInactiveTintColor: colors.muted,
          tabBarStyle: {
            backgroundColor: colors.surfaceSecondary,
            borderTopColor: colors.border,
            ...(Platform.OS === "web" ? { height: 64 } : {}),
          },
          tabBarItemStyle: { alignSelf: "center" },
          tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 11 },
        }}
      >
        <Tabs.Screen name="deals" options={{ title: "Deals", tabBarIcon: icon(Tag), tabBarButtonTestID: "tab-deals" }} />
        <Tabs.Screen name="watchlist" options={{ title: "Watchlist", tabBarIcon: icon(ListChecks), tabBarButtonTestID: "tab-watchlist" }} />
        <Tabs.Screen name="savings" options={{ title: "Savings", tabBarIcon: icon(PiggyBank), tabBarButtonTestID: "tab-savings" }} />
        <Tabs.Screen name="profile" options={{ title: "Profile", tabBarIcon: icon(UserCircle), tabBarButtonTestID: "tab-profile" }} />
      </Tabs>
    </>
  );
}
