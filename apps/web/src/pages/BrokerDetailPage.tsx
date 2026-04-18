import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  getBrokerWorkspace,
  archiveBroker,
  unarchiveBroker,
  updateBroker,
  createBrokerContact,
  createBrokerDomain,
  createBrokerAlias,
  createBrokerKnownSender,
  type Broker,
  type BrokerContact,
  type BrokerWorkspace,
} from "@/api";
import { OPS } from "@/routes";
import Button from "@/components/Button";

// ─── Shared style tokens ────────────────────────────────────────────────────

const INPUT =
  "w-full rounded border border-[#334155] bg-[var(--trk-bg)] px-2.5 py-1.5 text-sm text-[var(--trk-text)] placeholder:text-[#64748b] focus:border-[var(--trk-heading)] focus:ring-0 focus:outline-none";
const TEXTAREA = `${INPUT} min-h-[72px] resize-y`;
const LABEL = "block text-xs text-[var(--trk-text-muted)] mb-1";
const SECTION = "rounded-xl border border-[#1a2231] bg-[#0d111a] p-5";
const SECTION_HEADING = "text-sm font-semibold text-[var(--trk-text)] mb-4";
const SUBSECTION_HEADING = "text-xs font-semibold uppercase tracking-wide text-[#64748b] mb-2";
const READ_ONLY_VALUE = "min-h-[38px] rounded border border-transparent bg-transparent px-0 py-1.5 text-sm text-[var(--trk-text)]";

// ─── Root page ───────────────────────────────────────────────────────────────

