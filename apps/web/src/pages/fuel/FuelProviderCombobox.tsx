import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { FuelProviderCatalog } from "../../api";
import { FUEL_QUICK_PROVIDER_CODES } from "./fuelDashboardData";
import { readLastFuelProviderCode } from "./fuelLastProvider";

type Props = {
  catalog: FuelProviderCatalog[];
  value: string;
  onChange: (providerCode: string) => void;
  disabled?: boolean;
};

export default function FuelProviderCombobox({ catalog, value, onChange, disabled }: Props) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listId = useId();

  const selected = useMemo(
    () => catalog.find((p) => p.provider_code === value),
    [catalog, value],
  );

  const lastUsed = readLastFuelProviderCode();

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return catalog;
    return catalog.filter(
      (p) =>
        p.provider_code.toLowerCase().includes(q) ||
        p.display_name.toLowerCase().includes(q),
    );
  }, [catalog, query]);

  const recentProviders = useMemo(() => {
    const codes = new Set<string>();
    const out: FuelProviderCatalog[] = [];
    if (lastUsed) {
      const p = catalog.find((c) => c.provider_code === lastUsed);
      if (p) {
        codes.add(p.provider_code);
        out.push(p);
      }
    }
    for (const code of FUEL_QUICK_PROVIDER_CODES) {
      if (codes.has(code)) continue;
      const p = catalog.find((c) => c.provider_code === code);
      if (p) {
        codes.add(code);
        out.push(p);
      }
    }
    return out;
  }, [catalog, lastUsed]);

  const otherProviders = useMemo(() => {
    const recentCodes = new Set(recentProviders.map((p) => p.provider_code));
    const q = query.trim().toLowerCase();
    return filtered.filter((p) => !recentCodes.has(p.provider_code) || q.length > 0);
  }, [filtered, recentProviders, query]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQuery("");
      }
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => searchRef.current?.focus(), 0);
      return () => window.clearTimeout(t);
    }
    setQuery("");
    return undefined;
  }, [open]);

  function pick(code: string) {
    onChange(code);
    setOpen(false);
    setQuery("");
  }

  const showRecent = query.trim().length === 0 && recentProviders.length > 0;

  return (
    <div ref={rootRef} className="relative min-w-[12rem] max-w-md flex-1" data-testid="fuel-provider-combobox">
      <span className="mb-0.5 block text-xs font-medium text-[var(--trk-text-muted)]">Provider</span>
      <button
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        className="flex w-full items-center justify-between gap-2 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2.5 py-1.5 text-left text-xs text-[var(--trk-text)] disabled:opacity-50"
        onClick={() => setOpen((v) => !v)}
        data-testid="fuel-provider-combobox-trigger"
      >
        <span className="truncate font-medium">{selected?.display_name ?? value ?? "Select provider"}</span>
        <span className="text-[var(--trk-text-muted)]" aria-hidden="true">▾</span>
      </button>
      {open ? (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-1 max-h-[min(20rem,50vh)] overflow-hidden rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] shadow-lg"
          data-testid="fuel-provider-combobox-panel"
        >
          <div className="border-b border-[var(--trk-border)] p-2">
            <input
              ref={searchRef}
              type="search"
              placeholder="Search providers..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="w-full rounded border border-[var(--trk-border)] bg-[var(--trk-surface-2)] px-2 py-1.5 text-xs"
              data-testid="fuel-provider-combobox-search"
            />
          </div>
          <ul id={listId} role="listbox" className="max-h-[min(16rem,40vh)] overflow-y-auto py-1 text-xs">
            {showRecent ? (
              <li>
                <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                  Recently used
                </div>
                {recentProviders.map((p) => (
                  <button
                    key={`recent-${p.provider_code}`}
                    type="button"
                    role="option"
                    aria-selected={p.provider_code === value}
                    className={`block w-full px-2.5 py-1.5 text-left hover:bg-[var(--trk-surface-2)] ${
                      p.provider_code === value ? "bg-[var(--trk-surface-2)] font-medium" : ""
                    }`}
                    onClick={() => pick(p.provider_code)}
                  >
                    {p.display_name}
                  </button>
                ))}
              </li>
            ) : null}
            <li>
              <div className="px-2.5 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                Providers
              </div>
              {(query.trim() ? filtered : otherProviders).map((p) => (
                <button
                  key={p.provider_code}
                  type="button"
                  role="option"
                  aria-selected={p.provider_code === value}
                  className={`block w-full px-2.5 py-1.5 text-left hover:bg-[var(--trk-surface-2)] ${
                    p.provider_code === value ? "bg-[var(--trk-surface-2)] font-medium" : ""
                  }`}
                  onClick={() => pick(p.provider_code)}
                >
                  {p.display_name}
                </button>
              ))}
              {(query.trim() ? filtered : otherProviders).length === 0 ? (
                <p className="px-2.5 py-2 text-[var(--trk-text-muted)]">No providers match.</p>
              ) : null}
            </li>
          </ul>
        </div>
      ) : null}
    </div>
  );
}
