import { useCallback, useEffect, useState } from "react";
import { listAuditEventsByEntity, type AuditEventRow } from "@/api";
import {
  formatAuditValue,
  formatLoadAuditActor,
  formatLoadStopsAuditSummary,
  groupLoadAuditRowsByDay,
  loadAuditActionLabel,
} from "@/loadWorkspace/loadAuditLabels";

type Props = {
  loadId: number | null;
  open: boolean;
  onClose: () => void;
};

export default function LoadHistoryPanel({ loadId, open, onClose }: Props) {
  const [rows, setRows] = useState<AuditEventRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    if (!loadId) return;
    try {
      setErr(null);
      const r = await listAuditEventsByEntity("load", String(loadId), { limit: 100 });
      setRows(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load history");
      setRows([]);
    }
  }, [loadId]);

  useEffect(() => {
    if (open && loadId) void fetchRows();
    if (!open) {
      setRows(null);
      setErr(null);
    }
  }, [open, loadId, fetchRows]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open || !loadId) return null;

  const groups = rows ? groupLoadAuditRowsByDay(rows) : null;

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-[55] bg-black/50"
        aria-label="Close load history"
        onClick={onClose}
      />
      <aside
        className="fixed right-0 top-0 z-[56] flex h-full w-full max-w-md flex-col border-l border-[var(--trk-border-strong)] bg-[var(--trk-bg)] shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="load-history-panel-title"
        data-testid="load-history-panel"
      >
        <header className="flex shrink-0 items-center justify-between gap-2 border-b border-[var(--trk-border)] px-4 py-3">
          <h2
            id="load-history-panel-title"
            className="text-sm font-bold uppercase tracking-[0.06em] text-[var(--trk-text)]"
          >
            History
          </h2>
          <button
            type="button"
            className="text-xs text-[var(--trk-text-muted)] hover:text-[var(--trk-text)]"
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-3">
          {err ? (
            <p className="text-center text-xs text-[var(--trk-danger)]">{err}</p>
          ) : rows === null ? (
            <p className="text-center text-xs text-[var(--trk-text-muted)]">Loading…</p>
          ) : rows.length === 0 ? (
            <p className="text-center text-xs text-[var(--trk-text-muted)]">No history yet.</p>
          ) : (
            <div className="space-y-5">
              {groups!.map((group) => (
                <section key={group.label}>
                  <h3 className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--trk-text-muted)]">
                    {group.label}
                  </h3>
                  <ul className="space-y-3">
                    {group.rows.map((r) => (
                      <li
                        key={r.id}
                        className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2.5"
                      >
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="text-xs font-semibold text-[var(--trk-text)]">
                            {loadAuditActionLabel(r.action)}
                          </span>
                          <time
                            className="shrink-0 text-[11px] tabular-nums text-[var(--trk-text-muted)]"
                            dateTime={r.event_at}
                          >
                            {new Date(r.event_at).toLocaleTimeString(undefined, {
                              hour: "numeric",
                              minute: "2-digit",
                            })}
                          </time>
                        </div>
                        <p className="mt-1 text-[11px] text-[var(--trk-text-muted)]">
                          {formatLoadAuditActor(r)}
                        </p>
                        {r.changed_fields && Object.keys(r.changed_fields).length > 0 ? (
                          r.action === "load_stops_changed" ? (
                            <p className="mt-2 text-[11px] text-[var(--trk-text-muted)]">
                              {formatLoadStopsAuditSummary(r.changed_fields)}
                            </p>
                          ) : (
                          <ul className="mt-2 space-y-1 text-[11px]">
                            {Object.entries(r.changed_fields).map(([k, v]) => (
                              <li key={k}>
                                <span className="text-[var(--trk-text-muted)]">{k}: </span>
                                {(v as { redacted?: boolean })?.redacted ? (
                                  <span className="text-[var(--trk-danger)]">redacted</span>
                                ) : (
                                  <span>
                                    <span className="text-red-400 line-through">
                                      {formatAuditValue((v as { before?: unknown })?.before)}
                                    </span>
                                    <span className="mx-1 text-[var(--trk-text-muted)]">→</span>
                                    <span className="font-medium text-emerald-400">
                                      {formatAuditValue((v as { after?: unknown })?.after)}
                                    </span>
                                  </span>
                                )}
                              </li>
                            ))}
                          </ul>
                          )
                        ) : null}
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
