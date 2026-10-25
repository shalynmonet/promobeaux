import { Bell, CheckCircle, WarningCircle, X } from "phosphor-react-native";
import { createContext, ReactNode, useCallback, useContext, useRef, useState } from "react";
import { Pressable, View } from "react-native";
import Animated, { FadeInUp, FadeOutUp } from "react-native-reanimated";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { Txt } from "@/src/components/ui";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

type BannerOpts = {
  title: string;
  message?: string;
  tone?: "deal" | "success" | "error";
  actionLabel?: string;
  onAction?: () => void;
  onPress?: () => void;
  onDismiss?: () => void;
  sticky?: boolean;
  duration?: number; // ms; banners with an action stay until dismissed unless this is set
};

const BannerCtx = createContext<(o: BannerOpts) => void>(() => {});

export function BannerProvider({ children }: { children: ReactNode }) {
  const [banner, setBanner] = useState<(BannerOpts & { key: number }) | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const insets = useSafeAreaInsets();
  const styles = useStyles();
  const { colors } = useTheme();

  const show = useCallback((o: BannerOpts) => {
    if (timer.current) clearTimeout(timer.current);
    setBanner({ ...o, key: Date.now() });
    const ms = o.duration ?? (o.sticky || o.actionLabel ? null : 4500);
    if (ms) timer.current = setTimeout(() => setBanner(null), ms);
  }, []);

  const close = () => {
    banner?.onDismiss?.();
    setBanner(null);
  };

  const Icon = banner?.tone === "error" ? WarningCircle : banner?.tone === "success" ? CheckCircle : Bell;
  const iconColor = banner?.tone === "error" ? colors.error : colors.brandPrimary;

  return (
    <BannerCtx.Provider value={show}>
      {children}
      {banner && (
        <Animated.View
          key={banner.key}
          entering={FadeInUp.springify().damping(16)}
          exiting={FadeOutUp}
          style={[styles.wrap, { top: insets.top + spacing.sm }]}
          pointerEvents="box-none"
        >
          <Pressable
            testID="in-app-banner"
            style={styles.card}
            onPress={() => {
              banner.onPress?.();
              if (banner.onPress) setBanner(null);
            }}
          >
            <View style={styles.iconWrap}>
              <Icon size={22} color={iconColor} weight="fill" />
            </View>
            <View style={styles.body}>
              <Txt medium style={styles.title} numberOfLines={2}>{banner.title}</Txt>
              {!!banner.message && <Txt style={styles.msg} numberOfLines={2}>{banner.message}</Txt>}
              {!!banner.actionLabel && (
                <Pressable
                  testID="in-app-banner-action"
                  onPress={() => {
                    banner.onAction?.();
                    setBanner(null);
                  }}
                  style={styles.action}
                >
                  <Txt medium style={styles.actionText}>{banner.actionLabel}</Txt>
                </Pressable>
              )}
            </View>
            <Pressable testID="in-app-banner-close" onPress={close} hitSlop={12} style={styles.close}>
              <X size={18} color={colors.muted} />
            </Pressable>
          </Pressable>
        </Animated.View>
      )}
    </BannerCtx.Provider>
  );
}

export const useBanner = () => useContext(BannerCtx);

const useStyles = makeStyles((c) => ({
  wrap: { position: "absolute", left: spacing.lg, right: spacing.lg },
  card: {
    flexDirection: "row", alignItems: "flex-start", gap: spacing.md, padding: spacing.lg,
    backgroundColor: c.surfaceSecondary, borderRadius: radius.lg, borderWidth: 1, borderColor: c.border,
    shadowColor: c.shadow, shadowOpacity: 0.12, shadowRadius: 16, shadowOffset: { width: 0, height: 6 }, elevation: 6,
  },
  iconWrap: { width: 36, height: 36, borderRadius: 18, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center" },
  body: { flex: 1, gap: 2 },
  title: { fontSize: 15 },
  msg: { fontSize: 13, color: c.muted },
  action: { alignSelf: "flex-start", marginTop: spacing.sm, minHeight: 44, minWidth: 72, justifyContent: "center", alignItems: "center", paddingHorizontal: spacing.lg, borderRadius: radius.pill, backgroundColor: c.brandPrimary },
  actionText: { color: c.onBrandPrimary, fontSize: 13 },
  close: { padding: 2 },
}));
