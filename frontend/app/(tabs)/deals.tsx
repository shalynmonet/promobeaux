import { Image } from "expo-image";
import * as WebBrowser from "expo-web-browser";
import { useRouter } from "expo-router";
import { ArrowSquareOut, BellRinging, BellSimple, Clock, Newspaper } from "phosphor-react-native";
import { useMemo, useState } from "react";
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { daysLeft, Deal, expiryLabel, money, useDeals, useMe, useToggleReminder } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { CHECK_BAR_HEIGHT, CheckDealsBar } from "@/src/components/check-deals-bar";
import { Houndstooth } from "@/src/components/houndstooth";
import { Button, Chip, haptic, PressScale, StoreAvatar, Txt } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

const EMPTY_IMG = "https://images.pexels.com/photos/15491784/pexels-photo-15491784.jpeg?auto=compress&cs=tinysrgb&w=800";
const ENDING_SOON = "Ending soon";

function badgeText(d: Deal) {
  if (d.promo_type === "bogo") return "BOGO";
  return `${Math.round(d.pct_off)}% off`;
}

const PROMO_LABEL: Record<Deal["promo_type"], string> = { sale: "Sale price", bogo: "Buy 1 Get 1", coupon: "Coupon", cashback: "Cash back" };

function DealCard({ deal, index }: { deal: Deal; index: number }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const toggle = useToggleReminder();
  const banner = useBanner();
  const expiry = expiryLabel(deal);
  const open = () => deal.source_url && WebBrowser.openBrowserAsync(deal.source_url);
  const remind = () => {
    haptic();
    toggle.mutate(
      { item_id: deal.item_id, store: deal.store },
      {
        onSuccess: (r) => {
          // When the reminder fires right away (deal ends today/tomorrow) the alert banner says it all.
          if (r.sent > 0) return;
          banner({
            tone: "success",
            title: r.remind ? `We'll remind you about ${deal.item_name}` : "Reminder removed",
            message: r.remind
              ? deal.ends_at
                ? "You'll get an alert the day before this deal ends."
                : "We'll alert you once we know when this deal ends."
              : undefined,
          });
        },
        onError: (e) => banner({ tone: "error", title: "Couldn't update reminder", message: e.message }),
      },
    );
  };
  return (
    <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 60).springify().damping(18)}>
      <PressScale testID={`deal-card-${deal.id}`} onPress={open} style={styles.card}>
        <View style={[styles.tile, index % 3 === 1 && styles.tileTall]}>
          <View style={styles.badge}>
            <Txt medium testID={`deal-badge-${deal.id}`} style={styles.badgeText}>{badgeText(deal)}</Txt>
          </View>
          <Txt style={styles.promoType}>
            {PROMO_LABEL[deal.promo_type]}
            {deal.source_kind === "weekly_ad" ? " · Weekly ad" : ""}
          </Txt>
          <Pressable
            testID={`deal-remind-${deal.id}`}
            onPress={remind}
            disabled={toggle.isPending}
            style={[styles.remindBtn, deal.remind && styles.remindOn]}
            accessibilityRole="switch"
            accessibilityState={{ checked: !!deal.remind }}
            aria-checked={!!deal.remind}
            accessibilityLabel={deal.remind ? "Reminder on" : "Remind me before it ends"}
          >
            {deal.remind ? (
              <BellRinging size={18} color={colors.onBrandPrimary} weight="fill" />
            ) : (
              <BellSimple size={18} color={colors.brandSecondary} />
            )}
          </Pressable>
          <Houndstooth height={8} style={styles.tileBand} />
        </View>
        <View style={styles.cardBody}>
          <Txt medium style={styles.name} numberOfLines={2}>{deal.item_name}</Txt>
          {!!(deal.brand || deal.size) && (
            <Txt style={styles.meta} numberOfLines={1}>{[deal.brand, deal.size].filter(Boolean).join(" · ")}</Txt>
          )}
          <View style={styles.priceRow}>
            <Txt medium style={styles.price}>{money(deal.sale_price)}</Txt>
            <Txt style={styles.was}>{money(deal.usual_price)}</Txt>
          </View>
          <Txt medium style={styles.save}>Save {money(deal.savings)}</Txt>
          {!!deal.promo_text && <Txt style={styles.promo} numberOfLines={3}>{deal.promo_text}</Txt>}
          <View style={[styles.expiryPill, expiry?.urgent && styles.expiryUrgent]}>
            <Clock size={13} color={expiry?.urgent ? colors.onSurface : colors.muted} weight={expiry?.urgent ? "fill" : "regular"} />
            <Txt testID={`deal-expiry-${deal.id}`} style={[styles.expiryText, expiry?.urgent && styles.expiryTextUrgent]} numberOfLines={1}>
              {expiry?.text ?? "End date unknown"}
            </Txt>
          </View>
          <View style={styles.footer}>
            <StoreAvatar store={deal.store} size={22} />
            <Txt style={styles.store} numberOfLines={1}>{deal.store}</Txt>
            {deal.is_sample ? (
              <Txt style={styles.sample}>Sample</Txt>
            ) : (
              <ArrowSquareOut size={16} color={colors.muted} />
            )}
          </View>
        </View>
      </PressScale>
    </Animated.View>
  );
}

