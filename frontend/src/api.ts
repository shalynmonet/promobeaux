import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { BACKEND_URL, useSession } from "@/src/auth";

export type User = { user_id: string; is_demo: boolean; zip: string; stores: string[]; onboarded: boolean; last_checked_at?: string | null };
export type Item = { id: string; name: string; brand: string; size: string; usual_price: number; barcode: string };
export type Deal = {
  id: string; item_id: string; item_name: string; brand: string; size: string; store: string;
  usual_price: number; sale_price: number; savings: number; pct_off: number;
  promo_type: "sale" | "bogo" | "coupon" | "cashback"; promo_text: string; source_url: string; source_title: string;
  source_kind?: "search" | "weekly_ad";
  is_sample: boolean; found_at: string;
};
export type Savings = {
  total: number; deal_count: number; item_count: number;
  by_store: { store: string; savings: number; count: number }[]; top: Deal[]; last_checked_at?: string | null;
};
export type AlertItem = { id: string; title: string; message: string; read: boolean; created_at: string };
export type CheckResult = { checked: number; found: number; new_alerts: number };
export type ItemInput = Omit<Item, "id">;

export function useApi() {
  const { getToken } = useSession();
  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      const res = await fetch(`${BACKEND_URL}/api${path}`, {
        ...init,
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      });
      if (!res.ok) {
        let detail = `Request failed (${res.status})`;
        try {
          const body = await res.json();
          if (typeof body.detail === "string") detail = body.detail;
        } catch {}
        throw new Error(detail);
      }
      return res.json();
    },
    [getToken],
  );
}

function useAuthedQuery<T>(key: string, path: string, refetchInterval?: number) {
  const api = useApi();
  const { signedIn } = useSession();
  return useQuery({ queryKey: [key], queryFn: () => api<T>(path), enabled: signedIn, refetchInterval });
}

export const useMe = () => useAuthedQuery<User>("me", "/me");
export const useWatchlist = () => useAuthedQuery<Item[]>("watchlist", "/watchlist");
export const useDeals = () => useAuthedQuery<Deal[]>("deals", "/deals");
export const useSavings = () => useAuthedQuery<Savings>("savings", "/savings");
export const useAlerts = () => useAuthedQuery<AlertItem[]>("alerts", "/alerts", 60000);

export function useCheckDeals() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api<CheckResult>("/deals/check", { method: "POST" }),
    onSuccess: () => {
      ["deals", "savings", "alerts", "me", "trip"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });
}

export function useSaveItem() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: ItemInput & { id?: string }) =>
      api<Item>(id ? `/watchlist/${id}` : "/watchlist", { method: id ? "PUT" : "POST", body: JSON.stringify(body) }),
    onSuccess: () => {
      ["watchlist", "savings", "trip"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    },
  });
}

export function useDeleteItem() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api(`/watchlist/${id}`, { method: "DELETE" }),
    onSuccess: () => ["watchlist", "deals", "savings", "trip"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
}

export const money = (n: number) => `$${n.toFixed(2)}`;

export type TripRow = {
  item_id: string; name: string; brand: string; size: string; usual_price: number; price: number;
  savings: number; promo_type: Deal["promo_type"] | null; on_deal: boolean;
};
export type Trip = { store: string | null; savings: number; estimated_total: number; items: TripRow[]; alternatives: { store: string; savings: number }[] };
export type AdLine = { text: string; price: number | null; promo_type: "bogo" | "coupon" | null; source_url: string };
export type AdPage = { store: string; zip: string; retrieved_at: string; lines: AdLine[]; sources: { title: string; url: string }[] };

export const useTrip = () => useAuthedQuery<Trip>("trip", "/trip");

export function useAds(store: string | undefined) {
  const api = useApi();
  const { signedIn } = useSession();
  return useQuery({
    queryKey: ["ads", store],
    queryFn: () => api<AdPage>(`/ads/${encodeURIComponent(store!)}`),
    enabled: signedIn && !!store,
    staleTime: 10 * 60 * 1000,
  });
}

export function useRefreshAds() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (store: string) => api<AdPage>(`/ads/${encodeURIComponent(store)}?refresh=true`),
    onSuccess: (page) => qc.setQueryData(["ads", page.store], page),
  });
}

export function useRestoreItem() {
  const api = useApi();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<Item>(`/watchlist/${id}/restore`, { method: "POST" }),
    onSuccess: () => ["watchlist", "deals", "savings", "trip"].forEach((k) => qc.invalidateQueries({ queryKey: [k] })),
  });
}
