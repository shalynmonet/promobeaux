import { useSSO } from "@clerk/expo";
import { useSignIn, useSignUp } from "@clerk/expo/legacy";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { Redirect, useRouter } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { GoogleLogo, Sparkle } from "phosphor-react-native";
import { useState } from "react";
import { Platform, Pressable, TextInput, View } from "react-native";
import { KeyboardAwareScrollView } from "react-native-keyboard-controller";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useSession } from "@/src/auth";
import { Button, Txt } from "@/src/components/ui";
import { fonts, makeStyles, radius, spacing, useTheme } from "@/src/theme";

WebBrowser.maybeCompleteAuthSession();

const HERO = "https://images.unsplash.com/photo-1628102491629-778571d893a3?crop=entropy&cs=srgb&fm=jpg&q=85&w=1200";

function errMessage(e: any) {
  return e?.errors?.[0]?.longMessage || e?.errors?.[0]?.message || e?.message || "Something went wrong";
}

export default function SignIn() {
  const styles = useStyles();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { signedIn, enterDemo } = useSession();
  const { isLoaded: inLoaded, signIn, setActive } = useSignIn();
  const { isLoaded: upLoaded, signUp, setActive: setActiveUp } = useSignUp();
  const { startSSOFlow } = useSSO();

  const [mode, setMode] = useState<"in" | "up">("in");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [verifying, setVerifying] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");

  if (signedIn) return <Redirect href="/" />;

  const run = async (key: string, fn: () => Promise<void>) => {
    setError("");
    setBusy(key);
    try {
      await fn();
    } catch (e) {
      setError(errMessage(e));
    } finally {
      setBusy(null);
    }
  };

  const submit = () =>
    run("email", async () => {
      if (mode === "in") {
        if (!inLoaded) return;
        const res = await signIn.create({ identifier: email.trim(), password });
        if (res.status === "complete") {
          await setActive({ session: res.createdSessionId });
          router.replace("/");
        } else setError("Additional verification is required for this account.");
      } else {
        if (!upLoaded) return;
        await signUp.create({ emailAddress: email.trim(), password });
        await signUp.prepareEmailAddressVerification({ strategy: "email_code" });
        setVerifying(true);
      }
    });

  const verify = () =>
    run("verify", async () => {
      if (!upLoaded) return;
      const res = await signUp.attemptEmailAddressVerification({ code: code.trim() });
      if (res.status === "complete") {
        await setActiveUp({ session: res.createdSessionId });
        router.replace("/");
      } else setError("That code didn't work. Check your email and try again.");
    });

  const google = () =>
    run("google", async () => {
      const { createdSessionId, setActive: activate } = await startSSOFlow({ strategy: "oauth_google" });
      if (createdSessionId && activate) {
        await activate({ session: createdSessionId });
        router.replace("/");
      }
    });

  const demo = () =>
    run("demo", async () => {
      await enterDemo();
      router.replace("/");
    });

  return (
    <View style={styles.root}>
      <KeyboardAwareScrollView bottomOffset={24} contentContainerStyle={{ paddingBottom: insets.bottom + spacing.xl }} keyboardShouldPersistTaps="handled">
        <View style={styles.hero}>
          <Image source={{ uri: HERO }} style={styles.heroImg} contentFit="cover" transition={300} />
          <LinearGradient colors={["transparent", colors.surface]} style={styles.heroFade} />
        </View>
        <View style={styles.content}>
          <View style={styles.logoRow}>
            <View style={styles.logoDot}>
              <Sparkle size={18} color={colors.onBrandPrimary} weight="fill" />
            </View>
            <Txt medium style={styles.logo}>Promobeaux</Txt>
          </View>
          <Txt style={styles.headline}>Never pay full price for your regulars.</Txt>
          <Txt style={styles.sub}>We watch the weekly ads at your stores and tell you when your groceries go on sale.</Txt>

          {!verifying ? (
            <>
              <View style={styles.segment}>
                {(["in", "up"] as const).map((m) => (
                  <Pressable key={m} testID={`auth-mode-${m}`} onPress={() => { setMode(m); setError(""); }} style={[styles.segBtn, mode === m && styles.segActive]}>
                    <Txt medium style={[styles.segText, mode === m && styles.segTextActive]}>{m === "in" ? "Sign in" : "Create account"}</Txt>
                  </Pressable>
                ))}
              </View>
              <TextInput
                testID="auth-email-input" value={email} onChangeText={setEmail} placeholder="Email"
                placeholderTextColor={colors.muted} autoCapitalize="none" keyboardType="email-address"
                autoComplete="email" style={styles.input}
              />
              <TextInput
                testID="auth-password-input" value={password} onChangeText={setPassword} placeholder="Password"
                placeholderTextColor={colors.muted} secureTextEntry style={styles.input}
                onSubmitEditing={submit}
              />
              <Button testID="auth-submit-button" label={mode === "in" ? "Sign in" : "Create account"} onPress={submit}
                loading={busy === "email"} disabled={!email || password.length < 8 || !!busy} />
            </>
          ) : (
            <>
              <Txt style={styles.sub}>We sent a 6-digit code to {email}.</Txt>
              <TextInput
                testID="auth-code-input" value={code} onChangeText={setCode} placeholder="Verification code"
                placeholderTextColor={colors.muted} keyboardType="number-pad" style={styles.input} maxLength={6}
              />
              <Button testID="auth-verify-button" label="Verify email" onPress={verify} loading={busy === "verify"} disabled={code.length < 6} />
              <Pressable testID="auth-back-button" onPress={() => setVerifying(false)} style={styles.link}>
                <Txt style={styles.linkText}>Use a different email</Txt>
              </Pressable>
            </>
          )}

          {!!error && <Txt testID="auth-error" style={styles.error}>{error}</Txt>}

          {!verifying && (
            <>
              <View style={styles.dividerRow}>
                <View style={styles.line} />
                <Txt style={styles.or}>or</Txt>
                <View style={styles.line} />
              </View>
              {Platform.OS !== "web" && (
                <Button testID="auth-google-button" label="Continue with Google" variant="ghost" onPress={google}
                  loading={busy === "google"} icon={<GoogleLogo size={20} color={colors.onSurface} weight="bold" />} />
              )}
              <Button testID="auth-demo-button" label="Explore the demo" variant="secondary" onPress={demo} loading={busy === "demo"} style={{ marginTop: spacing.md }} />
              <Txt style={styles.fine}>Demo mode uses a sample shopper in Dallas, TX.</Txt>
            </>
          )}
        </View>
      </KeyboardAwareScrollView>
    </View>
  );
}

