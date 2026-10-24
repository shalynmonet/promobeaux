import { BlurView } from "expo-blur";
import { useRouter } from "expo-router";
import { MagnifyingGlass } from "phosphor-react-native";
import { StyleProp, View, ViewStyle } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useCheckDeals } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { Button } from "@/src/components/ui";
import { usesNativeTabs } from "@/src/navigation";
import { makeStyles, spacing, useTheme } from "@/src/theme";

export const CHECK_BAR_HEIGHT = 86;

// Sticky glass "Check deals now" bar for tab screens.
export function CheckDealsBar({ testID, style }: { testID: string; style?: StyleProp<ViewStyle> }) {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const bottomChrome = usesNativeTabs ? insets.bottom : 0;
  const check = useCheckDeals();
  const banner = useBanner();
  const router = useRouter();

  const run = () =>
    check.mutate(undefined, {
      onSuccess: (r) =>
        banner({
          tone: r.found ? "deal" : "success",
          title: r.found ? `Found ${r.found} deal${r.found === 1 ? "" : "s"} on your list` : "No new deals right now",
          message: r.checked ? `Checked ${r.checked} item${r.checked === 1 ? "" : "s"} across your stores.` : "Add items to your watchlist first.",
          onPress: r.found ? () => router.navigate("/(tabs)/deals") : undefined,
        }),
      onError: (e) => banner({ tone: "error", title: "Couldn't check deals", message: e.message }),
    });

  return (
    <View style={[styles.wrap, { bottom: bottomChrome }, style]} pointerEvents="box-none">
      <BlurView intensity={40} tint="light" style={styles.glass}>
        <Button
          testID={testID}
          label={check.isPending ? "Searching weekly ads…" : "Check deals now"}
          loading={check.isPending}
          onPress={run}
          icon={check.isPending ? undefined : <MagnifyingGlass size={20} color={colors.onBrandPrimary} weight="bold" />}
        />
      </BlurView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  wrap: { position: "absolute", left: 0, right: 0 },
  glass: { paddingHorizontal: spacing.lg, paddingVertical: spacing.lg, overflow: "hidden", borderTopWidth: 1, borderTopColor: c.border },
}));
