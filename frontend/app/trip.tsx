import { useRouter } from "expo-router";
import { CaretLeft, CheckSquare, Square } from "phosphor-react-native";
import { useEffect, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { money, TripRow, useTrip } from "@/src/api";
import { Houndstooth } from "@/src/components/houndstooth";
import { Button, haptic, StoreAvatar, Txt } from "@/src/components/ui";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";
import { storage } from "@/src/utils/storage";

const PROMO: Record<string, string> = { sale: "Sale", bogo: "BOGO", coupon: "Coupon", cashback: "Cash back" };

export default function TripScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const trip = useTrip();
  const t = trip.data;
  const key = `trip_checked_${(t?.store ?? "none").replace(/\W/g, "")}`;
  const [checked, setChecked] = useState<string[]>([]);

  useEffect(() => {
    if (!t?.store) return;
    storage.getItem(key, "").then((v) => setChecked(typeof v === "string" && v ? v.split(",") : []));
  }, [key, t?.store]);

  const toggle = (id: string) => {
    haptic();
    setChecked((cur) => {
      const next = cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id];
      storage.setItem(key, next.join(","));
      return next;
    });
  };

  const clear = () => {
    setChecked([]);
    storage.setItem(key, "");
  };

  const Row = ({ item }: { item: TripRow }) => {
    const on = checked.includes(item.item_id);
    return (
      <Pressable testID={`trip-item-${item.item_id}`} onPress={() => toggle(item.item_id)} style={styles.row}
        accessibilityRole="checkbox" accessibilityState={{ checked: on }} aria-checked={on} accessibilityLabel={item.name}>
        {on ? <CheckSquare size={26} color={colors.brandPrimary} weight="fill" /> : <Square size={26} color={colors.borderStrong} />}
        <View style={{ flex: 1 }}>
          <Txt medium style={[styles.name, on && styles.done]} numberOfLines={1}>{item.name}</Txt>
          <Txt style={styles.meta} numberOfLines={1}>
            {item.on_deal ? `${PROMO[item.promo_type ?? "sale"]} · save ${money(item.savings)}` : "Regular price"}
          </Txt>
        </View>
        <View style={{ alignItems: "flex-end" }}>
          <Txt medium style={[styles.price, item.on_deal && styles.dealPrice]}>{money(item.price)}</Txt>
          {item.on_deal && <Txt style={styles.was}>{money(item.usual_price)}</Txt>}
        </View>
      </Pressable>
    );
  };

  return (
    <View style={styles.root} testID="trip-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Pressable testID="trip-back-button" onPress={() => router.back()} hitSlop={8} style={styles.back}>
          <CaretLeft size={22} color={colors.onSurface} />
        </Pressable>
        <Txt style={styles.headerTitle}>Best store trip</Txt>
        <View style={{ width: 44 }} />
      </View>
      <Houndstooth height={10} />

      {trip.isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} size="large" /></View>
      ) : trip.error ? (
        <View style={styles.center}>
          <Txt testID="trip-error" style={styles.meta}>Couldn&apos;t build your trip. {trip.error.message}</Txt>
          <Button testID="trip-retry-button" label="Retry" variant="secondary" onPress={() => trip.refetch()} />
        </View>
      ) : !t?.store ? (
        <View style={styles.center} testID="trip-empty">
          <Txt style={styles.emptyTitle}>No store stands out yet</Txt>
          <Txt style={[styles.meta, { textAlign: "center" }]}>Run a deal check and we&apos;ll pick the store that saves you the most this week.</Txt>
        </View>
      ) : (
        <FlatList
          data={t.items}
          keyExtractor={(r) => r.item_id}
          renderItem={Row}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          ListHeaderComponent={
            <View style={styles.hero} testID="trip-hero">
              <View style={styles.heroTop}>
                <StoreAvatar store={t.store} size={48} />
                <View style={{ flex: 1 }}>
                  <Txt style={styles.heroKicker}>Shop here this week</Txt>
                  <Txt medium testID="trip-store" style={styles.heroStore}>{t.store}</Txt>
                </View>
              </View>
              <View style={styles.stats}>
                <View style={styles.stat}>
                  <Txt style={styles.statLabel}>You save</Txt>
                  <Txt medium testID="trip-savings" style={styles.statValue}>{money(t.savings)}</Txt>
                </View>
                <View style={styles.stat}>
                  <Txt style={styles.statLabel}>Est. total</Txt>
                  <Txt medium testID="trip-total" style={styles.statValue}>{money(t.estimated_total)}</Txt>
                </View>
                <View style={styles.stat}>
                  <Txt style={styles.statLabel}>In cart</Txt>
                  <Txt medium testID="trip-progress" style={styles.statValue}>{checked.filter((id) => t.items.some((i) => i.item_id === id)).length}/{t.items.length}</Txt>
                </View>
              </View>
              {t.alternatives.length > 0 && (
                <Txt style={styles.alt} testID="trip-alternatives">
                  Next best: {t.alternatives.slice(0, 2).map((a) => `${a.store} (${money(a.savings)})`).join(", ")}
                </Txt>
              )}
              {checked.length > 0 && (
                <Pressable testID="trip-clear-button" onPress={clear} style={styles.clear}>
                  <Txt style={styles.clearText}>Clear checkmarks</Txt>
                </Pressable>
              )}
            </View>
          }
        />
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.sm, paddingBottom: spacing.sm },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  headerTitle: { fontSize: 18 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.lg, padding: spacing.xl },
  emptyTitle: { fontSize: 20 },
  hero: { backgroundColor: c.brandTertiary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, marginBottom: spacing.sm },
  heroTop: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  heroKicker: { color: c.onBrandTertiary, fontSize: 13 },
  heroStore: { fontSize: 26, color: c.onBrandTertiary, letterSpacing: -0.4 },
  stats: { flexDirection: "row", gap: spacing.sm },
  stat: { flex: 1, backgroundColor: c.surfaceSecondary, borderRadius: radius.md, padding: spacing.md },
  statLabel: { fontSize: 12, color: c.muted },
  statValue: { fontSize: 18 },
  alt: { fontSize: 13, color: c.onBrandTertiary },
  clear: { alignSelf: "flex-start", minHeight: 44, justifyContent: "center", paddingRight: spacing.lg },
  clearText: { color: c.brandSecondary, fontSize: 13 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, minHeight: 64, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border },
  name: { fontSize: 16 },
  done: { textDecorationLine: "line-through", color: c.muted },
  meta: { fontSize: 13, color: c.muted },
  price: { fontSize: 17 },
  dealPrice: { color: c.brandSecondary },
  was: { fontSize: 12, color: c.muted, textDecorationLine: "line-through" },
}));
