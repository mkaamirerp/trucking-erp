import { useEffect, useState } from "react";
import {
  acceptLoadCustody,
  completeTrip,
  finalDeliveryLoad,
  getLoadCustody,
  listTerminals,
  takeLoadCustody,
  yardHandoffLoad,
  type LoadCustodySnapshot,
  type TerminalOption,
  type TripDetail,
  type YardHandoffPayload,
} from "@/api";
import {
  canCompleteTrip,
  custodyStatusLabel,
  formatCustodyApiError,
  showAcceptCustody,
  showFinalDelivery,
  showHandoff,
  showTakeCustody,
  type CustodyPlacement,
} from "./custodyOperator";

export type CustodyPanelApi = {
  getLoadCustody: typeof getLoadCustody;
  listTerminals: typeof listTerminals;
  acceptLoadCustody: typeof acceptLoadCustody;
  takeLoadCustody: typeof takeLoadCustody;
  yardHandoffLoad: typeof yardHandoffLoad;
  finalDeliveryLoad: typeof finalDeliveryLoad;
  completeTrip: typeof completeTrip;
};

const defaultApi: CustodyPanelApi = {
  getLoadCustody,
  listTerminals,
  acceptLoadCustody,
  takeLoadCustody,
  yardHandoffLoad,
  finalDeliveryLoad,
  completeTrip,
};

const btn =
  "rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)] disabled:opacity-45";
const btnPrimary =
  "rounded border border-[var(--trk-heading)]/50 bg-[var(--trk-heading)]/15 px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-heading)] hover:bg-[var(--trk-heading)]/25 disabled:opacity-45";

type HandoffDraft = { terminalId: string; placement: "" | CustodyPlacement };

