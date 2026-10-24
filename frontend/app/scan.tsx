import { BarcodeScanningResult, CameraView, useCameraPermissions } from "expo-camera";
import { useRouter } from "expo-router";
import { Barcode, X } from "phosphor-react-native";
import { useRef, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useApi } from "@/src/api";
import { Button, haptic, Txt } from "@/src/components/ui";
import { makeStyles, radius, spacing, useTheme } from "@/src/theme";

type Lookup = { found: boolean; barcode: string; name?: string; brand?: string; size?: string };

export default function Scan() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const api = useApi();
  const [permission, requestPermission] = useCameraPermissions();
  const [looking, setLooking] = useState(false);
  const handled = useRef(false);

  const typeInstead = () => router.replace("/add-item");

  const onScan = async (r: BarcodeScanningResult) => {
    if (handled.current) return;
    handled.current = true;
    haptic();
    setLooking(true);
    try {
      const res = await api<Lookup>(`/barcode/${encodeURIComponent(r.data)}`);
      router.replace({
        pathname: "/add-item",
        params: res.found
          ? { name: res.name, brand: res.brand, size: res.size, barcode: res.barcode }
          : { barcode: res.barcode, notFound: "1" },
      });
    } catch {
      router.replace({ pathname: "/add-item", params: { notFound: "1" } });
    }
  };

  const close = (
    <Pressable testID="scan-close-button" onPress={() => router.back()} hitSlop={12} style={[styles.close, { top: insets.top + spacing.md }]}>
      <X size={22} color={colors.onSurfaceInverse} />
    </Pressable>
  );

  if (!permission) {
    return <View style={styles.dark}><ActivityIndicator color={colors.onSurfaceInverse} /></View>;
  }

  if (!permission.granted) {
    const blocked = !permission.canAskAgain;
    return (
      <View style={[styles.light, { paddingTop: insets.top + spacing["3xl"], paddingBottom: insets.bottom + spacing.xl }]} testID="scan-permission-screen">
        <Pressable testID="scan-close-button" onPress={() => router.back()} hitSlop={12} style={[styles.closeLight, { top: insets.top + spacing.md }]}>
          <X size={22} color={colors.onSurface} />
        </Pressable>
        <View style={styles.permIcon}><Barcode size={48} color={colors.brandPrimary} /></View>
        <Txt style={styles.permTitle}>Scan groceries in a second</Txt>
        <Txt style={styles.permText}>
          {blocked
            ? "Camera access is turned off for Promobeaux. Turn it on in Settings to scan barcodes, or type the item instead."
            : "Point your camera at a barcode and we'll fill in the product for you. We only use the camera while you scan."}
        </Txt>
        <View style={{ flex: 1 }} />
        {blocked ? (
          <Button testID="scan-open-settings-button" label="Open Settings" onPress={() => Linking.openSettings()} />
        ) : (
          <Button testID="scan-allow-camera-button" label="Allow camera" onPress={requestPermission} />
        )}
        <Button testID="scan-type-instead-button" label="Type it instead" variant="ghost" onPress={typeInstead} style={{ marginTop: spacing.md }} />
      </View>
    );
  }

  return (
    <View style={styles.dark} testID="scan-camera-screen">
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        barcodeScannerSettings={{ barcodeTypes: ["ean13", "ean8", "upc_a", "upc_e"] }}
        onBarcodeScanned={looking ? undefined : onScan}
      />
      {close}
      <View style={styles.frame} pointerEvents="none" />
      <View style={[styles.bottom, { paddingBottom: insets.bottom + spacing.xl }]}>
        {looking ? (
          <View style={styles.lookRow}>
            <ActivityIndicator color={colors.onSurfaceInverse} />
            <Txt style={styles.bottomText}>Looking up product…</Txt>
          </View>
        ) : (
          <Txt style={styles.bottomText}>Line up the barcode inside the box</Txt>
        )}
        <Button testID="scan-type-instead-button" label="Type it instead" variant="secondary" onPress={typeInstead} />
      </View>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  dark: { flex: 1, backgroundColor: c.surfaceInverse, alignItems: "center", justifyContent: "center" },
  light: { flex: 1, backgroundColor: c.surface, paddingHorizontal: spacing.xl, gap: spacing.md },
  close: { position: "absolute", left: spacing.lg, width: 44, height: 44, borderRadius: 22, backgroundColor: c.scrim, alignItems: "center", justifyContent: "center" },
  closeLight: { position: "absolute", right: spacing.lg, width: 44, height: 44, borderRadius: 22, backgroundColor: c.surfaceTertiary, alignItems: "center", justifyContent: "center" },
  permIcon: { width: 96, height: 96, borderRadius: 48, backgroundColor: c.brandTertiary, alignItems: "center", justifyContent: "center", marginTop: spacing.xl },
  permTitle: { fontSize: 28, lineHeight: 36, letterSpacing: -0.5 },
  permText: { fontSize: 16, lineHeight: 24, color: c.muted },
  frame: { width: 280, height: 170, borderRadius: radius.lg, borderWidth: 3, borderColor: c.brandTertiary },
  bottom: { position: "absolute", left: 0, right: 0, bottom: 0, paddingHorizontal: spacing.xl, gap: spacing.md, paddingTop: spacing.lg, backgroundColor: c.scrim },
  bottomText: { color: c.onSurfaceInverse, textAlign: "center", fontSize: 15 },
  lookRow: { flexDirection: "row", gap: spacing.sm, justifyContent: "center", alignItems: "center" },
}));
