import { useLocalSearchParams, useRouter } from "expo-router";
import { Barcode, X } from "phosphor-react-native";
import { useState } from "react";
import { Platform, Pressable, TextInput, View } from "react-native";
import { KeyboardAwareScrollView, KeyboardStickyView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useSaveItem } from "@/src/api";
import { useBanner } from "@/src/components/banner";
import { Button, PressScale, Txt } from "@/src/components/ui";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

type Params = { id?: string; name?: string; brand?: string; size?: string; usual_price?: string; barcode?: string; notFound?: string };

export default function AddItem() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const p = useLocalSearchParams<Params>();
  const save = useSaveItem();
  const banner = useBanner();
  const [name, setName] = useState(p.name ?? "");
  const [brand, setBrand] = useState(p.brand ?? "");
  const [size, setSize] = useState(p.size ?? "");
  const [price, setPrice] = useState(p.usual_price ?? "");
  const [error, setError] = useState("");

  const priceNum = parseFloat(price.replace(",", "."));
  const valid = name.trim().length > 0 && priceNum > 0 && priceNum < 1000;

  const submit = () => {
    setError("");
    save.mutate(
      { id: p.id, name: name.trim(), brand: brand.trim(), size: size.trim(), usual_price: Math.round(priceNum * 100) / 100, barcode: p.barcode ?? "" },
      {
        onSuccess: () => {
          banner({ tone: "success", title: p.id ? "Item updated" : `Watching ${name.trim()}`, message: p.id ? undefined : "We'll check it on your next deal scan." });
          router.back();
        },
        onError: (e) => setError(e.message),
      },
    );
  };

  const field = (label: string, value: string, set: (v: string) => void, testID: string, extra: object = {}) => (
    <View style={styles.field}>
      <Txt medium style={styles.label}>{label}</Txt>
      <TextInput testID={testID} value={value} onChangeText={set} placeholderTextColor={colors.muted} style={styles.input} {...extra} />
    </View>
  );

  return (
    <View style={styles.root} testID="add-item-screen">
      <View style={[styles.header, { paddingTop: spacing.lg }]}>
        <Txt style={styles.title}>{p.id ? "Edit item" : "Add an item"}</Txt>
        <Pressable testID="add-item-close-button" onPress={() => router.back()} hitSlop={12} style={styles.close}>
          <X size={22} color={colors.onSurface} />
        </Pressable>
      </View>
      <KeyboardAwareScrollView bottomOffset={110} keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.xl, paddingTop: spacing.sm, gap: spacing.lg, paddingBottom: 140 + insets.bottom }}>
        {!p.id && (
          <PressScale testID="add-item-scan-button" onPress={() => router.replace("/scan")} style={styles.scan}>
            <Barcode size={28} color={colors.onBrandTertiary} />
            <View style={{ flex: 1 }}>
              <Txt medium style={styles.scanTitle}>Scan a barcode</Txt>
              <Txt style={styles.scanSub}>Fill in name, brand and size automatically</Txt>
            </View>
          </PressScale>
        )}
        {p.notFound === "1" && (
          <Txt testID="add-item-not-found" style={styles.note}>We couldn&apos;t find that barcode. Type the details below.</Txt>
        )}
        {field("Item name", name, setName, "add-item-name-input", { placeholder: "e.g. Large eggs" })}
        <View style={styles.row}>
          <View style={{ flex: 1 }}>{field("Brand", brand, setBrand, "add-item-brand-input", { placeholder: "Optional" })}</View>
          <View style={{ flex: 1 }}>{field("Size", size, setSize, "add-item-size-input", { placeholder: "e.g. 12 ct" })}</View>
        </View>
        <View style={styles.field}>
          <Txt medium style={styles.label}>Usual price</Txt>
          <View style={styles.priceWrap}>
            <Txt medium style={styles.dollar}>$</Txt>
            <TextInput testID="add-item-price-input" value={price} onChangeText={(t) => setPrice(t.replace(/[^0-9.,]/g, ""))}
              placeholder="0.00" placeholderTextColor={colors.muted} keyboardType="decimal-pad" style={styles.priceInput} />
          </View>
          <Txt style={styles.hint}>We flag a real deal at 10%+ off this price, or any BOGO, coupon or cash back.</Txt>
        </View>
        {!!error && <Txt testID="add-item-error" style={styles.error}>{error}</Txt>}
      </KeyboardAwareScrollView>
      <KeyboardStickyView offset={{ opened: insets.bottom }} style={styles.sticky}>
        <View style={[styles.bar, { paddingBottom: insets.bottom + spacing.lg }]}>
          <Button testID="add-item-save-button" label={p.id ? "Save changes" : "Add to watchlist"} onPress={submit} loading={save.isPending} disabled={!valid} />
        </View>
      </KeyboardStickyView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.xl, paddingBottom: spacing.md },
  title: { fontSize: 24, letterSpacing: -0.4 },
  close: { width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  scan: { flexDirection: "row", alignItems: "center", gap: spacing.md, padding: spacing.lg, borderRadius: radius.lg, backgroundColor: c.brandTertiary },
  scanTitle: { fontSize: 16, color: c.onBrandTertiary },
  scanSub: { fontSize: 13, color: c.onBrandTertiary, opacity: 0.8 },
  note: { color: c.warning, fontSize: 14 },
  field: { gap: spacing.sm },
  row: { flexDirection: "row", gap: spacing.md },
  label: { fontSize: 14 },
  input: {
    height: 54, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border,
    paddingHorizontal: spacing.lg, fontSize: 16, fontFamily: fonts.regular, color: c.onSurface,
  },
  priceWrap: { flexDirection: "row", alignItems: "center", height: 64, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border, paddingHorizontal: spacing.lg },
  dollar: { fontSize: 26, color: c.muted, marginRight: spacing.xs },
  priceInput: { flex: 1, fontSize: 26, fontFamily: fonts.medium, color: c.onSurface, height: "100%", minWidth: 0, ...(Platform.OS === "web" ? ({ outlineStyle: "none" } as object) : {}) },
  hint: { fontSize: 12, color: c.muted, lineHeight: 17 },
  error: { color: c.error },
  sticky: { position: "absolute", left: 0, right: 0, bottom: 0 },
  bar: { paddingHorizontal: spacing.xl, paddingTop: spacing.lg, backgroundColor: c.surface, borderTopWidth: 1, borderTopColor: c.border },
}));
