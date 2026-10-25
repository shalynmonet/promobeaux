import { useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { CaretLeft, Plus } from "phosphor-react-native";
import { useMemo, useState } from "react";
import { ActivityIndicator, FlatList, Pressable, RefreshControl, ScrollView, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { AdLine, useAds, useMe, useRefreshAds } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { Houndstooth } from "@/src/components/houndstooth";
import { Button, Chip, Txt } from "@/src/components/ui";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

function ago(iso?: string) {
  if (!iso) return "";
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return "Updated just now";
  if (mins < 60) return `Updated ${mins} min ago`;
  return `Updated ${Math.round(mins / 60)}h ago`;
}

// Best-effort product name from an ad line, e.g. "Buy 2 Ortega Taco Shells, $3" -> "Ortega Taco Shells",
// "Organic large avocados: 2 for $4" -> "Organic large avocados".
function guessName(line: string) {
  let name = line.split("$")[0];
  name = name
    .replace(/^[\d)\s.-]+/, "")
    .replace(/^(buy|get)\s+\d+\s+/i, "")
    .replace(/[:\-–—,]?\s*\d+\s*(for|\/)?\s*$/i, "")
    .replace(/[:\-–—,]+\s*$/, "")
    .trim();
  return (name.length >= 3 ? name : line).slice(0, 60);
}

export default function AdsScreen() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const banner = useBanner();
  const me = useMe();
  const stores = useMemo(() => me.data?.stores ?? [], [me.data?.stores]);
  const [picked, setStore] = useState<string | undefined>(undefined);
  // Default to the first saved store until the shopper picks one.
  const store = picked && stores.includes(picked) ? picked : stores[0];

  const ads = useAds(store);
  const refresh = useRefreshAds();

  const watch = (line: AdLine) =>
    router.push({ pathname: "/add-item", params: { name: guessName(line.text) } });

  const renderLine = ({ item, index }: { item: AdLine; index: number }) => (
    <View style={styles.line} testID={`ad-line-${index}`}>
      <View style={{ flex: 1, gap: spacing.xs }}>
        {item.promo_type && <Txt medium style={styles.tag}>{item.promo_type === "bogo" ? "BOGO" : "Coupon"}</Txt>}
        <Txt style={styles.lineText}>{item.text}</Txt>
      </View>
      <View style={styles.lineRight}>
        {item.price != null && <Txt medium style={styles.price}>${item.price.toFixed(2)}</Txt>}
        <Pressable testID={`ad-watch-${index}`} onPress={() => watch(item)} style={styles.watch} accessibilityLabel="Add to watchlist">
          <Plus size={16} color={colors.onBrandTertiary} weight="bold" />
          <Txt medium style={styles.watchText}>Watch</Txt>
        </Pressable>
      </View>
    </View>
  );

  return (
    <View style={styles.root} testID="ads-screen">
      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <View style={styles.topRow}>
          <Pressable testID="ads-back-button" onPress={() => router.back()} hitSlop={8} style={styles.back}>
            <CaretLeft size={22} color={colors.onSurface} />
          </Pressable>
          <View style={{ flex: 1 }}>
            <Txt style={styles.title}>Weekly ads</Txt>
            <Txt style={styles.sub} testID="ads-updated">{ads.data ? ago(ads.data.retrieved_at) : `Near ${me.data?.zip ?? ""}`}</Txt>
          </View>
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chipRow} contentContainerStyle={styles.chipContent}>
          {stores.map((s) => (
            <Chip key={s} testID={`ads-store-${s.toLowerCase().replace(/\W/g, "")}`} label={s} selected={store === s} onPress={() => setStore(s)} />
          ))}
        </ScrollView>
      </View>
      <Houndstooth height={24} />

      {ads.isLoading || !store ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.brandPrimary} size="large" />
          <Txt style={styles.sub}>Reading this week&apos;s {store ?? ""} ad…</Txt>
        </View>
      ) : ads.error ? (
        <View style={styles.center}>
          <Txt testID="ads-error" style={styles.empty}>{ads.error.message}</Txt>
          <Button testID="ads-retry-button" label="Retry" variant="secondary" onPress={() => ads.refetch()} />
        </View>
      ) : (
        <FlatList
          data={ads.data?.lines ?? []}
          keyExtractor={(l, i) => `${i}-${l.text}`}
          renderItem={renderLine}
          contentContainerStyle={{ padding: spacing.lg, gap: spacing.sm, paddingBottom: insets.bottom + spacing.xl }}
          refreshControl={
            <RefreshControl
              refreshing={refresh.isPending}
              tintColor={colors.brandPrimary}
              onRefresh={() =>
                refresh.mutate(store, { onError: (e) => banner({ tone: "error", title: "Couldn't refresh the ad", message: e.message }) })
              }
            />
          }
          ListEmptyComponent={
            <Txt testID="ads-empty" style={styles.empty}>
              We couldn&apos;t find this week&apos;s {store} ad online yet. Pull down to try again later.
            </Txt>
          }
          ListFooterComponent={
            ads.data?.sources.length ? (
              <View style={styles.sources}>
                <Txt style={styles.sub}>Sources</Txt>
                {ads.data.sources.map((s) => (
                  <Pressable key={s.url} onPress={() => WebBrowser.openBrowserAsync(s.url)} testID={`ads-source-${s.url}`}>
                    <Txt style={styles.sourceLink} numberOfLines={1}>{s.title || s.url}</Txt>
                  </Pressable>
                ))}
              </View>
            ) : null
          }
        />
      )}
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { paddingHorizontal: spacing.lg, backgroundColor: c.surface },
  topRow: { flexDirection: "row", alignItems: "center", gap: spacing.xs },
  back: { width: 44, height: 44, alignItems: "center", justifyContent: "center", marginLeft: -spacing.md },
  title: { fontSize: 24, letterSpacing: -0.4 },
  sub: { fontSize: 13, color: c.muted },
  chipRow: { height: 56, flexGrow: 0, marginHorizontal: -spacing.lg },
  chipContent: { gap: spacing.sm, paddingHorizontal: spacing.lg, alignItems: "center" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.md, padding: spacing.xl },
  empty: { color: c.muted, textAlign: "center", fontSize: 15, lineHeight: 22, paddingTop: spacing.xl },
  line: { flexDirection: "row", gap: spacing.md, padding: spacing.lg, backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border },
  lineText: { fontSize: 14, lineHeight: 20 },
  tag: { alignSelf: "flex-start", fontSize: 11, color: c.onBrandPrimary, backgroundColor: c.brandPrimary, paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.pill, overflow: "hidden" },
  lineRight: { alignItems: "flex-end", justifyContent: "space-between", gap: spacing.sm },
  price: { fontSize: 18, color: c.brandSecondary },
  watch: { flexDirection: "row", alignItems: "center", gap: 4, minHeight: 36, paddingHorizontal: spacing.md, borderRadius: radius.pill, backgroundColor: c.brandTertiary },
  watchText: { fontSize: 13, color: c.onBrandTertiary },
  sources: { marginTop: spacing.lg, gap: spacing.xs },
  sourceLink: { fontSize: 13, color: c.brandSecondary },
}));
