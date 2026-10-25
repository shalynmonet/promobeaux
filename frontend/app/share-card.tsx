import { Image } from "expo-image";
import * as Sharing from "expo-sharing";
import { useRouter } from "expo-router";
import { ShareNetwork, X } from "phosphor-react-native";
import { useRef, useState } from "react";
import { Platform, Pressable, Share, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { captureRef } from "react-native-view-shot";

import { money, useMe, useSavings } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { Houndstooth } from "@/src/components/houndstooth";
import { Button, Txt } from "@/src/components/ui";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

export default function ShareCard() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const banner = useBanner();
  const savings = useSavings();
  const me = useMe();
  const cardRef = useRef<View>(null);
  const [busy, setBusy] = useState(false);

  const s = savings.data;
  const total = s?.total ?? 0;
  const stores = s?.by_store.map((b) => b.store) ?? me.data?.stores ?? [];
  const message = `I could save ${money(total)} on groceries this week with Promobeaux — it watches the weekly ads at ${stores.slice(0, 3).join(", ")} for me.`;

  const shareText = async () => {
    try {
      await Share.share({ message });
    } catch {
      banner({ tone: "error", title: "Sharing isn't available here", message: "Open Promobeaux on your phone to share." });
    }
  };

  const shareImage = async () => {
    setBusy(true);
    try {
      if (Platform.OS === "web" || !(await Sharing.isAvailableAsync())) {
        await shareText();
        return;
      }
      const uri = await captureRef(cardRef, { format: "png", quality: 1, result: "tmpfile" });
      await Sharing.shareAsync(uri, { mimeType: "image/png", dialogTitle: "Share your savings", UTI: "public.png" });
    } catch {
      await shareText();
    } finally {
      setBusy(false);
    }
  };

  return (
    <View style={[styles.root, { paddingBottom: insets.bottom + spacing.lg }]} testID="share-card-screen">
      <View style={styles.header}>
        <Txt style={styles.title}>Share your savings</Txt>
        <Pressable testID="share-card-close-button" onPress={() => router.back()} hitSlop={12} style={styles.close}>
          <X size={22} color={colors.onSurface} />
        </Pressable>
      </View>

      <View style={styles.center}>
        <View ref={cardRef} collapsable={false} style={styles.card} testID="share-card-preview">
          <View style={[styles.blob, styles.blobA]} />
          <View style={[styles.blob, styles.blobB]} />
          <View style={styles.brandRow}>
            <Image source={require("../assets/images/brand/logo-wordmark.png")} style={styles.wordmark} contentFit="contain" />
          </View>
          <Txt style={styles.kicker}>I saved</Txt>
          <Txt medium testID="share-card-total" style={styles.amount} adjustsFontSizeToFit numberOfLines={1}>{money(total)}</Txt>
          <Txt style={styles.kicker}>on groceries this week</Txt>
          <View style={styles.wins}>
            {(s?.top ?? []).slice(0, 3).map((d) => (
              <View key={d.id} style={styles.winRow}>
                <Txt style={styles.winName} numberOfLines={1}>{d.item_name}</Txt>
                <Txt medium style={styles.winAmt}>−{money(d.savings)}</Txt>
              </View>
            ))}
          </View>
          <Txt style={styles.footer} numberOfLines={2}>
            {s?.deal_count ?? 0} deals found at {stores.slice(0, 3).join(" · ") || "my stores"}
          </Txt>
          <Houndstooth height={24} style={styles.band} testID="share-card-houndstooth" />
        </View>
      </View>

      <View style={styles.actions}>
        <Button testID="share-card-share-button" label="Share card" onPress={shareImage} loading={busy}
          icon={busy ? undefined : <ShareNetwork size={20} color={colors.onBrandPrimary} weight="bold" />} disabled={total <= 0} />
        <Button testID="share-card-text-button" label="Share as text" variant="ghost" onPress={shareText} disabled={total <= 0} />
        {total <= 0 && <Txt style={styles.hint}>Run a deal check first — there&apos;s nothing to brag about yet.</Txt>}
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingTop: spacing.lg },
  title: { fontSize: 24, letterSpacing: -0.4 },
  close: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  center: { flex: 1, justifyContent: "center", paddingHorizontal: spacing.xl },
  card: { backgroundColor: c.brandPrimary, borderRadius: radius.lg + 8, padding: spacing.xl, overflow: "hidden", gap: 2 },
  blob: { position: "absolute", borderRadius: 999, backgroundColor: c.brandSecondary },
  blobA: { width: 240, height: 240, top: -90, right: -80, opacity: 0.6 },
  blobB: { width: 140, height: 140, bottom: -50, left: -40, opacity: 0.45 },
  // Logo artwork sits on its own light background, so show it on a light pill.
  brandRow: { alignSelf: "center", backgroundColor: c.surface, borderRadius: radius.md, paddingHorizontal: spacing.md, paddingVertical: spacing.xs, marginBottom: spacing.lg },
  wordmark: { width: 150, height: 63 },
  kicker: { color: c.onBrandPrimary, fontSize: 18, opacity: 0.9 },
  amount: { color: c.onBrandPrimary, fontSize: 76, lineHeight: 88, letterSpacing: -3 },
  wins: { marginTop: spacing.lg, gap: spacing.xs, backgroundColor: c.brandSecondary, borderRadius: radius.md, padding: spacing.md },
  winRow: { flexDirection: "row", justifyContent: "space-between", gap: spacing.md },
  winName: { color: c.onBrandPrimary, flex: 1, fontSize: 14 },
  winAmt: { color: c.onBrandPrimary, fontSize: 14 },
  footer: { color: c.onBrandPrimary, opacity: 0.85, fontSize: 12, marginTop: spacing.md },
  band: { marginTop: spacing.lg, marginHorizontal: -spacing.xl, marginBottom: -spacing.xl },
  actions: { paddingHorizontal: spacing.xl, gap: spacing.md },
  hint: { color: c.muted, textAlign: "center", fontSize: 13 },
}));
