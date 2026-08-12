/**
 * Future-scope reference for Trip Container — non-functional, collapsed by default.
 */
export function FuturePlaceholderPanels() {
  const panelClass =
    "rounded border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)]/40 px-2 py-1.5 text-[9px] leading-snug text-[var(--trk-text-muted)]";

  return (
    <details className="mt-4 rounded border border-[var(--trk-border)]/80 bg-[var(--trk-surface)]/50 text-[var(--trk-text-muted)]">
      <summary className="cursor-pointer select-none px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)]/20">
        Future reference · FUTURE <span className="font-normal normal-case">(expand)</span>
      </summary>
      <div className="border-t border-[var(--trk-border)]/60 px-2 pb-2 pt-1">
        <p className="mb-2 text-[9px] italic text-[var(--trk-text-muted)]">
          Architecture guardrails only — not wired to live data in this slice.
        </p>
        <div className="grid gap-1.5 sm:grid-cols-2">
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Trip Itinerary / Custody Route</div>
            <p>One physical stop → multiple load actions + custody (e.g. terminal handoff).</p>
          </div>
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Custody / Terminal Workflow</div>
            <p>Holder types: driver, terminal/yard, trailer at yard, facility, customs, disputed.</p>
          </div>
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Trip History / Activity</div>
            <p>Audited events: execution signals, custody, handoffs, exceptions.</p>
          </div>
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Driver Dispatch Package</div>
            <p>BOLs, rate cons, stop instructions — separate from execution start.</p>
          </div>
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Trailer Transfer</div>
            <p>Trailer-to-trailer transfer + custody chain.</p>
          </div>
          <div className={panelClass}>
            <div className="mb-0.5 font-semibold text-[var(--trk-text)]">Load Continuity Across Trips</div>
            <p>Commercial load continues across trips until final delivery.</p>
          </div>
        </div>
      </div>
    </details>
  );
}
