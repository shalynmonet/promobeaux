import * as Haptics from "expo-haptics";
import { ReactNode } from "react";
import { AccessibilityRole, AccessibilityState, ActivityIndicator, Platform, Pressable, StyleProp, Text, TextProps, TextStyle, View, ViewStyle } from "react-native";
import Animated, { useAnimatedStyle, useSharedValue, withSpring } from "react-native-reanimated";

import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

export function Txt({ style, medium, ...rest }: TextProps & { medium?: boolean }) {
  const { colors } = useTheme();
  return (
    <Text
      {...rest}
      style={[{ fontFamily: medium ? fonts.medium : fonts.regular, color: colors.onSurface, fontSize: 14 }, style]}
    />
  );
}

export const haptic = () => {
  if (Platform.OS !== "web") Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
};

const AnimatedPressable = Animated.createAnimatedComponent(Pressable);

export function PressScale({ children, style, onPress, disabled, testID, hapticFeedback, accessibilityRole, accessibilityState, accessibilityLabel }: {
  children: ReactNode; style?: StyleProp<ViewStyle>; onPress?: () => void; disabled?: boolean; testID?: string; hapticFeedback?: boolean;
  accessibilityRole?: AccessibilityRole; accessibilityState?: AccessibilityState; accessibilityLabel?: string;
}) {
  const scale = useSharedValue(1);
  const anim = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  return (
    <AnimatedPressable
      testID={testID}
      disabled={disabled}
      accessibilityRole={accessibilityRole ?? "button"}
      accessibilityState={accessibilityState ?? { disabled: !!disabled }}
      accessibilityLabel={accessibilityLabel}
      aria-checked={accessibilityState?.checked as boolean | undefined}
      onPressIn={() => (scale.value = withSpring(0.96, { damping: 15 }))}
      onPressOut={() => (scale.value = withSpring(1, { damping: 15 }))}
      onPress={() => {
        if (hapticFeedback) haptic();
        onPress?.();
      }}
      style={[style, anim]}
    >
      {children}
    </AnimatedPressable>
  );
}

export function Button({ label, onPress, variant = "primary", loading, disabled, icon, testID, style }: {
  label: string; onPress?: () => void; variant?: "primary" | "secondary" | "ghost"; loading?: boolean;
  disabled?: boolean; icon?: ReactNode; testID?: string; style?: StyleProp<ViewStyle>;
}) {
  const styles = useStyles();
  const { colors } = useTheme();
  const bg = variant === "primary" ? styles.primary : variant === "secondary" ? styles.secondary : styles.ghost;
  const fg = variant === "primary" ? colors.onBrandPrimary : variant === "secondary" ? colors.onBrandTertiary : colors.onSurface;
  return (
    <PressScale testID={testID} onPress={onPress} disabled={disabled || loading} style={[styles.btn, bg, (disabled || loading) && styles.disabled, style]}>
      {loading ? <ActivityIndicator color={fg} /> : icon}
      <Txt medium style={[styles.btnLabel, { color: fg } as TextStyle]}>{label}</Txt>
    </PressScale>
  );
}

export function StoreAvatar({ store, size = 32 }: { store: string; size?: number }) {
  const styles = useStyles();
  const words = store.split(" ").filter(Boolean);
  const initials = words.length > 1 ? words.map((w) => w[0]).join("").slice(0, 2) : store.charAt(0);
  return (
    <View style={[styles.avatar, { width: size, height: size, borderRadius: size / 2 }]}>
      <Txt medium style={[styles.avatarText, { fontSize: size * (initials.length > 1 ? 0.36 : 0.45) }]}>{initials}</Txt>
    </View>
  );
}

export function Chip({ label, selected, onPress, testID }: { label: string; selected: boolean; onPress: () => void; testID?: string }) {
  const styles = useStyles();
  return (
    <Pressable testID={testID} onPress={onPress} hitSlop={{ top: 4, bottom: 4 }} style={[styles.chip, selected && styles.chipSelected]}>
      <Txt medium style={[styles.chipText, selected && styles.chipTextSelected]}>{label}</Txt>
    </Pressable>
  );
}

const useStyles = makeStyles((c) => ({
  btn: {
    minHeight: 54, borderRadius: radius.pill, flexDirection: "row", alignItems: "center",
    justifyContent: "center", gap: spacing.sm, paddingHorizontal: spacing.xl,
  },
  primary: { backgroundColor: c.brandPrimary },
  secondary: { backgroundColor: c.brandTertiary },
  ghost: { backgroundColor: "transparent", borderWidth: 1, borderColor: c.border },
  disabled: { opacity: 0.5 },
  btnLabel: { fontSize: 16 },
  avatar: { backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  avatarText: { color: c.onSurfaceInverse },
  chip: {
    height: 36, flexShrink: 0, paddingHorizontal: spacing.lg, borderRadius: radius.pill, justifyContent: "center",
    backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border,
  },
  chipSelected: { backgroundColor: c.brandPrimary, borderColor: c.brandPrimary },
  chipText: { fontSize: 14, color: c.onSurface },
  chipTextSelected: { color: c.onBrandPrimary },
}));
