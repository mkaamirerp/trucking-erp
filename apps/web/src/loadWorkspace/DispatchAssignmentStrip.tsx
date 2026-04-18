/**
 * Dispatch context panel: assign unassigned loads without leaving the canonical load workspace.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";
import Button from "@/components/Button";
import type { Driver, Trailer, Truck } from "@/api";

const inputCls =
  "w-full rounded-md border border-[#2b3347] bg-[#101522] px-2.5 py-1.5 text-xs text-[var(--trk-text)] outline-none placeholder:text-[var(--trk-text-muted)] focus:border-[var(--trk-heading)]/50";

function SearchablePick({
  label,
  placeholder,
  items,
  valueId,
  onSelect,
  disabled,
  primary,
}: {
  label: string;
  placeholder: string;
  items: { id: number; label: string }[];
  valueId: number | null;
  onSelect: (id: number | null) => void;
  disabled?: boolean;
  primary?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const boxRef = useRef<HTMLDivElement | null>(null);

  const selectedLabel = useMemo(() => {
    if (valueId == null) return "";
    return items.find((i) => i.id === valueId)?.label ?? "";
  }, [items, valueId]);

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase();
    if (!qq) return items.slice(0, 100);
    return items.filter((i) => i.label.toLowerCase().includes(qq)).slice(0, 100);
  }, [items, q]);

  useEffect(() => {
    function onDoc(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  useEffect(() => {
    if (!open) setQ("");
  }, [open, selectedLabel]);

  return (
    <div ref={boxRef} className={clsx("relative flex min-w-0 flex-1 flex-col gap-1", primary && "sm:flex-[1.25]")}>
      <label className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">{label}</label>
      <div className="relative">
        <input
          className={inputCls}
          disabled={disabled}
          placeholder={placeholder}
          value={open ? q : selectedLabel}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
          }}
          onFocus={() => {
            setQ(selectedLabel);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "Escape") setOpen(false);
          }}
          autoComplete="off"
        />
        {open && !disabled ? (
          <ul
            className="absolute z-[60] mt-1 max-h-52 w-full overflow-auto rounded-md border border-[#2b3347] bg-[#0d1117] py-1 shadow-xl"
            role="listbox"
          >
            <li>
              <button
                type="button"
                className="w-full px-2.5 py-1.5 text-left text-[11px] text-[var(--trk-text-muted)] hover:bg-[#1e2330]"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => {
                  onSelect(null);
                  setOpen(false);
                }}
              >
                — Clear —
              </button>
            </li>
            {filtered.map((it) => (
              <li key={it.id}>
                <button
                  type="button"
                  className="w-full px-2.5 py-1.5 text-left text-xs text-[var(--trk-text)] hover:bg-[#1e2330]"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => {
                    onSelect(it.id);
                    setOpen(false);
                  }}
                >
                  {it.label}
                </button>
              </li>
            ))}
            {filtered.length === 0 ? (
              <li className="px-2.5 py-2 text-[11px] text-[#64748b]">No matches</li>
            ) : null}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

export function DispatchAssignmentStrip(p: {
  drivers: Driver[];
  trucks: Truck[];
  trailers: Trailer[];
  driverId: number | null;
  truckId: number | null;
  trailerId: number | null;
  onDriverSelect: (id: number | null) => void;
  onTruckSelect: (id: number | null) => void;
  onTrailerSelect: (id: number | null) => void;
  onAssign: () => void;
  saving: boolean;
  message?: string | null;
}) {
  const driverItems = useMemo(
    () =>
      p.drivers.map((d) => ({
        id: d.id,
        label: `${d.first_name} ${d.last_name}`.trim() + (d.phone ? ` · ${d.phone}` : ""),
      })),
    [p.drivers],
  );
  const truckItems = useMemo(
    () =>
      [...p.trucks]
        .sort((a, b) => a.unit_number.localeCompare(b.unit_number))
        .map((t) => ({ id: t.id, label: t.unit_number })),
    [p.trucks],
  );
  const trailerItems = useMemo(
    () =>
      [...p.trailers]
        .sort((a, b) => a.unit_number.localeCompare(b.unit_number))
        .map((t) => ({
          id: t.id,
          label: [t.unit_number, t.trailer_type].filter(Boolean).join(" · "),
        })),
    [p.trailers],
  );

  const canAssign = p.driverId != null && !p.saving;

  return (
    <div className="shrink-0 border-b border-[var(--trk-heading)]/25 bg-gradient-to-r from-[#1a1408] via-[#12151c] to-[#0d1018]">
      <div className="mx-auto flex max-w-[1600px] flex-col gap-3 px-4 py-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--trk-heading)]/90">Dispatch assignment</p>
            <p className="mt-0.5 text-[11px] text-[var(--trk-text-muted)]">
              Assign driver and equipment. This sets status to Assigned only — no trip number until the load is
              Dispatched.
            </p>
          </div>
          <Button type="button" variant="primary" disabled={!canAssign} onClick={() => p.onAssign()}>
            {p.saving ? "Saving…" : "Assign load"}
          </Button>
        </div>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-end">
          <SearchablePick
            label="Driver"
            placeholder="Search driver…"
            items={driverItems}
            valueId={p.driverId}
            onSelect={p.onDriverSelect}
            disabled={p.saving}
            primary
          />
          <SearchablePick
            label="Truck"
            placeholder="Search unit #…"
            items={truckItems}
            valueId={p.truckId}
            onSelect={p.onTruckSelect}
            disabled={p.saving}
          />
          <SearchablePick
            label="Trailer"
            placeholder="Search trailer…"
            items={trailerItems}
            valueId={p.trailerId}
            onSelect={p.onTrailerSelect}
            disabled={p.saving}
          />
        </div>
        {p.message ? <p className="text-[11px] text-[var(--trk-text-muted)]">{p.message}</p> : null}
      </div>
    </div>
  );
}
