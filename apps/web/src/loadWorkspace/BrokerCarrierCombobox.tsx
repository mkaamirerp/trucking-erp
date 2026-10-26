import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { Broker } from "@/api";
import { brokerDisplayName } from "@/loadWorkspace/workspaceCreateLoadValidation";
import {
  parseConfidenceDotClass,
  parseConfidenceTierLabel,
  type ParseConfidenceTier,
} from "@/loadWorkspace/parseFieldConfidenceUi";

const inputClass =
  "w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2 text-sm text-[var(--trk-text)] placeholder:text-[var(--trk-text-muted)] focus:border-amber-500 focus:outline-none";

type Props = {
  brokers: Broker[];
  brokerId: number | null;
  brokerNameSnapshot: string;
  disabled?: boolean;
  onPick: (brokerId: number | null, nameSnapshot: string) => void;
  docFocusHandlers?: { onFocus?: () => void; onClick?: () => void };
  confidenceTier?: ParseConfidenceTier | null;
};

export default function BrokerCarrierCombobox({
  brokers,
  brokerId,
  brokerNameSnapshot,
  disabled,
  onPick,
  docFocusHandlers,
  confidenceTier = null,
}: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState(brokerNameSnapshot);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    setQuery(brokerNameSnapshot);
  }, [brokerNameSnapshot]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return brokers.slice(0, 40);
    return brokers
      .filter((b) => {
        const label = brokerDisplayName(b).toLowerCase();
        const mc = (b.mc_number ?? "").toLowerCase();
        const dot = (b.dot_number ?? "").toLowerCase();
        return label.includes(q) || mc.includes(q) || dot.includes(q);
      })
      .slice(0, 40);
  }, [brokers, query]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  function commitFreeText(text: string) {
    const trimmed = text.trim();
    if (brokerId != null) {
      const b = brokers.find((x) => x.id === brokerId);
      if (b && brokerDisplayName(b) === trimmed) return;
    }
    onPick(null, trimmed);
  }

  function pickBroker(b: Broker) {
    const name = brokerDisplayName(b);
    setQuery(name);
    onPick(b.id, name);
    setOpen(false);
  }

  return (
    <div ref={rootRef} className="relative sm:col-span-2" data-testid="broker-carrier-combobox">
      <label className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-[var(--trk-text-muted)]">
        {confidenceTier ? (
          <span
            className={parseConfidenceDotClass(confidenceTier)}
            title={`AI extraction: ${parseConfidenceTierLabel(confidenceTier)}`}
            aria-hidden
          />
        ) : null}
        Broker/Carrier
      </label>
      <input
        className={inputClass}
        value={query}
        disabled={disabled}
        placeholder="Type to search brokers or enter a carrier name (e.g. Jaysm Logistics)"
        autoComplete="off"
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        onFocus={() => {
          setOpen(true);
          docFocusHandlers?.onFocus?.();
        }}
        onClick={() => docFocusHandlers?.onClick?.()}
        onChange={(e) => {
          const v = e.target.value;
          setQuery(v);
          setOpen(true);
          commitFreeText(v);
        }}
        onBlur={() => {
          commitFreeText(query);
          window.setTimeout(() => setOpen(false), 150);
        }}
      />
      {open && filtered.length > 0 ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] py-1 text-sm shadow-lg"
        >
          {filtered.map((b) => (
            <li key={b.id}>
              <button
                type="button"
                role="option"
                className="w-full px-3 py-2 text-left hover:bg-[var(--trk-surface)]"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => pickBroker(b)}
              >
                <span className="font-medium text-[var(--trk-text)]">{brokerDisplayName(b)}</span>
                {b.mc_number ? (
                  <span className="ml-2 text-[11px] text-[var(--trk-text-muted)]">MC {b.mc_number}</span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {open && query.trim() && filtered.length === 0 ? (
        <p className="absolute z-30 mt-1 w-full rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] px-3 py-2 text-xs text-[var(--trk-text-muted)] shadow-lg">
          No broker match — &quot;{query.trim()}&quot; will be saved as the carrier name on this load.
        </p>
      ) : null}
    </div>
  );
}
