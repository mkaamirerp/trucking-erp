/**
 * Freight brokers — list, search, single add, bulk import (name + MC).
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { clsx } from "clsx";
import { listBrokers, createBroker, type Broker } from "@/api";
import { OPS } from "@/routes";
import { parseBrokerBulkInput } from "@/utils/brokerBulkImport";
import Button from "@/components/Button";

const INPUT =
  "w-full rounded border border-[#334155] bg-[#080a0f] px-2.5 py-1.5 text-sm text-[#e8edf5] placeholder:text-[#64748b] focus:border-[#f5a623] focus:ring-0 focus:outline-none";
const LABEL = "block text-xs font-medium text-[#94a3b8] mb-1";

export default function BrokersPage() {
  const [draftQ, setDraftQ] = useState("");
  const [q, setQ] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [sort, setSort] = useState<"name_asc" | "name_desc" | "id_desc">("name_asc");
  const [page, setPage] = useState(1);
  const size = 50;
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<Broker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [singleName, setSingleName] = useState("");
  const [singleMc, setSingleMc] = useState("");
  const [singleMsg, setSingleMsg] = useState<string | null>(null);

  const [bulkText, setBulkText] = useState("");
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkDone, setBulkDone] = useState<{ ok: number; fail: number; lastError?: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listBrokers({ page, size, q: q || undefined, include_archived: includeArchived, sort });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load brokers");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [page, size, q, includeArchived, sort]);

  useEffect(() => {
    void load();
  }, [load]);

  const onAddOne = async (e: React.FormEvent) => {
    e.preventDefault();
    setSingleMsg(null);
    if (!singleName.trim()) {
      setSingleMsg("Name is required");
      return;
    }
    try {
      await createBroker({ name: singleName.trim(), mc_number: singleMc.trim() || null });
      setSingleName("");
      setSingleMc("");
      setSingleMsg("Created.");
      setPage(1);
      await load();
    } catch (err: unknown) {
      setSingleMsg(err instanceof Error ? err.message : "Create failed");
    }
  };

  const onBulkImport = async () => {
    const rows = parseBrokerBulkInput(bulkText);
    if (!rows.length) {
      setBulkDone({ ok: 0, fail: 0, lastError: "No rows to import (use Name<TAB>MC or Name, MC per line)" });
      return;
    }
    setBulkRunning(true);
    setBulkDone(null);
    let ok = 0;
    let fail = 0;
    let lastError = "";
    for (const row of rows) {
      try {
        await createBroker({
          name: row.name,
          mc_number: row.mc_number,
          notes: row.notes ?? null,
        });
        ok += 1;
      } catch (e: unknown) {
        fail += 1;
        lastError = e instanceof Error ? e.message : "error";
      }
    }
    setBulkRunning(false);
    setBulkDone({ ok, fail, lastError: lastError || undefined });
    setPage(1);
    await load();
  };

  const totalPages = Math.max(1, Math.ceil(total / size));

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 text-[#e8edf5]">
      <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#f5a623]">Freight brokers</h1>
          <p className="mt-1 text-sm text-[#94a3b8]">
            Operational broker list (MC / intake). Bulk paste: one broker per line — <code className="text-[#cbd5e1]">Name[TAB]MC</code> or{" "}
            <code className="text-[#cbd5e1]">Name, MC</code>. Name-only lines are allowed (MC blank).
          </p>
        </div>
      </div>

      <div className="mb-8 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
          <h2 className="mb-3 text-sm font-semibold text-[#e8edf5]">Add one broker</h2>
          <form onSubmit={onAddOne} className="space-y-3">
            <div>
              <label className={LABEL}>Name</label>
              <input className={INPUT} value={singleName} onChange={(e) => setSingleName(e.target.value)} placeholder="Broker legal / display name" />
            </div>
            <div>
              <label className={LABEL}>MC number</label>
              <input className={INPUT} value={singleMc} onChange={(e) => setSingleMc(e.target.value)} placeholder="Optional" />
            </div>
            <Button type="submit" variant="primary">
              Create broker
            </Button>
            {singleMsg && <p className={clsx("text-xs", singleMsg.startsWith("Created") ? "text-emerald-400" : "text-rose-400")}>{singleMsg}</p>}
          </form>
        </section>

        <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
          <h2 className="mb-3 text-sm font-semibold text-[#e8edf5]">Bulk import</h2>
          <p className="mb-2 text-xs text-[#64748b]">Paste hundreds of rows. Lines starting with # are ignored.</p>
          <textarea
            className={clsx(INPUT, "min-h-[180px] font-mono text-xs")}
            value={bulkText}
            onChange={(e) => setBulkText(e.target.value)}
            placeholder={
              "Rank,Company Name,MC Number,Headquarters\n1,Example Logistics,MC-999999,\"Austin, TX\"\nOr tab: Name\tMC-123"
            }
            disabled={bulkRunning}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button type="button" variant="primary" disabled={bulkRunning} onClick={() => void onBulkImport()}>
              {bulkRunning ? "Importing…" : "Import all lines"}
            </Button>
            {bulkDone && (
              <span className="text-xs text-[#94a3b8]">
                Done: <span className="text-emerald-400">{bulkDone.ok}</span> created
                {bulkDone.fail > 0 && (
                  <>
                    , <span className="text-rose-400">{bulkDone.fail}</span> failed
                  </>
                )}
                {bulkDone.lastError && bulkDone.fail > 0 && (
                  <span className="ml-2 max-w-md truncate text-rose-300" title={bulkDone.lastError}>
                    (last: {bulkDone.lastError.slice(0, 120)}…)
                  </span>
                )}
              </span>
            )}
          </div>
        </section>
      </div>

      <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 shadow-[0_8px_32px_rgba(0,0,0,0.25)]">
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
          <div className="min-w-[200px] flex-1">
            <label className={LABEL}>Search</label>
            <input
              className={INPUT}
              value={draftQ}
              onChange={(e) => setDraftQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  setQ(draftQ);
                  setPage(1);
                }
              }}
              placeholder="Name, MC, DOT, domain, alias, known sender…"
            />
          </div>
          <div>
            <label className={LABEL}>Sort</label>
            <select className={INPUT} value={sort} onChange={(e) => setSort(e.target.value as typeof sort)}>
              <option value="name_asc">Name A–Z</option>
              <option value="name_desc">Name Z–A</option>
              <option value="id_desc">Newest id</option>
            </select>
          </div>
          <label className="flex cursor-pointer items-center gap-2 text-sm text-[#94a3b8]">
            <input type="checkbox" checked={includeArchived} onChange={(e) => setIncludeArchived(e.target.checked)} className="rounded border-[#334155]" />
            Show archived
          </label>
          <Button
            type="button"
            variant="secondary"
            onClick={() => {
              setQ(draftQ);
              setPage(1);
            }}
          >
            Apply
          </Button>
        </div>

        {error && <p className="mb-3 text-sm text-rose-400">{error}</p>}
        {loading ? (
          <p className="text-sm text-[#64748b]">Loading…</p>
        ) : (
          <>
            <p className="mb-2 text-xs text-[#64748b]">
              {total} broker{total !== 1 ? "s" : ""} · page {page} / {totalPages}
            </p>
            <div className="overflow-x-auto rounded-lg border border-[#1a2231]">
              <table className="w-full text-left text-sm">
                <thead className="bg-[#141924] text-xs uppercase tracking-wide text-[#64748b]">
                  <tr>
                    <th className="px-3 py-2">Display</th>
                    <th className="px-3 py-2">MC</th>
                    <th className="px-3 py-2">DOT</th>
                    <th className="px-3 py-2">Status</th>
                    <th className="px-3 py-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#1a2231]">
                  {items.map((b) => (
                    <tr key={b.id} className="hover:bg-[#141924]/60">
                      <td className="px-3 py-2 font-medium text-[#e8edf5]">
                        {(b.display_name || b.legal_name || b.name).trim()}
                      </td>
                      <td className="px-3 py-2 text-[#94a3b8]">{b.mc_number ?? "—"}</td>
                      <td className="px-3 py-2 text-[#94a3b8]">{b.dot_number ?? "—"}</td>
                      <td className="px-3 py-2">
                        {b.is_active === false ? (
                          <span className="rounded bg-[#422006] px-2 py-0.5 text-xs text-[#fdba74]">Archived</span>
                        ) : (
                          <span className="rounded bg-[#052e16] px-2 py-0.5 text-xs text-[#86efac]">Active</span>
                        )}
            </td>
                      <td className="px-3 py-2 text-right">
                        <Link to={OPS.BROKER_DETAIL(b.id)} className="text-sm font-medium text-[#f5a623] hover:underline">
                          Open
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {items.length === 0 && <p className="p-6 text-center text-sm text-[#64748b]">No brokers match.</p>}
            </div>
            <div className="mt-4 flex gap-2">
              <Button type="button" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>
                Previous
              </Button>
              <Button type="button" variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}
