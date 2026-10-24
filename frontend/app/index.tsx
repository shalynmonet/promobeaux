import { Redirect } from "expo-router";
import { ActivityIndicator, View } from "react-native";

import { useMe } from "@/src/api";
import { useSession } from "@/src/auth";
import { Button, Txt } from "@/src/components/ui";
import { spacing, useTheme } from "@/src/theme";

export default function Index() {
  const { ready, signedIn, signOut } = useSession();
  const me = useMe();
  const { colors } = useTheme();

  if (ready && !signedIn) return <Redirect href="/sign-in" />;
  if (me.data) return <Redirect href={me.data.onboarded ? "/(tabs)/deals" : "/onboarding"} />;

  return (
    <View testID="launch-screen" style={{ flex: 1, alignItems: "center", justifyContent: "center", gap: spacing.lg, padding: spacing.xl, backgroundColor: colors.surface }}>
      {me.error ? (
        <>
          <Txt testID="launch-error" style={{ fontSize: 16, textAlign: "center" }}>
            We couldn&apos;t load your account. {me.error.message}
          </Txt>
          <Button testID="launch-retry-button" label="Try again" onPress={() => me.refetch()} />
          <Button testID="launch-signout-button" label="Sign out" variant="ghost" onPress={signOut} />
        </>
      ) : (
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      )}
    </View>
  );
}
