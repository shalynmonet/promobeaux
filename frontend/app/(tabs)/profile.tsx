import { useUser } from "@clerk/expo";
import { useFocusEffect, useRouter } from "expo-router";
import { Bell, CaretRight, MapPin, SignOut, Storefront } from "phosphor-react-native";
import { useCallback, useState } from "react";
import { Linking, Pressable, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAlerts, useApi, useMe } from "@/src/api";
import { useSession } from "@/src/auth";
import { useBanner } from "@/src/components/banner";
import { Button, StoreAvatar, Txt } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { getPushState, PushState, registerForPush } from "@/src/push";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

function PushCard() {
  const styles = useStyles();
  const { colors } = useTheme();
  const api = useApi();
  const banner = useBanner();
  const [state, setState] = useState<PushState | null>(null);
  const [busy, setBusy] = useState(false);

  useFocusEffect(
    useCallback(() => {
      getPushState().then(setState).catch(() => {});
    }, []),
  );

  const enable = async () => {
    setBusy(true);
    try {
      const s = await registerForPush(api, true);
      setState(s);
      if (s.status === "granted") banner({ tone: "success", title: "Deal alerts are on", message: "We'll ping you when your items go on sale." });
    } finally {
      setBusy(false);
    }
  };

  if (!state) return null;
  const blocked = state.status === "denied" && !state.canAskAgain;

  return (
    <View style={styles.card} testID="push-card">
      <View style={styles.rowTop}>
        <View style={styles.iconBubble}><Bell size={20} color={colors.brandPrimary} weight="fill" /></View>
        <View style={{ flex: 1 }}>
          <Txt medium style={styles.cardTitle}>Phone alerts</Txt>
          <Txt testID="push-status" style={styles.muted}>
            {state.status === "unsupported"
              ? "Phone alerts work in the installed app. You'll still see in-app alerts here."
              : state.status === "granted"
                ? "On — we'll notify you when a watched item drops 10%+ or has a BOGO or coupon, and before deals you starred end."
                : blocked
                  ? "Notifications are blocked. Turn them on in Settings to get deal alerts."
                  : "Get a heads-up the moment your regular items go on sale."}
          </Txt>
        </View>
      </View>
      {state.status !== "granted" && state.status !== "unsupported" &&
        (blocked ? (
          <Button testID="push-open-settings-button" label="Open Settings" variant="secondary" onPress={() => Linking.openSettings()} />
        ) : (
          <Button testID="push-enable-button" label="Turn on deal alerts" variant="secondary" onPress={enable} loading={busy} />
        ))}
    </View>
  );
}

function ClerkEmail() {
  const { user } = useUser();
  return <Txt testID="profile-email" style={{ fontSize: 20 }} numberOfLines={1}>{user?.primaryEmailAddress?.emailAddress ?? "Signed in"}</Txt>;
}

export default function ProfileScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const { isDemo, signOut } = useSession();
  const me = useMe();
  const alerts = useAlerts();

  return (
    <View style={styles.root} testID="profile-screen">
      <ScrollView contentContainerStyle={{ paddingTop: insets.top + spacing.lg, paddingHorizontal: spacing.lg, paddingBottom: bottomChrome + spacing.xl, gap: spacing.lg }}>
        <View>
          <Txt style={styles.muted}>{isDemo ? "Demo shopper" : "Your account"}</Txt>
          {isDemo ? <Txt testID="profile-email" style={{ fontSize: 20 }}>demo@promobeaux.app</Txt> : <ClerkEmail />}
        </View>

        <Pressable testID="profile-edit-stores-button" style={styles.card} onPress={() => router.push({ pathname: "/onboarding", params: { edit: "1" } })}>
          <View style={styles.rowTop}>
            <View style={styles.iconBubble}><Storefront size={20} color={colors.brandPrimary} weight="fill" /></View>
            <View style={{ flex: 1, gap: 2 }}>
              <Txt medium style={styles.cardTitle}>Stores & ZIP</Txt>
              <View style={styles.zipRow}>
                <MapPin size={14} color={colors.muted} />
                <Txt testID="profile-zip" style={styles.muted}>{me.data?.zip}</Txt>
              </View>
            </View>
            <CaretRight size={18} color={colors.muted} />
          </View>
          <View style={styles.storeRow}>
            {me.data?.stores.map((s) => (
              <View key={s} style={styles.storePill}>
                <StoreAvatar store={s} size={22} />
                <Txt style={{ fontSize: 13 }}>{s}</Txt>
              </View>
            ))}
          </View>
        </Pressable>

        <PushCard />

        <View style={styles.card} testID="alerts-card">
          <Txt medium style={styles.cardTitle}>Recent alerts</Txt>
          {(alerts.data ?? []).length === 0 ? (
            <Txt style={styles.muted}>No alerts yet. We check your stores every morning.</Txt>
          ) : (
            alerts.data!.slice(0, 6).map((a) => (
              <View key={a.id} style={styles.alertRow} testID={`alert-${a.id}`}>
                {!a.read && <View style={styles.dot} />}
                <View style={{ flex: 1 }}>
                  <Txt numberOfLines={1}>{a.title}</Txt>
                  <Txt style={styles.small} numberOfLines={1}>{a.message}</Txt>
                </View>
              </View>
            ))
          )}
        </View>

        <Button testID="profile-signout-button" label={isDemo ? "Exit demo" : "Sign out"} variant="ghost"
          icon={<SignOut size={18} color={colors.onSurface} />}
          onPress={async () => {
            await signOut();
            router.replace("/sign-in");
          }}
        />
      </ScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  muted: { color: c.muted, fontSize: 14, lineHeight: 20 },
  small: { color: c.muted, fontSize: 12 },
  card: { backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border, padding: spacing.lg, gap: spacing.md },
  rowTop: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  iconBubble: { width: 40, height: 40, borderRadius: 20, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  cardTitle: { fontSize: 16 },
  zipRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  storeRow: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  storePill: { flexDirection: "row", alignItems: "center", gap: spacing.xs + 2, paddingRight: spacing.md, paddingLeft: 4, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary },
  alertRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm, paddingVertical: spacing.xs },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: c.brandPrimary },
}));
