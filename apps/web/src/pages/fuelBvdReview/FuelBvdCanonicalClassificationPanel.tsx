import { useCallback, useEffect, useState } from "react";
import {
  getFuelBvdCanonicalTransactions,
  getFuelChargeCategories,
  setFuelTransactionClassification,
  type FuelCanonicalTransaction,
  type FuelChargeCategory,
} from "../../api";

type Props = {
  importId: string;
  canManage: boolean;
};

function classificationSourceLabel(source: string | null | undefined): string {
  if (!source) return "—";
  if (source === "TENANT_MAPPING") return "Tenant mapping";
  if (source === "PROVIDER_RULE") return "Provider rule";
  if (source === "MANUAL") return "Manual";
  return source;
}

export default function FuelBvdCanonicalClassificationPanel({ importId, canManage }: Props) {
  const [rows, setRows] = useState<FuelCanonicalTransaction[]>([]);
  const [categories, setCategories] = useState<FuelChargeCategory[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [txns, cats] = await Promise.all([
        getFuelBvdCanonicalTransactions(importId),
        getFuelChargeCategories(),
      ]);
      setRows(txns);
      setCategories(cats.filter((c) => c.code !== "UNMAPPED"));
    } catch (e: unknown) {
      setRows([]);
      setError(e instanceof Error ? e.message : "Canonical transactions unavailable");
    } finally {
      setLoading(false);
    }
  }, [importId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onCategoryChange = async (txnId: number, category: string, remember: boolean) => {
    await setFuelTransactionClassification(txnId, { canonical_category: category, remember_mapping: remember });
    await load();
  };

  if (loading) {
    return <p className="text-sm text-[var(--trk-text-muted)]">Loading canonical classification…</p>;
  }
  if (error) {
    return null;
  }
  if (!rows.length) {
    return null;
  }

  return (
    <section className="mt-6 border-t border-[var(--trk-border)] pt-4">
      <h3 className="text-sm font-semibold text-[var(--trk-text)]">Canonical classification</h3>
      <p className="mt-1 text-xs text-[var(--trk-text-muted)]">
        Provider source rows above are read-only. Category here is operational metadata only — it
        does not edit amounts, units, drivers, or provider reason text.
      </p>
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-[var(--trk-text-muted)]">
              <th className="py-1 pr-2">Auth / ref</th>
              <th className="py-1 pr-2">Section</th>
              <th className="py-1 pr-2">Reason / product</th>
              <th className="py-1 pr-2">Total</th>
              <th className="py-1 pr-2">Category</th>
              <th className="py-1 pr-2">Status</th>
              <th className="py-1 pr-2">Source</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-[var(--trk-border-subtle)]">
                <td className="py-1 pr-2 font-mono">{r.provider_transaction_identity ?? "—"}</td>
                <td className="py-1 pr-2">{r.provider_section_raw ?? "—"}</td>
                <td className="py-1 pr-2">
                  {r.provider_reason_raw ?? r.product_code_raw ?? "—"}
                </td>
                <td className="py-1 pr-2">{r.total_amount ?? "—"}</td>
                <td className="py-1 pr-2">
                  {canManage && r.provider_reason_raw ? (
                    <select
                      className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-1 py-0.5"
                      value={r.classification ?? "UNMAPPED"}
                      onChange={(e) => {
                        const remember = window.confirm(
                          "Remember this mapping for future matching provider text on this section?",
                        );
                        void onCategoryChange(r.id, e.target.value, remember);
                      }}
                    >
                      <option value="UNMAPPED">UNMAPPED</option>
                      {categories.map((c) => (
                        <option key={c.code} value={c.code}>{c.display_name}</option>
                      ))}
                    </select>
                  ) : (
                    r.classification ?? "UNMAPPED"
                  )}
                </td>
                <td className="py-1 pr-2">{r.classification_status ?? "—"}</td>
                <td className="py-1 pr-2">{classificationSourceLabel(r.classification_source)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
