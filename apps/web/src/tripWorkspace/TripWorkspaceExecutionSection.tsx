import { useCallback, useEffect, useMemo, useState } from "react";
import {
  acceptTripLoadCustody,
  completeTripContainer,
  getLoadCustodySnapshot,
  getTrip,
  isOpenTripMembership,
  listTerminals,
  takeTripLoadCustody,
  type LoadCustodySnapshot,
  type TerminalRow,
  type TripDetail,
  type TripMemberLoad,
  yardHandoffTripLoadCustody,
} from "@/api";
import {
  canOfferTerminalYardHandoff,
  countOpenMemberships,
  FINAL_DELIVERY_API_UNAVAILABLE,
  formatCustodySnapshotLine,
  formatCustodyTransitionError,
  formatTripCompleteError,
  showFinalDeliveryUnavailableNotice,
  suggestedCustodyStep,
  tripCompleteEligibility,
} from "./tripWorkspaceExecution";

type Props = {
  trip: TripDetail;
  tripId: number;
  onTripUpdated: (trip: TripDetail) => void;
};

export function TripWorkspaceExecutionSection({ trip, tripId, onTripUpdated }: Props) {
  const [custodyByLoadId, setCustodyByLoadId] = useState<Record<number, LoadCustodySnapshot>>({});
  const [custodyLoadError, setCustodyLoadError] = useState<string | null>(null);
  const [terminals, setTerminals] = useState<TerminalRow[]>([]);
  const [terminalsError, setTerminalsError] = useState<string | null>(null);
  const [yardTerminalByLoad, setYardTerminalByLoad] = useState<Record<number, string>>({});
  const [custodyBusyLoadId, setCustodyBusyLoadId] = useState<number | null>(null);
  const [custodyActionError, setCustodyActionError] = useState<string | null>(null);
  const [completeBusy, setCompleteBusy] = useState(false);
  const [completeError, setCompleteError] = useState<string | null>(null);

  const openMembers = useMemo(
    () => (trip.member_loads ?? []).filter((m: TripMemberLoad) => isOpenTripMembership(m)),
    [trip.member_loads],
  );

  const executionPhase = useMemo(() => {
    const st = (trip.status || "").toLowerCase();
    return st === "in_progress" || st === "completed";
  }, [trip.status]);

  const refreshCustodySnapshots = useCallback(async (loadIds: number[]) => {
    if (loadIds.length === 0) return;
    setCustodyLoadError(null);
    try {
      const snaps = await Promise.all(loadIds.map((id) => getLoadCustodySnapshot(id)));
      setCustodyByLoadId((prev) => {
        const next = { ...prev };
        for (const s of snaps) next[s.load_id] = s;
        return next;
      });
    } catch (e: unknown) {
      setCustodyLoadError(e instanceof Error ? e.message : "Could not load custody snapshots.");
    }
  }, []);

  useEffect(() => {
    if (!executionPhase || openMembers.length === 0) return;
    void refreshCustodySnapshots(openMembers.map((m) => m.load_id));
  }, [executionPhase, openMembers, refreshCustodySnapshots]);

  useEffect(() => {
    if (!executionPhase) return;
    let cancelled = false;
    void (async () => {
      setTerminalsError(null);
      try {
        const items = await listTerminals(true);
        if (!cancelled) setTerminals(items);
      } catch (e: unknown) {
        if (!cancelled) setTerminalsError(e instanceof Error ? e.message : "Could not load terminals.");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [executionPhase, tripId]);

  const completeEligibility = useMemo(() => tripCompleteEligibility(trip), [trip]);

  const onCompleteTrip = useCallback(async () => {
    if (!completeEligibility.canComplete || completeBusy) return;
    const ok = window.confirm(
      "Complete this trip?\n\nThis closes the operational trip container. It does not mark commercial loads delivered, change Load.status, or post payroll.\n\nContinue?",
    );
    if (!ok) return;
    setCompleteBusy(true);
    setCompleteError(null);
    try {
      const updated = await completeTripContainer(tripId);
      onTripUpdated(updated);
    } catch (e: unknown) {
      setCompleteError(formatTripCompleteError(e));
    } finally {
      setCompleteBusy(false);
    }
  }, [completeEligibility.canComplete, completeBusy, tripId, onTripUpdated]);

  const refreshTripAndCustody = useCallback(
    async (loadId: number) => {
      const updated = await getTrip(tripId);
      onTripUpdated(updated);
      await refreshCustodySnapshots([loadId]);
    },
    [tripId, onTripUpdated, refreshCustodySnapshots],
  );

  const onCustodyAction = useCallback(
    async (m: TripMemberLoad, step: "accept" | "take" | "yard_handoff") => {
      if (custodyBusyLoadId != null) return;
      setCustodyBusyLoadId(m.load_id);
      setCustodyActionError(null);
      try {
        if (step === "accept") {
          await acceptTripLoadCustody(tripId, m.load_id, {});
        } else if (step === "take") {
          await takeTripLoadCustody(tripId, m.load_id, {});
        } else {
          const tid = Number(yardTerminalByLoad[m.load_id] || "");
          if (!Number.isFinite(tid) || tid < 1) {
            setCustodyActionError("Select a terminal for yard handoff.");
            return;
          }
          await yardHandoffTripLoadCustody(tripId, m.load_id, {
            terminal_id: tid,
            placement: "staged",
          });
        }
        await refreshTripAndCustody(m.load_id);
      } catch (e: unknown) {
        setCustodyActionError(formatCustodyTransitionError(e));
      } finally {
        setCustodyBusyLoadId(null);
      }
    },
    [custodyBusyLoadId, tripId, yardTerminalByLoad, refreshTripAndCustody],
  );

  const statusLabel = (trip.status || "").toLowerCase();
  const openCount = countOpenMemberships(trip);

  return (
    <section
      className="rounded-xl border border-[var(--trk-border)] bg-[var(--trk-surface)] p-5"
      data-testid="trip-workspace-execution-section"
    >
      <h2 className="text-sm font-semibold text-[var(--trk-text)]">Execution &amp; closeout</h2>
      <p className="mt-2 text-[11px] text-[var(--trk-text-muted)]">
        Trip status: <span className="font-medium text-[var(--trk-text)]">{trip.status}</span>
        {trip.completed_at ? (
          <>
            {" "}
            · completed {new Date(trip.completed_at).toLocaleString()}
          </>
        ) : null}
        {executionPhase ? (
          <>
            {" "}
            · open memberships: <span className="font-medium text-[var(--trk-text)]">{openCount}</span>
          </>
        ) : null}
      </p>
      <p className="mt-2 text-sm text-[var(--trk-text-muted)]">
        Finish load custody on this trip, then complete the trip when no open memberships remain. Commercial load
        status is unchanged by these actions.
      </p>

      {executionPhase && openMembers.length > 0 ? (
        <ul className="mt-4 divide-y divide-[var(--trk-border)] rounded-lg border border-[var(--trk-border)]">
          {openMembers.map((m) => {
            const snap = custodyByLoadId[m.load_id];
            const step = suggestedCustodyStep(m, snap, tripId);
            const terminalHandoff = canOfferTerminalYardHandoff(m, snap, tripId);
            const finalDeliveryNotice = showFinalDeliveryUnavailableNotice(m, snap, tripId);
            return (
              <li key={m.trip_load_id} className="flex flex-col gap-2 px-4 py-3 text-sm">
                <div className="font-medium text-[var(--trk-text)]">
                  {m.load_number} · membership {m.status_within_trip}
                </div>
                <div className="text-xs text-[var(--trk-text-muted)]">{formatCustodySnapshotLine(snap)}</div>
                {step ? (
                  <button
                    type="button"
                    disabled={custodyBusyLoadId != null}
                    onClick={() => void onCustodyAction(m, step)}
                    className="w-fit rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-heading)] hover:border-[var(--trk-border-strong)] disabled:opacity-50"
                  >
                    {custodyBusyLoadId === m.load_id
                      ? "Working…"
                      : step === "accept"
                        ? "Accept custody (pickup)"
                        : "Take custody from terminal"}
                  </button>
                ) : null}
                {terminalHandoff ? (
                  <div className="mt-1 flex flex-col gap-2 border-l-2 border-[var(--trk-border)] pl-3">
                    <p className="text-[11px] text-[var(--trk-text-muted)]">
                      Terminal / yard handoff — use only when freight is handed to a tenant terminal (not consignee
                      delivery).
                    </p>
                    <label className="flex max-w-md flex-col gap-1 text-[11px] text-[var(--trk-text-muted)]">
                      Terminal
                      <select
                        value={yardTerminalByLoad[m.load_id] ?? ""}
                        onChange={(e) =>
                          setYardTerminalByLoad((prev) => ({ ...prev, [m.load_id]: e.target.value }))
                        }
                        disabled={custodyBusyLoadId === m.load_id}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-1.5 text-sm text-[var(--trk-text)]"
                      >
                        <option value="">— Select terminal —</option>
                        {terminals.map((t) => (
                          <option key={t.id} value={String(t.id)}>
                            #{t.id} {t.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      data-testid={`trip-yard-handoff-${m.load_id}`}
                      disabled={custodyBusyLoadId != null}
                      onClick={() => void onCustodyAction(m, "yard_handoff")}
                      className="w-fit rounded-md border border-amber-300/80 bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-amber-900 hover:bg-amber-50 disabled:opacity-50"
                    >
                      {custodyBusyLoadId === m.load_id ? "Working…" : "Record terminal / yard handoff"}
                    </button>
                  </div>
                ) : null}
                {finalDeliveryNotice ? (
                  <p className="text-[11px] text-[var(--trk-text-muted)]" data-testid="final-delivery-unavailable">
                    {FINAL_DELIVERY_API_UNAVAILABLE}
                  </p>
                ) : null}
                {!step && !terminalHandoff ? (
                  <p className="text-[11px] text-amber-800/90">
                    No custody action available for this membership state. Resolve custody elsewhere or contact support.
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}

      {custodyLoadError ? <p className="mt-3 text-[11px] text-red-700">{custodyLoadError}</p> : null}
      {terminalsError ? <p className="mt-3 text-[11px] text-red-700">{terminalsError}</p> : null}
      {custodyActionError ? <p className="mt-3 text-[11px] text-red-700">{custodyActionError}</p> : null}

      <div className="mt-5 border-t border-[var(--trk-border)] pt-4">
        {statusLabel === "completed" ? (
          <p className="text-sm font-medium text-[var(--trk-text-muted)]">This trip is completed.</p>
        ) : (
          <>
            <button
              type="button"
              data-testid="trip-workspace-complete-trip"
              disabled={!completeEligibility.canComplete || completeBusy}
              onClick={() => void onCompleteTrip()}
              className="rounded-md border border-emerald-300/80 bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-emerald-800 hover:bg-emerald-50 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {completeBusy ? "Completing…" : "Complete trip"}
            </button>
            {!completeEligibility.canComplete && completeEligibility.reason ? (
              <p className="mt-2 text-[11px] text-[var(--trk-text-muted)]">{completeEligibility.reason}</p>
            ) : null}
            {completeError ? <p className="mt-2 text-[11px] text-red-700">{completeError}</p> : null}
          </>
        )}
      </div>
    </section>
  );
}