export default function BrokerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const brokerId = Number(id);
  const [ws, setWs] = useState<BrokerWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => fieldsFromBroker(null));
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!Number.isFinite(brokerId)) {
      setError("Invalid broker id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const next = await getBrokerWorkspace(brokerId, { include_archived: true });
      setWs(next);
      setForm(fieldsFromBroker(next.broker));
      setEditing(false);
      setSaveMsg(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [brokerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const broker = ws?.broker;

  const save = async () => {
    if (!broker) return;
    setSaving(true);
    setSaveMsg(null);
    try {
      const str = (v: string) => v.trim() || null;
      const nm = form.name.trim() || broker.name;
      const updated = await updateBroker(broker.id, {
        name: nm,
        display_name: str(form.name) ?? nm,
        legal_name: str(form.name) ?? nm,
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
      setWs((prev) => (prev ? { ...prev, broker: updated } : null));
      setForm(fieldsFromBroker(updated));
      setEditing(false);
      setSaveMsg("Saved.");
    } catch (e: unknown) {
      setSaveMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const cancelEdit = () => {
    if (broker) setForm(fieldsFromBroker(broker));
    setEditing(false);
    setSaveMsg(null);
  };

  if (!Number.isFinite(brokerId))
    return (
      <div className="p-8 text-rose-400">
        Invalid id.{" "}
        <Link to={OPS.BROKERS} className="text-[var(--trk-heading)]">
          Back
        </Link>
      </div>
    );

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 text-[var(--trk-text)]">
      <div className="mb-5">
        <Link to={OPS.BROKERS} className="text-sm text-[var(--trk-heading)] hover:underline">
          ← Freight brokers
        </Link>
      </div>

      {loading && <p className="text-[#64748b]">Loading…</p>}
      {error && <p className="text-rose-400">{error}</p>}

      {broker && ws && (
        <div className="space-y-5">
          <Header
            broker={broker}
            form={form}
            editing={editing}
            saving={saving}
            onFormChange={setForm}
            onEdit={() => {
              setForm(fieldsFromBroker(broker));
              setEditing(true);
              setSaveMsg(null);
            }}
            onCancel={cancelEdit}
            onSave={() => void save()}
            onArchive={async () => {
              await archiveBroker(brokerId);
              await load();
            }}
            onUnarchive={async () => {
              await unarchiveBroker(brokerId);
              await load();
            }}
          />

          {editing && saveMsg && saveMsg !== "Saved." && (
            <p className="text-sm text-rose-400">{saveMsg}</p>
          )}

          <FirmSections form={form} editing={editing} onFormChange={setForm} />

          {saveMsg && !editing && (
            <p className={`text-sm ${saveMsg === "Saved." ? "text-emerald-400" : "text-rose-400"}`}>{saveMsg}</p>
          )}

          <ContactsSection brokerId={brokerId} contacts={ws.contacts} onReload={load} />
          <EmailRulesSection brokerId={brokerId} ws={ws} onReload={load} />
        </div>
      )}
    </div>
  );
}

// ─── Header: title, MC/DOT/SCAC + status + Edit / Archive ───────────────────

function Header({
  broker,
  form,
  editing,
  saving,
  onFormChange,
  onEdit,
  onCancel,
  onSave,
  onArchive,
  onUnarchive,
}: {
  broker: Broker;
  form: ReturnType<typeof fieldsFromBroker>;
  editing: boolean;
  saving: boolean;
  onFormChange: React.Dispatch<React.SetStateAction<ReturnType<typeof fieldsFromBroker>>>;
  onEdit: () => void;
  onCancel: () => void;
  onSave: () => void;
  onArchive: () => Promise<void>;
  onUnarchive: () => Promise<void>;
}) {
  const label = (broker.display_name || broker.legal_name || broker.name).trim();
  const isActive = broker.is_active !== false;

  const setMeta =
    (key: "mc_number" | "dot_number" | "scac") => (e: React.ChangeEvent<HTMLInputElement>) =>
      onFormChange((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <div className="border-b border-[#1a2231] pb-5">
      <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[var(--trk-heading)]">{label}</h1>

      <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
          <span
            className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
              isActive ? "bg-[#052e16] text-[#86efac]" : "bg-[#422006] text-[#fdba74]"
            }`}
          >
            {isActive ? "Active" : `Archived${broker.archived_at ? " · " + broker.archived_at.slice(0, 10) : ""}`}
          </span>

          <MetaChip label="MC" editing={editing} value={form.mc_number} onChange={setMeta("mc_number")} />
          <MetaChip label="DOT" editing={editing} value={form.dot_number} onChange={setMeta("dot_number")} />
          <MetaChip label="SCAC" editing={editing} value={form.scac} onChange={setMeta("scac")} />
        </div>

        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {!editing && isActive && (
            <Button type="button" variant="secondary" onClick={onEdit}>
              Edit
            </Button>
          )}
          {editing && (
            <>
              <Button type="button" variant="primary" disabled={saving} onClick={onSave}>
                {saving ? "Saving…" : "Save"}
              </Button>
              <Button type="button" variant="secondary" disabled={saving} onClick={onCancel}>
                Cancel
              </Button>
            </>
          )}
          {isActive ? (
            <Button type="button" variant="secondary" onClick={() => void onArchive()}>
              Archive
            </Button>
          ) : (
            <Button type="button" variant="primary" onClick={() => void onUnarchive()}>
              Unarchive
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

function MetaChip({
  label,
  editing,
  value,
  onChange,
}: {
  label: string;
  editing: boolean;
  value: string;
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[var(--trk-text-muted)]">
      <span className="text-xs uppercase tracking-wide text-[#64748b]">{label}</span>
      {editing ? (
        <input
          className="w-28 rounded border border-[#334155] bg-[var(--trk-bg)] px-2 py-1 text-sm text-[var(--trk-text)] focus:border-[var(--trk-heading)] focus:outline-none"
          value={value}
          onChange={onChange}
          placeholder="—"
        />
      ) : (
        <span className="font-medium text-[var(--trk-text)]">{value?.trim() || "—"}</span>
      )}
    </span>
  );
}

// ─── Firm: Contact first, then Address, then Notes (no duplicate Identity) ───

function FirmSections({
  form,
  editing,
  onFormChange,
}: {
  form: ReturnType<typeof fieldsFromBroker>;
  editing: boolean;
  onFormChange: React.Dispatch<React.SetStateAction<ReturnType<typeof fieldsFromBroker>>>;
}) {
  const set =
    (key: keyof ReturnType<typeof fieldsFromBroker>) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      onFormChange((prev) => ({ ...prev, [key]: e.target.value }));

  return (
    <div className="space-y-5">
      {/* Contact (firm) — first */}
      <section className={SECTION}>
        <h2 className={SECTION_HEADING}>Contact</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {editing && (
            <div className="sm:col-span-2">
              <label className={LABEL}>Broker name</label>
              <input className={INPUT} value={form.name} onChange={set("name")} placeholder="Name as shown in lists" />
              <p className="mt-1 text-[11px] text-[#64748b]">Updates the display title and directory name. Legal/display names follow this value.</p>
            </div>
          )}
          <Field label="Phone primary" editing={editing} readValue={form.phone}>
            <input className={INPUT} value={form.phone} onChange={set("phone")} />
          </Field>
          <Field label="Phone secondary" editing={editing} readValue={form.phone_secondary}>
            <input className={INPUT} value={form.phone_secondary} onChange={set("phone_secondary")} />
          </Field>
          <Field label="Email primary" editing={editing} readValue={form.email}>
            <input className={INPUT} type="email" value={form.email} onChange={set("email")} />
          </Field>
          <Field label="Email secondary" editing={editing} readValue={form.email_secondary}>
            <input className={INPUT} type="email" value={form.email_secondary} onChange={set("email_secondary")} />
          </Field>
          <Field label="Website" editing={editing} readValue={form.website} className="sm:col-span-2">
            <input className={INPUT} value={form.website} onChange={set("website")} />
          </Field>
        </div>
      </section>

      <section className={SECTION}>
        <h2 className={SECTION_HEADING}>Address</h2>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Line 1" editing={editing} readValue={form.address_line1} className="sm:col-span-2">
            <input className={INPUT} value={form.address_line1} onChange={set("address_line1")} />
          </Field>
          <Field label="Line 2" editing={editing} readValue={form.address_line2}>
            <input className={INPUT} value={form.address_line2} onChange={set("address_line2")} />
          </Field>
          <Field label="City" editing={editing} readValue={form.address_city}>
            <input className={INPUT} value={form.address_city} onChange={set("address_city")} />
          </Field>
          <Field label="State / region" editing={editing} readValue={form.address_region}>
            <input className={INPUT} value={form.address_region} onChange={set("address_region")} />
          </Field>
          <Field label="Postal code" editing={editing} readValue={form.address_postal}>
            <input className={INPUT} value={form.address_postal} onChange={set("address_postal")} />
          </Field>
          <Field label="Country (ISO-2)" editing={editing} readValue={form.address_country}>
            <input className={INPUT} value={form.address_country} onChange={set("address_country")} maxLength={2} />
          </Field>
        </div>
      </section>

      <section className={SECTION}>
        <h2 className={SECTION_HEADING}>Notes</h2>
        <div className="space-y-3">
          <Field label="Classification notes" editing={editing} readValue={form.classification_notes}>
            <textarea className={TEXTAREA} value={form.classification_notes} onChange={set("classification_notes")} />
          </Field>
          <Field label="Internal notes" editing={editing} readValue={form.internal_notes}>
            <textarea className={TEXTAREA} value={form.internal_notes} onChange={set("internal_notes")} />
          </Field>
          <Field label="General notes" editing={editing} readValue={form.notes}>
            <textarea className={TEXTAREA} value={form.notes} onChange={set("notes")} />
          </Field>
        </div>
      </section>
    </div>
  );
}

function Field({
  label,
  editing,
  readValue,
  className = "",
  children,
}: {
  label: string;
  editing: boolean;
  readValue: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={className}>
      <label className={LABEL}>{label}</label>
      {editing ? (
        children
      ) : (
        <div className={READ_ONLY_VALUE}>{readValue?.trim() ? readValue : "—"}</div>
      )}
    </div>
  );
}

function fieldsFromBroker(b: Broker | null) {
  if (!b) {
    return {
      name: "",
      mc_number: "",
      dot_number: "",
      scac: "",
      phone: "",
      phone_secondary: "",
      email: "",
      email_secondary: "",
      website: "",
      address_line1: "",
      address_line2: "",
      address_city: "",
      address_region: "",
      address_postal: "",
      address_country: "",
      classification_notes: "",
      internal_notes: "",
      notes: "",
    };
  }
  return {
    name: b.name ?? "",
    mc_number: b.mc_number ?? "",
    dot_number: b.dot_number ?? "",
    scac: b.scac ?? "",
    phone: b.phone ?? "",
    phone_secondary: b.phone_secondary ?? "",
    email: b.email ?? "",
    email_secondary: b.email_secondary ?? "",
    website: b.website ?? "",
    address_line1: b.address_line1 ?? "",
    address_line2: b.address_line2 ?? "",
    address_city: b.address_city ?? "",
    address_region: b.address_region ?? "",
    address_postal: b.address_postal ?? "",
    address_country: b.address_country ?? "",
    classification_notes: b.classification_notes ?? "",
    internal_notes: b.internal_notes ?? "",
    notes: b.notes ?? "",
  };
}

// ─── Contacts (people) ──────────────────────────────────────────────────────

type ContactForm = {
  name: string;
  role: string;
  department: string;
  phone: string;
  extension: string;
  fax: string;
  email: string;
  is_primary: boolean;
};

const EMPTY_CONTACT: ContactForm = {
  name: "",
  role: "",
  department: "",
  phone: "",
  extension: "",
  fax: "",
  email: "",
  is_primary: false,
};

function ContactsSection({
  brokerId,
  contacts,
  onReload,
}: {
  brokerId: number;
  contacts: BrokerContact[];
  onReload: () => Promise<void>;
}) {
  const [form, setForm] = useState<ContactForm>(EMPTY_CONTACT);
  const [adding, setAdding] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const set = (key: keyof ContactForm) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: e.target.value }));

  const add = async () => {
    if (!form.name.trim()) {
      setMsg("Name is required");
      return;
    }
    setAdding(true);
    setMsg(null);
    try {
      const str = (v: string) => v.trim() || null;
      await createBrokerContact(brokerId, {
        name: form.name.trim(),
        role: str(form.role),
        department: str(form.department),
        phone: str(form.phone),
        extension: str(form.extension),
        fax: str(form.fax),
        email: str(form.email),
        is_primary: form.is_primary,
      });
      setForm(EMPTY_CONTACT);
      await onReload();
    } catch (e: unknown) {
      setMsg(e instanceof Error ? e.message : "Failed to add contact");
    } finally {
      setAdding(false);
    }
  };

  const active = contacts.filter((c) => c.is_active);

  return (
    <section className={SECTION}>
      <h2 className={SECTION_HEADING}>Contacts</h2>

      <div className="mb-5 overflow-x-auto rounded-lg border border-[#1a2231]">
        <table className="w-full text-sm">
          <thead className="border-b border-[#1a2231] bg-[#141924]">
            <tr className="text-xs uppercase tracking-wide text-[#64748b]">
              {["Name", "Role", "Department", "Phone", "Ext", "Fax", "Email", "Primary"].map((h) => (
                <th key={h} className="whitespace-nowrap px-3 py-2 text-left">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1a2231]">
            {active.map((c) => (
              <tr key={c.id} className="hover:bg-[#141924]/60">
                <td className="whitespace-nowrap px-3 py-2 font-medium text-[var(--trk-text)]">{c.name}</td>
                <td className="px-3 py-2 text-[var(--trk-text-muted)]">{c.role ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--trk-text-muted)]">{c.department ?? "—"}</td>
                <td className="whitespace-nowrap px-3 py-2 text-[var(--trk-text-muted)]">{c.phone ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--trk-text-muted)]">{c.extension ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--trk-text-muted)]">{c.fax ?? "—"}</td>
                <td className="px-3 py-2 text-[var(--trk-text-muted)]">{c.email ?? "—"}</td>
                <td className="px-3 py-2 text-center">
                  {c.is_primary && (
                    <span className="rounded bg-[#1e3a5f] px-1.5 py-0.5 text-[10px] text-[#93c5fd]">primary</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {active.length === 0 && <p className="p-4 text-center text-xs text-[#64748b]">No contacts yet.</p>}
      </div>

      <div className="border-t border-[#1a2231] pt-4">
        <p className={SUBSECTION_HEADING}>Add contact</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <label className={LABEL}>Name *</label>
            <input className={INPUT} value={form.name} onChange={set("name")} placeholder="Full name" />
          </div>
          <div>
            <label className={LABEL}>Role</label>
            <input className={INPUT} value={form.role} onChange={set("role")} placeholder="e.g. Dispatcher" />
          </div>
          <div>
            <label className={LABEL}>Department</label>
            <input className={INPUT} value={form.department} onChange={set("department")} />
          </div>
          <div>
            <label className={LABEL}>Phone</label>
            <input className={INPUT} value={form.phone} onChange={set("phone")} />
          </div>
          <div>
            <label className={LABEL}>Extension</label>
            <input className={INPUT} value={form.extension} onChange={set("extension")} />
          </div>
          <div>
            <label className={LABEL}>Fax</label>
            <input className={INPUT} value={form.fax} onChange={set("fax")} />
          </div>
          <div>
            <label className={LABEL}>Email</label>
            <input className={INPUT} type="email" value={form.email} onChange={set("email")} />
          </div>
        </div>
        <div className="mt-3 flex items-center gap-4">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--trk-text-muted)]">
            <input
              type="checkbox"
              checked={form.is_primary}
              onChange={(e) => setForm((prev) => ({ ...prev, is_primary: e.target.checked }))}
              className="rounded border-[#334155]"
            />
            Primary contact
          </label>
          <Button type="button" variant="secondary" disabled={adding} onClick={() => void add()}>
            {adding ? "Adding…" : "Add contact"}
          </Button>
          {msg && <span className="text-xs text-rose-400">{msg}</span>}
        </div>
      </div>
    </section>
  );
}

// ─── Email matching rules ────────────────────────────────────────────────────

function EmailRulesSection({
  brokerId,
  ws,
  onReload,
}: {
  brokerId: number;
  ws: BrokerWorkspace;
  onReload: () => Promise<void>;
}) {
  const [senderVal, setSenderVal] = useState("");
  const [domVal, setDomVal] = useState("");
  const [domPrimary, setDomPrimary] = useState(false);
  const [aliasVal, setAliasVal] = useState("");
  const [aliasType, setAliasType] = useState("display");

  const activeSenders = ws.known_senders.filter((s) => s.is_active);
  const activeDomains = ws.domains.filter((d) => d.is_active);
  const activeAliases = ws.aliases.filter((a) => a.is_active);

  return (
    <section className={SECTION}>
      <h2 className={SECTION_HEADING}>Email matching rules</h2>
      <p className="mb-5 text-xs text-[#64748b]">
        Precedence when an email arrives:{" "}
        <span className="text-[var(--trk-text-muted)]">known sender</span> (exact From address) → <span className="text-[var(--trk-text-muted)]">domain</span> →{" "}
        <span className="text-[var(--trk-text-muted)]">alias</span>
      </p>

      <div className="grid gap-5 sm:grid-cols-3">
        <div>
          <p className={SUBSECTION_HEADING}>Known senders</p>
          <div className="mb-3 flex gap-2">
            <input
              className={INPUT}
              value={senderVal}
              onChange={(e) => setSenderVal(e.target.value)}
              placeholder="ops@broker.com"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                if (!senderVal.trim()) return;
                await createBrokerKnownSender(brokerId, { email: senderVal.trim() });
                setSenderVal("");
                await onReload();
              }}
            >
              Add
            </Button>
          </div>
          <ul className="space-y-1.5">
            {activeSenders.map((s) => (
              <li key={s.id} className="truncate font-mono text-xs text-[#cbd5e1]">
                {s.email_normalized}
              </li>
            ))}
            {activeSenders.length === 0 && <li className="text-xs text-[#64748b]">None</li>}
          </ul>
        </div>

        <div>
          <p className={SUBSECTION_HEADING}>Domains</p>
          <div className="mb-2 flex gap-2">
            <input
              className={INPUT}
              value={domVal}
              onChange={(e) => setDomVal(e.target.value)}
              placeholder="broker.com"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                if (!domVal.trim()) return;
                await createBrokerDomain(brokerId, { domain: domVal.trim(), is_primary: domPrimary });
                setDomVal("");
                setDomPrimary(false);
                await onReload();
              }}
            >
              Add
            </Button>
          </div>
          <label className="mb-3 flex cursor-pointer items-center gap-1.5 text-xs text-[var(--trk-text-muted)]">
            <input type="checkbox" checked={domPrimary} onChange={(e) => setDomPrimary(e.target.checked)} className="rounded border-[#334155]" />
            Mark as primary
          </label>
          <ul className="space-y-1.5">
            {activeDomains.map((d) => (
              <li key={d.id} className="flex items-center gap-1.5 text-xs text-[#cbd5e1]">
                <span className="font-mono">{d.domain}</span>
                {d.is_primary && <span className="text-amber-300/80">primary</span>}
              </li>
            ))}
            {activeDomains.length === 0 && <li className="text-xs text-[#64748b]">None</li>}
          </ul>
        </div>

        <div>
          <p className={SUBSECTION_HEADING}>Aliases</p>
          <div className="mb-2 flex gap-2">
            <input
              className={INPUT}
              value={aliasVal}
              onChange={(e) => setAliasVal(e.target.value)}
              placeholder="Strict match string"
            />
            <Button
              type="button"
              variant="secondary"
              onClick={async () => {
                if (!aliasVal.trim()) return;
                await createBrokerAlias(brokerId, { alias: aliasVal.trim(), alias_type: aliasType });
                setAliasVal("");
                await onReload();
              }}
            >
              Add
            </Button>
          </div>
          <select className={`${INPUT} mb-3`} value={aliasType} onChange={(e) => setAliasType(e.target.value)}>
            <option value="display">display</option>
            <option value="legal">legal</option>
            <option value="dba">dba</option>
            <option value="other">other</option>
          </select>
          <ul className="space-y-1.5">
            {activeAliases.map((a) => (
              <li key={a.id} className="text-xs text-[#cbd5e1]">
                {a.alias} <span className="text-[#64748b]">({a.alias_type})</span>
              </li>
            ))}
            {activeAliases.length === 0 && <li className="text-xs text-[#64748b]">None</li>}
          </ul>
        </div>
      </div>
    </section>
  );
}
