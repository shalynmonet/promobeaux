import { useAuth } from "@clerk/expo";
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { queryClient } from "@/src/query-client";
import { storage } from "@/src/utils/storage";

const DEMO_KEY = "demo_token";
export const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL;

type AuthValue = {
  ready: boolean;
  signedIn: boolean;
  isDemo: boolean;
  getToken: () => Promise<string | null>;
  enterDemo: () => Promise<void>;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const clerk = useAuth();
  const [demoToken, setDemoToken] = useState<string | null>(null);
  const [demoLoaded, setDemoLoaded] = useState(false);

  useEffect(() => {
    storage.secureGet(DEMO_KEY, null).then((t) => {
      setDemoToken(typeof t === "string" ? t : null);
      setDemoLoaded(true);
    });
  }, []);

  const enterDemo = useCallback(async () => {
    const res = await fetch(`${BACKEND_URL}/api/auth/demo`, { method: "POST" });
    if (!res.ok) throw new Error("Could not start demo");
    const { token } = await res.json();
    await storage.secureSet(DEMO_KEY, token);
    queryClient.clear();
    setDemoToken(token);
  }, []);

  const signOut = useCallback(async () => {
    queryClient.clear();
    if (demoToken) {
      await storage.secureRemove(DEMO_KEY);
      setDemoToken(null);
    }
    if (clerk.isSignedIn) await clerk.signOut();
  }, [demoToken, clerk]);

  const { getToken: clerkGetToken, isSignedIn, isLoaded } = clerk;
  const getToken = useCallback(async () => demoToken ?? (await clerkGetToken()), [demoToken, clerkGetToken]);

  const value = useMemo<AuthValue>(
    () => ({
      ready: demoLoaded && isLoaded,
      signedIn: !!demoToken || !!isSignedIn,
      isDemo: !!demoToken,
      getToken,
      enterDemo,
      signOut,
    }),
    [demoLoaded, isLoaded, demoToken, isSignedIn, getToken, enterDemo, signOut],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useSession() {
  const v = useContext(AuthCtx);
  if (!v) throw new Error("useSession must be used inside AuthProvider");
  return v;
}
