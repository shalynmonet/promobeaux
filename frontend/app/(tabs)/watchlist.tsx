import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Plus, Trash } from "phosphor-react-native";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, View } from "react-native";
import Animated, { FadeInDown, LinearTransition } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Item, money, useDeals, useDeleteItem, useRestoreItem, useWatchlist } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { Button, PressScale, Txt } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

const EMPTY_IMG = "https://images.unsplash.com/photo-1628102491629-778571d893a3?crop=entropy&cs=srgb&fm=jpg&q=80&w=900";

export default function WatchlistScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const router = useRouter();
  const list = useWatchlist();
  const deals = useDeals();
  const del = useDeleteItem();
  const restore = useRestoreItem();
  const banner = useBanner();

  const onSale = new Set((deals.data ?? []).map((d) => d.item_id));

  const edit = (it: Item) =>
    router.push({
      pathname: "/add-item",
      params: { id: it.id, name: it.name, brand: it.brand, size: it.size, usual_price: String(it.usual_price), barcode: it.barcode },
    });

  const remove = (it: Item) =>
    del.mutate(it.id, {
      onSuccess: () =>
        banner({
          tone: "success",
          title: `Removed ${it.name}`,
          message: "Changed your mind?",
          actionLabel: "Undo",
          duration: 6000,
          onAction: () =>
            restore.mutate(it.id, {
              onSuccess: () => banner({ tone: "success", title: `${it.name} is back on your list` }),
              onError: (e) => banner({ tone: "error", title: "Couldn't restore item", message: e.message }),
            }),
        }),
      onError: (e) => banner({ tone: "error", title: "Couldn't remove item", message: e.message }),
    });

  const renderItem = ({ item, index }: { item: Item; index: number }) => (
    <Animated.View entering={FadeInDown.delay(Math.min(index, 8) * 50)} layout={LinearTransition}>
      <PressScale testID={`watchlist-item-${item.id}`} onPress={() => edit(item)} style={styles.card}>
        <View style={styles.cardMain}>
          <View style={styles.nameRow}>
            <Txt medium style={styles.name} numberOfLines={1}>{item.name}</Txt>
            {onSale.has(item.id) && <Txt medium style={styles.saleTag}>On sale</Txt>}
          </View>
          <Txt style={styles.meta} numberOfLines={1}>{[item.brand, item.size].filter(Boolean).join(" · ") || "Any brand"}</Txt>
        </View>
        <View style={styles.priceCol}>
          <Txt style={styles.usualLabel}>Usually</Txt>
          <Txt medium style={styles.price}>{money(item.usual_price)}</Txt>
        </View>
        <Pressable testID={`watchlist-delete-${item.id}`} onPress={() => remove(item)} accessibilityLabel={`Remove ${item.name}`} style={styles.trash}>
          <Trash size={20} color={colors.muted} />
        </Pressable>
      </PressScale>
    </Animated.View>
  );

  return (
    <View style={styles.root} testID="watchlist-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Txt style={styles.kicker}>{list.data?.length ?? 0} items tracked</Txt>
        <Txt style={styles.title}>Your watchlist</Txt>
      </View>
      {list.isLoading ? (
        <View style={styles.center}><ActivityIndicator color={colors.brandPrimary} size="large" /></View>
      ) : list.error ? (
        <View style={styles.center}>
          <Txt testID="watchlist-error" style={styles.emptyText}>Couldn&apos;t load your list. {list.error.message}</Txt>
          <Button testID="watchlist-retry-button" label="Retry" variant="secondary" onPress={() => list.refetch()} />
        </View>
      ) : (
        <FlatList
          data={list.data}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.md, paddingBottom: bottomChrome + 104 }}
          refreshControl={<RefreshControl refreshing={list.isRefetching} onRefresh={() => list.refetch()} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={
            <View style={styles.empty} testID="watchlist-empty">
              <Image source={{ uri: EMPTY_IMG }} style={styles.emptyImg} contentFit="cover" transition={300} />
              <Txt style={styles.emptyTitle}>Your basket is empty</Txt>
              <Txt style={styles.emptyText}>Add the groceries you buy every week. We&apos;ll tell you when they drop.</Txt>
              <Button testID="watchlist-add-first-button" label="Add your first item" onPress={() => router.push("/add-item")} />
            </View>
          }
        />
      )}
      <PressScale
        testID="watchlist-add-fab"
        hapticFeedback
        onPress={() => router.push("/add-item")}
        style={[styles.fab, { bottom: bottomChrome + spacing.lg }]}
      >
        <Plus size={26} color={colors.onBrandPrimary} weight="bold" />
      </PressScale>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, borderBottomWidth: 1, borderBottomColor: c.divider },
  kicker: { color: c.muted, fontSize: 13 },
  title: { fontSize: 26, letterSpacing: -0.5 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.lg, padding: spacing.xl },
  card: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, minHeight: 76,
    backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border,
  },
  cardMain: { flex: 1, gap: 2 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  name: { fontSize: 16, flexShrink: 1 },
  saleTag: { flexShrink: 0, fontSize: 11, color: c.onBrandTertiary, backgroundColor: c.brandTertiary, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, overflow: "hidden" },
  meta: { fontSize: 13, color: c.muted },
  priceCol: { alignItems: "flex-end" },
  usualLabel: { fontSize: 11, color: c.muted },
  price: { fontSize: 18 },
  trash: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginRight: -spacing.sm },
  fab: {
    position: "absolute", right: spacing.lg, width: 60, height: 60, borderRadius: 30, backgroundColor: c.brandPrimary,
    alignItems: "center", justifyContent: "center",
    shadowColor: c.shadow, shadowOpacity: 0.2, shadowRadius: 12, shadowOffset: { width: 0, height: 6 }, elevation: 6,
  },
  empty: { alignItems: "center", gap: spacing.md },
  emptyImg: { width: "100%", height: 180, borderRadius: radius.lg },
  emptyTitle: { fontSize: 20 },
  emptyText: { color: c.muted, textAlign: "center", fontSize: 15, lineHeight: 22 },
}));