export default function DealsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const me = useMe();
  const deals = useDeals();
  const [store, setStore] = useState("All");

  const filtered = useMemo(() => {
    const list = deals.data ?? [];
    if (store === ENDING_SOON) {
      // Deals ending within 2 days, soonest first.
      return list
        .filter((d) => {
          const left = daysLeft(d);
          return left !== null && left <= 2;
        })
        .sort((a, b) => (daysLeft(a) ?? 99) - (daysLeft(b) ?? 99));
    }
    return list.filter((d) => store === "All" || d.store === store);
  }, [deals.data, store]);
  // Same rule as the Savings screen: count only the best deal per item.
  const total = Object.values(
    filtered.reduce<Record<string, number>>((acc, d) => ({ ...acc, [d.item_id]: Math.max(acc[d.item_id] ?? 0, d.savings) }), {}),
  ).reduce((s, v) => s + v, 0);
  const cols = [filtered.filter((_, i) => i % 2 === 0), filtered.filter((_, i) => i % 2 === 1)];
  const chips = ["All", ENDING_SOON, ...(me.data?.stores ?? [])];

  return (
    <View style={styles.root} testID="deals-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View style={styles.kickerRow}>
          <Txt style={styles.kicker}>Near {me.data?.zip ?? "—"}</Txt>
          <Pressable testID="deals-weekly-ads-button" onPress={() => router.push("/ads")} style={styles.adsBtn}>
            <Newspaper size={16} color={colors.onBrandTertiary} />
            <Txt medium style={styles.adsBtnText}>Weekly ads</Txt>
          </Pressable>
        </View>
        <View style={styles.titleRow}>
          <Txt style={styles.title}>This week&apos;s deals</Txt>
          {filtered.length > 0 && <Txt medium testID="deals-total-savings" style={styles.total}>{money(total)} off</Txt>}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chipContent}>
          {chips.map((c) => (
            <Chip key={c} testID={`deals-filter-${c.toLowerCase().replace(/\W/g, "")}`} label={c} selected={store === c} onPress={() => setStore(c)} />
          ))}
        </ScrollView>
      </View>
      <Houndstooth height={10} testID="deals-header-houndstooth" />

      {deals.isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} size="large" /></View>
      ) : deals.error ? (
        <View style={styles.center}>
          <Txt testID="deals-error" style={styles.emptyText}>Couldn&apos;t load deals. {deals.error.message}</Txt>
          <Button testID="deals-retry-button" label="Retry" variant="secondary" onPress={() => deals.refetch()} />
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: CHECK_BAR_HEIGHT + bottomChrome + spacing.lg }}
          refreshControl={<RefreshControl refreshing={deals.isRefetching} onRefresh={() => deals.refetch()} tintColor={colors.brandPrimary} />}
        >
          {filtered.length === 0 ? (
            <View style={styles.empty} testID="deals-empty">
              <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" transition={300} />
              <Txt style={styles.emptyTitle}>{store === ENDING_SOON ? "Nothing ending soon" : "No deals yet"}</Txt>
              <Txt style={styles.emptyText}>
                {store === ENDING_SOON
                  ? "None of your deals end in the next 2 days. Tap the bell on a deal to get a reminder before it ends."
                  : "Tap \"Check deals now\" and we'll scan this week's ads for your watchlist."}
              </Txt>
            </View>
          ) : (
            <View style={styles.masonry}>
              {cols.map((col, ci) => (
                <View key={ci} style={styles.col}>
                  {col.map((d, i) => <DealCard key={d.id} deal={d} index={i * 2 + ci} />)}
                </View>
              ))}
            </View>
          )}
        </ScrollView>
      )}
      <CheckDealsBar testID="deals-check-now-button" />
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: spacing.lg, backgroundColor: c.surface },
  kicker: { color: c.muted, fontSize: 13 },
  kickerRow: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  adsBtn: { flexDirection: "row", alignItems: "center", gap: 6, minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: c.brandTertiary },
  adsBtnText: { fontSize: 13, color: c.onBrandTertiary },
  titleRow: { flexDirection: "row", alignItems: "baseline", justifyContent: "space-between", gap: spacing.sm },
  title: { fontSize: 26, letterSpacing: -0.5 },
  total: { fontSize: 16, color: c.brandPrimary },
  chipRow: { height: 56, flexGrow: 0, marginHorizontal: -spacing.lg },
  chipContent: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.lg, padding: spacing.xl },
  masonry: { flexDirection: "row", gap: spacing.md },
  col: { flex: 1, gap: spacing.md },
  card: {
    backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, overflow: "hidden", borderWidth: 1, borderColor: c.border,
    shadowColor: c.shadow, shadowOpacity: 0.06, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 2,
  },
  tile: { height: 88, backgroundColor: c.brandTertiary, padding: spacing.md, justifyContent: "space-between" },
  tileTall: { height: 112 },
  tileBand: { position: "absolute", left: 0, right: 0, bottom: 0 },
  badge: { alignSelf: "flex-start", backgroundColor: c.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.md, paddingVertical: spacing.xs },
  badgeText: { color: c.onBrandPrimary, fontSize: 16 },
  promoType: { color: c.onBrandTertiary, fontSize: 12 },
  cardBody: { padding: spacing.md, gap: spacing.xs },
  name: { fontSize: 15, lineHeight: 20 },
  meta: { fontSize: 12, color: c.muted },
  priceRow: { flexDirection: "row", alignItems: "baseline", gap: spacing.sm, marginTop: spacing.xs },
  price: { fontSize: 22, letterSpacing: -0.4 },
  was: { fontSize: 13, color: c.muted, textDecorationLine: "line-through" },
  save: { fontSize: 13, color: c.brandSecondary },
  promo: { fontSize: 12, color: c.muted, lineHeight: 17 },
  expiryPill: { alignSelf: "flex-start", maxWidth: "100%", flexDirection: "row", alignItems: "center", gap: 4, marginTop: spacing.xs, paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.pill, backgroundColor: c.surfaceTertiary },
  expiryUrgent: { backgroundColor: c.warning },
  expiryText: { flexShrink: 1, fontSize: 12, color: c.muted },
  expiryTextUrgent: { color: c.onSurface },
  remindBtn: { position: "absolute", top: spacing.xs, right: spacing.xs, width: 44, height: 44, borderRadius: 22, alignItems: "center", justifyContent: "center", backgroundColor: c.surfaceSecondary },
  remindOn: { backgroundColor: c.brandPrimary },
  footer: { flexDirection: "row", alignItems: "center", gap: spacing.sm, marginTop: spacing.sm, paddingTop: spacing.sm, borderTopWidth: 1, borderTopColor: c.divider },
  store: { flex: 1, fontSize: 13 },
  sample: { fontSize: 11, color: c.onSurfaceTertiary, backgroundColor: c.surfaceTertiary, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, overflow: "hidden" },
  empty: { alignItems: "center", gap: spacing.md, paddingTop: spacing.lg },
  emptyImg: { width: "100%", height: 180, borderRadius: radius.lg },
  emptyTitle: { fontSize: 20 },
  emptyText: { color: c.muted, textAlign: "center", fontSize: 15, lineHeight: 22 },
}));
