import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { listBrokers, createBroker, type Broker } from "@/api";
import { OPS } from "@/routes";
import { parseBrokerBulkInput } from "@/utils/brokerBulkImport";
import Button from "@/components/Button";

const INPUT =
  "w-full rounded border border-[#334155] bg-[#080a0f] px-2.5 py-1.5 text-sm text-[#e8edf5] placeholder:text-[#64748b] focus:border-[#f5a623] focus:ring-0 focus:outline-none";
const LABEL = "block text-xs text-[#94a3b8] mb-1";
const SECTION_TITLE = "text-xs font-semibold uppercase tracking-wide text-[#64748b] mb-3 mt-5 first:mt-0";

type AddForm = {
  name: string;
  display_name: string;
  legal_name: string;
  mc_number: string;
  dot_number: string;
  scac: string;
  phone: string;
  phone_secondary: string;
  email: string;
  email_secondary: string;
  website: string;
  address_line1: string;
  address_line2: string;
  address_city: string;
  address_region: string;
  address_postal: string;
  address_country: string;
  classification_notes: string;
  internal_notes: string;
  notes: string;
};

const EMPTY_FORM: AddForm = {
  name: "", display_name: "", legal_name: "",
  mc_number: "", dot_number: "", scac: "",
  phone: "", phone_secondary: "", email: "", email_secondary: "", website: "",
  address_line1: "", address_line2: "", address_city: "", address_region: "",
  address_postal: "", address_country: "",
  classification_notes: "", internal_notes: "", notes: "",
};

