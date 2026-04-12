/**
 * Settlement section — read-only payroll view for a load.
 *
 * Calls GET /api/v1/payroll/loads/{load_id}/settlement — a single indexed query that
 * joins pay_run_items to pay_runs/pay_periods via JSONB containment. Replaces the
 * previous fan-out pattern (listPayRuns + N × getPayRunItems).
 */
import { useEffect, useState } from "react";
import { getLoadSettlement, type Load, type LoadSettlementItem } from "@/api";
import { wsSectionBody, wsSectionCard, wsSectionHeader, wsSectionTitle } from "@/loadWorkspace/loadWorkspaceShared";

function fmt(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(n);
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-2 py-1">
      <span className="text-[11px] text-[#7a8299]">{label}</span>
      <span className={`text-[12px] text-[#e8ecf4] ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}

export function SectionSettlement({ load }: { load: Load }) {
  const [items, setItems] = useState<LoadSettlementItem[]>([]);
  const [net, setNet] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    getLoadSettlement(load.id)
      .then((res) => {
        if (!cancelled) {
          setItems(res.items);
          setNet(res.net_total);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load settlement data");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [load.id]);

  const earnings = items.filter((i) => i.amount_signed >= 0);
  const deductions = items.filter((i) => i.amount_signed < 0);

  return (
    <section className={wsSectionCard}>
      <div className={wsSectionHeader}>
        <span className={wsSectionTitle}>Settlement</span>
        {load.trip_number ? (
          <span className="font-mono text-[10px] text-[#4a5068]">{load.trip_number}</span>
        ) : null}
      </div>
      <div className={wsSectionBody}>
        {/* Load-level context */}
        <div className="mb-4 space-y-0 divide-y divide-[#252a38] rounded-md border border-[#252a38] px-3">
          <Row
            label="Driver"
            value={
              load.driver
                ? `${load.driver.first_name} ${load.driver.last_name}`.trim()
                : "—"
            }
          />
          <Row label="Truck" value={load.truck?.unit_number ?? "—"} />
          <Row label="Broker rate" value={load.rate != null ? fmt(load.rate) : "—"} />
          <Row label="Customer rate" value={load.customer_rate != null ? fmt(load.customer_rate) : "—"} />
          <Row label="Miles" value={load.miles != null ? String(load.miles) : "—"} />
        </div>

        {loading ? (
          <p className="py-4 text-center text-xs text-[#7a8299]">Loading pay items…</p>
        ) : error ? (
          <p className="rounded-md border border-red-900/40 bg-red-950/20 px-3 py-2 text-xs text-red-400">{error}</p>
        ) : items.length === 0 ? (
          <p className="rounded-md border border-dashed border-[#252a38] px-3 py-4 text-center text-xs text-[#4a5068]">
            No pay run items found for this load.
          </p>
        ) : (
          <div className="space-y-3">
            {earnings.length > 0 && (
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[#7a8299]">Earnings</p>
                <div className="divide-y divide-[#252a38] rounded-md border border-[#252a38] px-3">
                  {earnings.map((item) => (
                    <div key={item.id} className="flex items-baseline justify-between gap-2 py-1.5">
                      <div className="min-w-0">
                        <p className="truncate text-[12px] text-[#e8ecf4]">{item.description}</p>
                        <p className="text-[10px] text-[#4a5068]">
                          {item.source_type.replace(/_/g, " ")}
                          {item.quantity != null && item.unit_rate != null
                            ? ` · ${item.quantity} × ${fmt(item.unit_rate)}`
                            : ""}
                          {" · "}
                          {item.pay_period_start} – {item.pay_period_end}
                        </p>
                      </div>
                      <span className="shrink-0 font-mono text-[12px] text-emerald-400">
                        {fmt(item.amount_signed)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {deductions.length > 0 && (
              <div>
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[#7a8299]">Deductions</p>
                <div className="divide-y divide-[#252a38] rounded-md border border-[#252a38] px-3">
                  {deductions.map((item) => (
                    <div key={item.id} className="flex items-baseline justify-between gap-2 py-1.5">
                      <div className="min-w-0">
                        <p className="truncate text-[12px] text-[#e8ecf4]">{item.description}</p>
                        <p className="text-[10px] text-[#4a5068]">{item.source_type.replace(/_/g, " ")}</p>
                      </div>
                      <span className="shrink-0 font-mono text-[12px] text-red-400">
                        {fmt(item.amount_signed)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="flex items-center justify-between border-t border-[#252a38] pt-2">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-[#7a8299]">Net driver pay</span>
              <span className={`font-mono text-sm font-bold ${net >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                {fmt(net)}
              </span>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
