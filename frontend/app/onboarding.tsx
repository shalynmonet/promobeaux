import { useQueryClient } from "@tanstack/react-query";
import { BlurView } from "expo-blur";
import { useLocalSearchParams, useRouter } from "expo-router";
import { CheckCircle } from "phosphor-react-native";
import { useEffect, useRef, useState } from "react";
import { TextInput, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useApi, useMe, User } from "@/src/api";
import { Button, haptic, PressScale, StoreAvatar, Txt } from "@/src/components/ui";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

const STORES = ["Kroger", "Walmart", "Target", "Aldi", "H-E-B", "Tom Thumb", "Sprouts"];

export default function Onboarding() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { edit } = useLocalSearchParams<{ edit?: string }>();
  const api = useApi();
  const qc = useQueryClient();
  const me = useMe();
  const [zip, setZip] = useState("");
  const [stores, setStores] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const prefilled = useRef(false);
  useEffect(() => {
    if (me.data?.onboarded && !prefilled.current) {
      prefilled.current = true;
      setZip(me.data.zip);
      setStores(me.data.stores);
    }
  }, [me.data]);

  const toggle = (s: string) => {
    haptic();
    setStores((cur) => (cur.includes(s) ? cur.filter((x) => x !== s) : cur.length >= 4 ? cur : [...cur, s]));
  };

  const valid = /^\d{5}$/.test(zip) && stores.length >= 2 && stores.length <= 4;

  const save = async () => {
    setError("");
    setSaving(true);
    try {
      const user = await api<User>("/me/onboarding", { method: "PUT", body: JSON.stringify({ zip, stores }) });
      qc.setQueryData(["me"], user);
      ["deals", "savings", "alerts", "trip"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      if (edit) router.back();
      else router.replace("/(tabs)/watchlist");
    } catch (e: any) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <View style={styles.root} testID="onboarding-screen">
      <KeyboardAwareScrollView
        bottomOffset={110}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + 120, paddingHorizontal: spacing.xl, gap: spacing.lg }}
      >
        <Txt style={styles.kicker}>{edit ? "Your stores" : "Let's get you saving"}</Txt>
        <Txt style={styles.title}>Where do you shop?</Txt>
        <Txt style={styles.sub}>We&apos;ll check weekly ads and coupons near you.</Txt>

        <Txt medium style={styles.label}>ZIP code</Txt>
        <TextInput
          testID="onboarding-zip-input"
          value={zip}
          onChangeText={(t) => setZip(t.replace(/\D/g, "").slice(0, 5))}
          placeholder="e.g. 75201"
          placeholderTextColor={colors.muted}
          keyboardType="number-pad"
          maxLength={5}
          style={styles.zip}
        />

        <View style={styles.labelRow}>
          <Txt medium style={styles.label}>Pick 2–4 stores</Txt>
          <Txt testID="onboarding-store-count" style={styles.count}>{stores.length}/4</Txt>
        </View>
        <View style={styles.grid}>
          {STORES.map((s) => {
            const on = stores.includes(s);
            return (
              <PressScale key={s} testID={`store-option-${s.toLowerCase().replace(/\W/g, "")}`} onPress={() => toggle(s)} style={[styles.tile, on && styles.tileOn]}
                accessibilityRole="checkbox" accessibilityState={{ checked: on }} accessibilityLabel={s}>
                <StoreAvatar store={s} size={40} />
                <Txt medium style={styles.tileText}>{s}</Txt>
                {on && (
                  <View style={styles.check}>
                    <CheckCircle size={22} color={colors.brandPrimary} weight="fill" />
                  </View>
                )}
              </PressScale>
            );
          })}
        </View>
        {!!error && <Txt testID="onboarding-error" style={styles.error}>{error}</Txt>}
      </KeyboardAwareScrollView>

      <KeyboardStickyView offset={{ opened: insets.bottom }} style={styles.sticky}>
        <BlurView intensity={40} tint="light" style={[styles.glass, { paddingBottom: insets.bottom + spacing.lg }]}>
          <Button testID="onboarding-continue-button" label={edit ? "Save stores" : "Start saving"} onPress={save} loading={saving} disabled={!valid} />
        </BlurView>
      </KeyboardStickyView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  kicker: { color: c.brandSecondary, fontSize: 14 },
  title: { fontSize: 32, lineHeight: 40, letterSpacing: -0.6, marginTop: -spacing.sm },
  sub: { fontSize: 15, color: c.muted, marginTop: -spacing.sm },
  label: { fontSize: 16 },
  labelRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.sm },
  count: { color: c.muted },
  zip: {
    height: 64, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border,
    paddingHorizontal: spacing.xl, fontSize: 24, letterSpacing: 4, fontFamily: fonts.medium, color: c.onSurface,
  },
  grid: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  tile: {
    width: "47.5%", padding: spacing.lg, borderRadius: radius.lg, backgroundColor: c.surfaceSecondary,
    borderWidth: 1.5, borderColor: c.border, gap: spacing.md, minHeight: 104,
  },
  tileOn: { borderColor: c.brandPrimary, backgroundColor: c.brandTertiary },
  tileText: { fontSize: 16 },
  check: { position: "absolute", top: spacing.md, right: spacing.md },
  error: { color: c.error },
  sticky: { position: "absolute", left: 0, right: 0, bottom: 0 },
  glass: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, borderTopWidth: 1, borderTopColor: c.border, overflow: "hidden" },
}));
