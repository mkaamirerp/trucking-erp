import { useEffect, useState } from "react";
import { fetchWithTenant, refreshSession } from "../api";
import { authErrorToMessage } from "../utils/authErrorToMessage";

export type FetchState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

export function useFetch<T>(url: string, deps: unknown[] = [], enabled: boolean = true) {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    loading: enabled,
    error: null,
  });

  useEffect(() => {
    if (!enabled) {
      setState({ data: null, loading: false, error: null });
      return;
    }
    let cancelled = false;
    setState((s) => ({ ...s, loading: true, error: null }));
    const run = async () => {
      try {
        let res = await fetchWithTenant(url);
        if (res.status === 401) {
          const refreshed = await refreshSession();
          if (refreshed) {
            res = await fetchWithTenant(url);
          }
        }
        if (!res.ok) {
          const text = await res.text();
          const message =
            res.status === 401 || res.status === 403
              ? authErrorToMessage(res.status, text || res.statusText)
              : text || res.statusText;
          throw new Error(message);
        }
        const data = await res.json();
        if (!cancelled) setState({ data, loading: false, error: null });
      } catch (err: any) {
        if (!cancelled) setState({ data: null, loading: false, error: err?.message || "Request failed" });
      }
    };
    run();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, ...deps]);

  return state;
}
