import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

export type PushState = { status: "granted" | "denied" | "undetermined" | "unsupported"; canAskAgain: boolean };

export async function getPushState(): Promise<PushState> {
  if (Platform.OS === "web") return { status: "unsupported", canAskAgain: false };
  const p = await Notifications.getPermissionsAsync();
  return { status: p.status as PushState["status"], canAskAgain: p.canAskAgain };
}

type Api = <T>(path: string, init?: RequestInit) => Promise<T>;

// Registers the native device token with the backend. Safe to call on every app open.
export async function registerForPush(api: Api, ask: boolean): Promise<PushState> {
  let state = await getPushState();
  if (state.status === "unsupported") return state;
  if (state.status !== "granted" && ask && state.canAskAgain) {
    const r = await Notifications.requestPermissionsAsync();
    state = { status: r.status as PushState["status"], canAskAgain: r.canAskAgain };
  }
  if (state.status !== "granted") return state;
  try {
    const token = await Notifications.getDevicePushTokenAsync();
    await api("/register-push", {
      method: "POST",
      body: JSON.stringify({ platform: Platform.OS, device_token: String(token.data) }),
    });
  } catch {
    // Device tokens are unavailable in Expo Go; in-app banners still work.
  }
  return state;
}