export default function BrokersPage() {
  const [q, setQ] = useState("");
  const [draftQ, setDraftQ] = useState("");
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [includeArchived, setIncludeArchived] = useState(false);
  const [page, setPage] = useState(1);
  const size = 50;
  const [total, setTotal] = useState(0);
  const [items, setItems] = useState<Broker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add form
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState<AddForm>(EMPTY_FORM);
  const [addMsg, setAddMsg] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);

  const setField = (key: keyof AddForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  // Bulk import
  const [showBulk, setShowBulk] = useState(false);
  const [bulkText, setBulkText] = useState("");
  const [bulkRunning, setBulkRunning] = useState(false);
  const [bulkDone, setBulkDone] = useState<{ ok: number; fail: number; lastError?: string } | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listBrokers({ page, size, q: q || undefined, include_archived: includeArchived, sort: "name_asc" });
      setItems(res.items);
      setTotal(res.total);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load brokers");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [page, size, q, includeArchived]);

  useEffect(() => { void load(); }, [load]);

  const onAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) { setAddMsg("Name is required"); return; }
    setAdding(true);
    setAddMsg(null);
    const str = (v: string) => v.trim() || null;
    try {
      await createBroker({
        name: form.name.trim(),
        display_name: str(form.display_name),
        legal_name: str(form.legal_name),
        mc_number: str(form.mc_number),
        dot_number: str(form.dot_number),
        scac: str(form.scac),
        phone: str(form.phone),
        phone_secondary: str(form.phone_secondary),
        email: str(form.email),
        email_secondary: str(form.email_secondary),
        website: str(form.website),
        address_line1: str(form.address_line1),
        address_line2: str(form.address_line2),
        address_city: str(form.address_city),
        address_region: str(form.address_region),
        address_postal: str(form.address_postal),
        address_country: str(form.address_country),
        classification_notes: str(form.classification_notes),
        internal_notes: str(form.internal_notes),
        notes: str(form.notes),
      });
      setForm(EMPTY_FORM);
      setAddMsg("Created.");
      setPage(1); await load();
    } catch (err: unknown) {
      setAddMsg(err instanceof Error ? err.message : "Create failed");
    } finally {
      setAdding(false);
    }
  };

  const onBulkImport = async () => {
    const rows = parseBrokerBulkInput(bulkText);
    if (!rows.length) { setBulkDone({ ok: 0, fail: 0, lastError: "No rows parsed" }); return; }
    setBulkRunning(true); setBulkDone(null);
    let ok = 0, fail = 0, lastError = "";
    for (const row of rows) {
      try { await createBroker({ name: row.name, mc_number: row.mc_number, notes: row.notes ?? null }); ok++; }
      catch (e: unknown) { fail++; lastError = e instanceof Error ? e.message : "error"; }
    }
    setBulkRunning(false); setBulkDone({ ok, fail, lastError: lastError || undefined });
    setPage(1); await load();
  };

  const totalPages = Math.max(1, Math.ceil(total / size));

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 text-[#e8edf5]">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#f5a623]">Freight brokers</h1>
          <p className="mt-1 text-sm text-[#64748b]">{total} broker{total !== 1 ? "s" : ""}</p>
        </div>
        <Button type="button" variant="primary" onClick={() => { setShowAdd((v) => !v); setAddMsg(null); }}>
          {showAdd ? "Cancel" : "+ Add broker"}
        </Button>
      </div>

      {/* Add broker form */}
      {showAdd && (
        <form onSubmit={onAdd} className="mb-6 rounded-xl border border-[#1a2231] bg-[#0d111a] p-5">
          <h2 className="mb-4 text-sm font-semibold text-[#e8edf5]">New broker</h2>

          {/* Identity */}
          <p className={SECTION_TITLE}>Identity</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL}>Name <span className="text-rose-400">*</span></label>
              <input className={INPUT} value={form.name} onChange={setField("name")} placeholder="Short / list name" autoFocus />
            </div>
            <div>
              <label className={LABEL}>Display name</label>
              <input className={INPUT} value={form.display_name} onChange={setField("display_name")} placeholder="Shown in UI" />
            </div>
            <div>
              <label className={LABEL}>Legal name</label>
              <input className={INPUT} value={form.legal_name} onChange={setField("legal_name")} placeholder="Full registered name" />
            </div>
            <div>
              <label className={LABEL}>MC number</label>
              <input className={INPUT} value={form.mc_number} onChange={setField("mc_number")} placeholder="MC-123456" />
            </div>
            <div>
              <label className={LABEL}>DOT / USDOT</label>
              <input className={INPUT} value={form.dot_number} onChange={setField("dot_number")} placeholder="DOT number" />
            </div>
            <div>
              <label className={LABEL}>SCAC</label>
              <input className={INPUT} value={form.scac} onChange={setField("scac")} placeholder="4-letter code" />
            </div>
          </div>

          {/* Contact */}
          <p className={SECTION_TITLE}>Contact</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className={LABEL}>Phone primary</label>
              <input className={INPUT} value={form.phone} onChange={setField("phone")} placeholder="+1 800 000 0000" />
            </div>
            <div>
              <label className={LABEL}>Phone secondary</label>
              <input className={INPUT} value={form.phone_secondary} onChange={setField("phone_secondary")} />
            </div>
            <div>
              <label className={LABEL}>Email primary</label>
              <input className={INPUT} type="email" value={form.email} onChange={setField("email")} placeholder="ops@broker.com" />
            </div>
            <div>
              <label className={LABEL}>Email secondary</label>
              <input className={INPUT} type="email" value={form.email_secondary} onChange={setField("email_secondary")} />
            </div>
            <div className="sm:col-span-2">
              <label className={LABEL}>Website</label>
              <input className={INPUT} value={form.website} onChange={setField("website")} placeholder="https://broker.com" />
            </div>
          </div>

          {/* Address */}
          <p className={SECTION_TITLE}>Address</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <label className={LABEL}>Line 1</label>
              <input className={INPUT} value={form.address_line1} onChange={setField("address_line1")} />
            </div>
            <div className="sm:col-span-2">
              <label className={LABEL}>Line 2</label>
              <input className={INPUT} value={form.address_line2} onChange={setField("address_line2")} />
            </div>
            <div>
              <label className={LABEL}>City</label>
              <input className={INPUT} value={form.address_city} onChange={setField("address_city")} />
            </div>
            <div>
              <label className={LABEL}>State / region</label>
              <input className={INPUT} value={form.address_region} onChange={setField("address_region")} />
            </div>
            <div>
              <label className={LABEL}>Postal code</label>
              <input className={INPUT} value={form.address_postal} onChange={setField("address_postal")} />
            </div>
            <div>
              <label className={LABEL}>Country (ISO-2)</label>
              <input className={INPUT} value={form.address_country} onChange={setField("address_country")} placeholder="US" maxLength={2} />
            </div>
          </div>

          {/* Notes */}
          <p className={SECTION_TITLE}>Notes</p>
          <div className="grid gap-3">
            <div>
              <label className={LABEL}>Classification notes</label>
              <textarea className={`${INPUT} min-h-[60px]`} value={form.classification_notes} onChange={setField("classification_notes")} placeholder="How you tag this broker operationally" />
            </div>
            <div>
              <label className={LABEL}>Internal notes</label>
              <textarea className={`${INPUT} min-h-[60px]`} value={form.internal_notes} onChange={setField("internal_notes")} placeholder="Not shown on documents" />
            </div>
            <div>
              <label className={LABEL}>General notes</label>
              <textarea className={`${INPUT} min-h-[60px]`} value={form.notes} onChange={setField("notes")} />
            </div>
          </div>

          <div className="mt-5 flex items-center gap-3">
            <Button type="submit" variant="primary" disabled={adding}>{adding ? "Creating…" : "Create broker"}</Button>
            {addMsg && (
              <span className={`text-xs ${addMsg.startsWith("Created") ? "text-emerald-400" : "text-rose-400"}`}>{addMsg}</span>
            )}
          </div>
        </form>
      )}

      {/* Search + filters */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <div className="flex-1 min-w-[200px]">
          <input
            className={INPUT}
            value={draftQ}
            onChange={(e) => {
              const val = e.target.value;
              setDraftQ(val);
              if (debounceRef.current) clearTimeout(debounceRef.current);
              debounceRef.current = setTimeout(() => { setQ(val); setPage(1); }, 300);
            }}
            placeholder="Search name, MC, domain, alias, sender…"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-[#94a3b8]">
          <input type="checkbox" checked={includeArchived} onChange={(e) => { setIncludeArchived(e.target.checked); setPage(1); }} className="rounded border-[#334155]" />
          Show archived
        </label>
      </div>

      {/* Directory table */}
      {error && <p className="mb-3 text-sm text-rose-400">{error}</p>}
      <div className="rounded-xl border border-[#1a2231] bg-[#0d111a]">
        {loading ? (
          <p className="p-6 text-sm text-[#64748b]">Loading…</p>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-[#1a2231]">
              <tr className="text-xs uppercase tracking-wide text-[#64748b]">
                <th className="px-4 py-2.5 text-left">Broker</th>
                <th className="px-4 py-2.5 text-left">MC #</th>
                <th className="px-4 py-2.5 text-left">Status</th>
                <th className="px-4 py-2.5"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1a2231]">
              {items.map((b) => (
                <tr key={b.id} className="hover:bg-[#141924]/60">
                  <td className="px-4 py-2.5 font-medium text-[#e8edf5]">
                    {(b.display_name || b.legal_name || b.name).trim()}
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-[#94a3b8]">{b.mc_number ?? "—"}</td>
                  <td className="px-4 py-2.5">
                    {b.is_active === false
                      ? <span className="rounded bg-[#422006] px-2 py-0.5 text-xs text-[#fdba74]">Archived</span>
                      : <span className="rounded bg-[#052e16] px-2 py-0.5 text-xs text-[#86efac]">Active</span>}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <Link to={OPS.BROKER_DETAIL(b.id)} className="text-sm font-medium text-[#f5a623] hover:underline">Open →</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {!loading && items.length === 0 && (
          <p className="p-6 text-center text-sm text-[#64748b]">No brokers found.</p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center gap-3">
          <Button type="button" variant="secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-xs text-[#64748b]">Page {page} / {totalPages}</span>
          <Button type="button" variant="secondary" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}

      {/* Bulk import — collapsed by default */}
      <div className="mt-8 border-t border-[#1a2231] pt-4">
        <button
          type="button"
          className="text-xs text-[#64748b] hover:text-[#94a3b8]"
          onClick={() => setShowBulk((v) => !v)}
        >
          {showBulk ? "▾" : "▸"} Bulk import
        </button>
        {showBulk && (
          <div className="mt-3 rounded-xl border border-[#1a2231] bg-[#0d111a] p-4">
            <p className="mb-2 text-xs text-[#64748b]">
              One broker per line — <code className="text-[#cbd5e1]">Name[TAB]MC</code> or <code className="text-[#cbd5e1]">Name, MC</code>. Lines starting with # are ignored.
            </p>
            <textarea
              className={`${INPUT} min-h-[160px] font-mono text-xs`}
              value={bulkText}
              onChange={(e) => setBulkText(e.target.value)}
              placeholder={"J.B. Hunt Transport\tMC-123456\nCH Robinson, MC-234567"}
              disabled={bulkRunning}
            />
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <Button type="button" variant="secondary" disabled={bulkRunning} onClick={() => void onBulkImport()}>
                {bulkRunning ? "Importing…" : "Import"}
              </Button>
              {bulkDone && (
                <span className="text-xs text-[#94a3b8]">
                  <span className="text-emerald-400">{bulkDone.ok}</span> created
                  {bulkDone.fail > 0 && <>, <span className="text-rose-400">{bulkDone.fail}</span> failed</>}
                  {bulkDone.lastError && bulkDone.fail > 0 && (
                    <span className="ml-2 text-rose-300" title={bulkDone.lastError}>(last: {bulkDone.lastError.slice(0, 80)})</span>
                  )}
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