const useStyles = makeStyles((c) => ({
  root: { flex: 1, backgroundColor: c.surface },
  hero: { height: 260 },
  heroImg: { ...{ position: "absolute", top: 0, left: 0, right: 0, bottom: 0 } },
  heroFade: { position: "absolute", left: 0, right: 0, bottom: 0, height: 140 },
  content: { paddingHorizontal: spacing.xl, gap: spacing.md, marginTop: -spacing.xl },
  logoRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  logoDot: { width: 32, height: 32, borderRadius: 16, backgroundColor: c.brandPrimary, alignItems: "center", justifyContent: "center" },
  logo: { fontSize: 20, color: c.brandSecondary },
  headline: { fontSize: 30, lineHeight: 38, letterSpacing: -0.6 },
  sub: { fontSize: 15, lineHeight: 22, color: c.muted, marginBottom: spacing.sm },
  segment: { flexDirection: "row", backgroundColor: c.surfaceTertiary, borderRadius: radius.pill, padding: 4 },
  segBtn: { flex: 1, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  segActive: { backgroundColor: c.surfaceSecondary },
  segText: { color: c.muted },
  segTextActive: { color: c.onSurface },
  input: {
    height: 54, borderRadius: radius.md, backgroundColor: c.surfaceSecondary, borderWidth: 1, borderColor: c.border,
    paddingHorizontal: spacing.lg, fontSize: 16, fontFamily: fonts.regular, color: c.onSurface,
  },
  error: { color: c.error, fontSize: 14 },
  link: { alignSelf: "center", padding: spacing.sm },
  linkText: { color: c.brandSecondary },
  dividerRow: { flexDirection: "row", alignItems: "center", gap: spacing.md, marginVertical: spacing.sm },
  line: { flex: 1, height: 1, backgroundColor: c.divider },
  or: { color: c.muted },
  fine: { fontSize: 12, color: c.muted, textAlign: "center" },
}));
