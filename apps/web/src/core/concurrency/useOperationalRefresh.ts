import { useCallback, useEffect, useRef } from "react";

export type UseOperationalRefreshOptions = {
  /**
   * Polling interval in ms. Pass `null` to disable interval polling (e.g. editable screens that only want focus refresh).
   */
  intervalMs: number | null;
  enabled?: boolean;
  /**
   * When true, skip automatic refresh entirely — never overwrite a dirty form from background refresh.
   * The hook continues tracking visibility and focus so a refresh fires immediately once isDirty becomes false.
   */
  isDirty?: boolean;
  onRefresh: () => void | Promise<void>;
};

/**
 * Operational refresh: visibility/focus regain + optional interval polling while the document is visible.
 * Concurrent triggers are deduped — if a refresh is already in flight, additional calls are no-ops until it finishes.
 */
export function useOperationalRefresh({
  intervalMs,
  enabled = true,
  isDirty = false,
  onRefresh,
}: UseOperationalRefreshOptions): { refetchNow: () => void } {
  const inFlightRef = useRef(false);
  const onRefreshRef = useRef(onRefresh);
  onRefreshRef.current = onRefresh;

  const refetchNow = useCallback(() => {
    if (!enabled) return;
    // never overwrite a dirty form from background refresh.
    if (isDirty) return;
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    void Promise.resolve(onRefreshRef.current()).finally(() => {
      inFlightRef.current = false;
    });
  }, [enabled, isDirty]);

  useEffect(() => {
    if (!enabled) return;

    const runIfVisible = () => {
      if (document.visibilityState !== "visible") return;
      refetchNow();
    };

    const onVisible = () => runIfVisible();

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);

    let intervalId: ReturnType<typeof setInterval> | undefined;
    if (intervalMs != null && intervalMs > 0) {
      intervalId = setInterval(runIfVisible, intervalMs);
    }

    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      if (intervalId !== undefined) clearInterval(intervalId);
    };
  }, [enabled, intervalMs, refetchNow]);

  return { refetchNow };
}