export default function TripCustodyPanel({
  trip,
  onRefresh,
  api = defaultApi,
}: {
  trip: TripDetail;
  onRefresh: () => Promise<void>;
  api?: CustodyPanelApi;
}) {
  const [snapshots, setSnapshots] = useState<Record<number, LoadCustodySnapshot | null>>({});
  const [rowErrors, setRowErrors] = useState<Record<number, string>>({});
  const [terminals, setTerminals] = useState<TerminalOption[]>([]);
  const [terminalError, setTerminalError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<number, HandoffDraft>>({});
  const [pendingKey, setPendingKey] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [confirmDeliveryId, setConfirmDeliveryId] = useState<number | null>(null);

  const membershipKey = trip.member_loads
    .map((member) => `${member.load_id}:${member.status_within_trip}:${member.completed_at ?? ""}:${member.removed_at ?? ""}`)
    .join("|");

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const listed = await api.listTerminals();
        if (!cancelled) {
          setTerminals(listed.items ?? []);
          setTerminalError(null);
        }
      } catch (err: unknown) {
        if (!cancelled) setTerminalError(formatCustodyApiError(err));
      }
      const next: Record<number, LoadCustodySnapshot | null> = {};
      const errors: Record<number, string> = {};
      await Promise.all(
        trip.member_loads.map(async (member) => {
          try {
            next[member.load_id] = await api.getLoadCustody(member.load_id);
          } catch (err: unknown) {
            next[member.load_id] = null;
            errors[member.load_id] = formatCustodyApiError(err);
          }
        }),
      );
      if (!cancelled) {
        setSnapshots(next);
        setRowErrors(errors);
      }
    })();
    return () => {
      cancelled = true;
    };
    // membershipKey already captures the member rows for this render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, trip.id, membershipKey]);

  async function runAction(key: string, action: () => Promise<unknown>) {
    if (pendingKey) return;
    setPendingKey(key);
    setActionError(null);
    try {
      await action();
      await onRefresh();
    } catch (err: unknown) {
      setActionError(formatCustodyApiError(err));
    } finally {
      setPendingKey(null);
    }
  }

  const completeEnabled = canCompleteTrip(trip) && pendingKey == null;

  return (
    <div className="mt-2 space-y-2" data-testid="trip-custody-panel">
      <div className="flex flex-wrap items-center gap-1">
        <button
          type="button"
          className={btnPrimary}
          data-testid="complete-trip"
          disabled={!completeEnabled}
          onClick={() => {
            if (!canCompleteTrip(trip)) return;
            void runAction("complete", () => api.completeTrip(trip.id));
          }}
        >
          {pendingKey === "complete" ? "Completing…" : "Complete Trip"}
        </button>
        <span className="text-[9px] text-[var(--trk-text-muted)]">Handoff and final delivery do not complete the Trip.</span>
      </div>
      {actionError ? (
        <p className="text-[10px] text-[var(--trk-danger)]" role="alert" data-testid="custody-action-error">
          {actionError}
        </p>
      ) : null}
      {terminalError ? <p className="text-[10px] text-[var(--trk-danger)]">{terminalError}</p> : null}
      <ul className="space-y-1">
        {trip.member_loads.map((member) => {
          const snapshot = snapshots[member.load_id];
          const draft = drafts[member.load_id] ?? { terminalId: "", placement: "" };
          const accept = showAcceptCustody(trip, member, snapshot);
          const take = showTakeCustody(trip, member, snapshot);
          const handoff = showHandoff(trip, member, snapshot);
          const finalDelivery = showFinalDelivery(trip, member, snapshot);
          const handoffReady = draft.terminalId !== "" && (draft.placement === "on_trailer" || draft.placement === "staged");
          return (
            <li
              key={member.trip_load_id}
              className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)]/40 px-2 py-1.5"
              data-testid={`custody-row-${member.load_id}`}
            >
              <div className="text-[10px] text-[var(--trk-text)]">
                <span className="font-semibold">{member.load_number || `Load #${member.load_id}`}</span>
                <span className="mx-1 text-[var(--trk-text-muted)]">·</span>
                <span data-testid={`membership-${member.load_id}`}>On trip: {member.status_within_trip}</span>
              </div>
              <div className="text-[10px] text-[var(--trk-text-muted)]" data-testid={`custody-label-${member.load_id}`}>
                {snapshot === undefined ? "Loading custody…" : custodyStatusLabel(snapshot)}
              </div>
              {rowErrors[member.load_id] ? (
                <p className="text-[10px] text-[var(--trk-danger)]">{rowErrors[member.load_id]}</p>
              ) : null}
              <div className="mt-1 flex flex-wrap items-center gap-1">
                {accept ? (
                  <button
                    type="button"
                    className={btn}
                    data-testid={`accept-custody-${member.load_id}`}
                    disabled={pendingKey != null}
                    onClick={() => void runAction(`accept-${member.load_id}`, () => api.acceptLoadCustody(trip.id, member.load_id))}
                  >
                    Accept Custody
                  </button>
                ) : null}
                {take ? (
                  <button
                    type="button"
                    className={btn}
                    data-testid={`take-custody-${member.load_id}`}
                    disabled={pendingKey != null}
                    onClick={() => void runAction(`take-${member.load_id}`, () => api.takeLoadCustody(trip.id, member.load_id))}
                  >
                    Take Custody
                  </button>
                ) : null}
                {handoff ? (
                  <>
                    <label className="text-[9px] text-[var(--trk-text-muted)]">
                      Terminal
                      <select
                        className="ml-1 rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1 py-0.5 text-[10px]"
                        data-testid={`handoff-terminal-${member.load_id}`}
                        value={draft.terminalId}
                        disabled={pendingKey != null}
                        onChange={(event) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [member.load_id]: { ...draft, terminalId: event.target.value },
                          }))
                        }
                      >
                        <option value="">Select</option>
                        {terminals.map((terminal) => (
                          <option key={terminal.id} value={String(terminal.id)}>
                            {terminal.name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="text-[9px] text-[var(--trk-text-muted)]">
                      Disposition
                      <select
                        className="ml-1 rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1 py-0.5 text-[10px]"
                        data-testid={`handoff-placement-${member.load_id}`}
                        value={draft.placement}
                        disabled={pendingKey != null}
                        onChange={(event) =>
                          setDrafts((prev) => ({
                            ...prev,
                            [member.load_id]: {
                              ...draft,
                              placement: event.target.value as HandoffDraft["placement"],
                            },
                          }))
                        }
                      >
                        <option value="">Select</option>
                        <option value="on_trailer">on_trailer</option>
                        <option value="staged">staged</option>
                      </select>
                    </label>
                    <button
                      type="button"
                      className={btn}
                      data-testid={`handoff-${member.load_id}`}
                      disabled={pendingKey != null || !handoffReady}
                      onClick={() => {
                        if (!handoffReady) return;
                        const body: YardHandoffPayload = {
                          terminal_id: Number(draft.terminalId),
                          placement: draft.placement as CustodyPlacement,
                        };
                        void runAction(`handoff-${member.load_id}`, () => api.yardHandoffLoad(trip.id, member.load_id, body));
                      }}
                    >
                      Handoff
                    </button>
                  </>
                ) : null}
                {finalDelivery && confirmDeliveryId !== member.load_id ? (
                  <button
                    type="button"
                    className={btn}
                    data-testid={`final-delivery-${member.load_id}`}
                    disabled={pendingKey != null}
                    onClick={() => setConfirmDeliveryId(member.load_id)}
                  >
                    Final Delivery
                  </button>
                ) : null}
                {finalDelivery && confirmDeliveryId === member.load_id ? (
                  <div className="flex flex-wrap items-center gap-1" data-testid={`final-delivery-confirm-${member.load_id}`}>
                    <span className="text-[9px] text-[var(--trk-text)]">
                      Record final delivery for this Load? This does not complete the Trip.
                    </span>
                    <button
                      type="button"
                      className={btn}
                      disabled={pendingKey != null}
                      onClick={() => setConfirmDeliveryId(null)}
                    >
                      Go back
                    </button>
                    <button
                      type="button"
                      className={btnPrimary}
                      data-testid={`final-delivery-submit-${member.load_id}`}
                      disabled={pendingKey != null}
                      onClick={() =>
                        void runAction(`deliver-${member.load_id}`, () =>
                          api.finalDeliveryLoad(trip.id, member.load_id, {}),
                        )
                      }
                    >
                      Confirm final delivery
                    </button>
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
