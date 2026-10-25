import { useRouter } from "expo-router";
import { CaretRight, ShareNetwork } from "phosphor-react-native";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from "react-native";
import Animated, { FadeInDown, ZoomIn } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { money, useSavings, useTrip } from "@/src/api";
import { CHECK_BAR_HEIGHT, CheckDealsBar } from "@/src/components/check-deals-bar";
import { Houndstooth } from "@/src/components/houndstooth";
import { Button, StoreAvatar, Txt } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

function ago(iso?: string | null) {
  if (!iso) return "Not checked yet";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "Checked just now";
  if (mins < 60) return `Checked ${mins} min ago`;
  const h = Math.round(mins / 60);
  return h < 24 ? `Checked ${h}h ago` : `Checked ${Math.round(h / 24)}d ago`;
}

export default function SavingsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const q = useSavings();
  const trip = useTrip();
  const s = q.data;
  const max = Math.max(1, ...(s?.by_store.map((b) => b.savings) ?? [1]));

  return (
    <View style={styles.root} testID="savings-screen">
      {q.isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} size="large" /></View>
      ) : q.error ? (
        <View style={styles.center}>
          <Txt testID="savings-error" style={styles.muted}>Couldn&apos;t load savings. {q.error.message}</Txt>
          <Button testID="savings-retry-button" label="Retry" variant="secondary" onPress={() => q.refetch()} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ paddingTop: insets.top + spacing.lg, paddingHorizontal: spacing.lg, paddingBottom: CHECK_BAR_HEIGHT + bottomChrome + spacing.lg, gap: spacing.xl }}
          refreshControl={<RefreshControl refreshing={q.isRefetching} onRefresh={() => q.refetch()} tintColor={colors.brandPrimary} />}
        >
          <Animated.View entering={ZoomIn.springify().damping(14)} style={styles.hero}>
            <View style={[styles.blob, styles.blobA]} />
            <View style={[styles.blob, styles.blobB]} />
            <Txt style={styles.heroKicker}>You could save</Txt>
            <Txt medium testID="savings-total" style={styles.heroNum} adjustsFontSizeToFit numberOfLines={1}>{money(s?.total ?? 0)}</Txt>
            <Txt style={styles.heroKicker}>this week</Txt>
            <View style={styles.heroStats}>
              <Txt testID="savings-deal-count" style={styles.heroStat}>{s?.deal_count ?? 0} of {s?.item_count ?? 0} items on sale</Txt>
              <Txt style={styles.heroStat}>{ago(s?.last_checked_at)}</Txt>
            </View>
            {(s?.total ?? 0) > 0 && (
              <Pressable testID="savings-share-button" onPress={() => router.push("/share-card")} style={styles.shareBtn}>
                <ShareNetwork size={18} color={colors.brandSecondary} weight="bold" />
                <Txt medium style={styles.shareText}>Share my savings</Txt>
              </Pressable>
            )}
            <Houndstooth height={24} style={styles.heroBand} testID="savings-hero-houndstooth" />
          </Animated.View>

          {trip.data?.store && (
            <Pressable testID="savings-trip-card" onPress={() => router.push("/trip")} style={styles.tripCard}>
              <StoreAvatar store={trip.data.store} size={44} />
              <View style={{ flex: 1 }}>
                <Txt style={styles.small}>Best single-store trip</Txt>
                <Txt medium style={styles.tripTitle}>Shop {trip.data.store}, save {money(trip.data.savings)}</Txt>
                <Txt style={styles.small}>Shopping list for {trip.data.items.length} items · est. {money(trip.data.estimated_total)}</Txt>
              </View>
              <CaretRight size={20} color={colors.muted} />
            </Pressable>
          )}

          {s && s.item_count === 0 ? (
            <Txt testID="savings-empty" style={styles.muted}>Start adding to your watchlist to see savings.</Txt>
          ) : s && s.by_store.length > 0 ? (
            <>
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>Where to shop</Txt>
                {s.by_store.map((b, i) => (
                  <Animated.View key={b.store} entering={FadeInDown.delay(i * 80)} style={styles.storeRow} testID={`savings-store-${b.store.toLowerCase().replace(/\W/g, "")}`}>
                    <StoreAvatar store={b.store} size={36} />
                    <View style={styles.storeBody}>
                      <View style={styles.storeHead}>
                        <Txt medium style={styles.storeName}>{b.store}</Txt>
                        <Txt medium style={styles.storeAmt}>{money(b.savings)}</Txt>
                      </View>
                      <View style={styles.bar}>
                        <View style={[styles.barFill, { width: `${(b.savings / max) * 100}%` }]} />
                      </View>
                      <Txt style={styles.small}>{b.count} deal{b.count === 1 ? "" : "s"}</Txt>
                    </View>
                  </Animated.View>
                ))}
              </View>
              <View style={styles.section}>
                <Txt style={styles.sectionTitle}>Biggest wins</Txt>
                {s.top.map((d) => (
                  <View key={d.id} style={styles.winRow} testID={`savings-top-${d.id}`}>
                    <View style={{ flex: 1 }}>
                      <Txt medium numberOfLines={1}>{d.item_name}</Txt>
                      <Txt style={styles.small}>{d.store} · {money(d.sale_price)} (was {money(d.usual_price)})</Txt>
                    </View>
                    <Txt medium style={styles.winAmt}>−{money(d.savings)}</Txt>
                  </View>
                ))}
              </View>
            </>
          ) : (
            <Txt style={styles.muted}>No deals found yet. Run a check to scan this week&apos;s ads.</Txt>
          )}
        </ScrollView>
      )}
      <CheckDealsBar testID="savings-check-now-button" />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.lg, padding: spacing.xl },
  muted: { color: c.muted, fontSize: 15, textAlign: "center" },
  hero: { backgroundColor: c.brandPrimary, borderRadius: radius.lg + 8, padding: spacing.xl, paddingVertical: spacing["2xl"], overflow: "hidden" },
  blob: { position: "absolute", borderRadius: 999, backgroundColor: c.brandSecondary },
  blobA: { width: 220, height: 220, top: -80, right: -70, opacity: 0.6 },
  blobB: { width: 120, height: 120, bottom: -40, left: -30, opacity: 0.4 },
  heroKicker: { color: c.onBrandPrimary, fontSize: 18, opacity: 0.9 },
  heroNum: { color: c.onBrandPrimary, fontSize: 80, lineHeight: 92, letterSpacing: -3 },
  heroStats: { marginTop: spacing.lg, gap: 2 },
  heroBand: { position: "absolute", left: 0, right: 0, bottom: 0 },
  heroStat: { color: c.onBrandPrimary, opacity: 0.85, fontSize: 13 },
  shareBtn: { flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm, alignSelf: "flex-start", marginTop: spacing.lg, height: 44, minWidth: 180, paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: c.onBrandPrimary },
  shareText: { color: c.brandSecondary, fontSize: 14 },
  tripCard: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, backgroundColor: c.brandTertiary, borderRadius: radius.lg },
  tripTitle: { fontSize: 17, color: c.onBrandTertiary },
  section: { gap: spacing.md },
  sectionTitle: { fontSize: 20 },
  storeRow: { flexDirection: "row", gap: spacing.md, padding: spacing.lg, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border },
  storeBody: { flex: 1, gap: spacing.xs },
  storeHead: { flexDirection: "row", justifyContent: "space-between" },
  storeName: { fontSize: 16 },
  storeAmt: { fontSize: 16, color: c.brandSecondary },
  bar: { height: 8, borderRadius: 4, backgroundColor: c.surfaceTertiary, overflow: "hidden" },
  barFill: { height: 8, borderRadius: 4, backgroundColor: c.brandPrimary },
  small: { fontSize: 12, color: c.muted },
  winRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  winAmt: { fontSize: 18, color: c.brandSecondary },
}));
