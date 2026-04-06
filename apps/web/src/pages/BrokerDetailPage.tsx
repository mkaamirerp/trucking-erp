/**
 * Freight broker detail — workspace tabs: overview, communication, address, email intelligence, contacts.
 */
import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { clsx } from "clsx";
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
  type BrokerWorkspace,
} from "@/api";
import { OPS } from "@/routes";
import Button from "@/components/Button";

const INPUT =
  "w-full rounded border border-[#334155] bg-[#080a0f] px-2.5 py-1.5 text-sm text-[#e8edf5] focus:border-[#f5a623] focus:ring-0 focus:outline-none";
const LABEL = "block text-xs font-medium text-[#94a3b8] mb-1";

type TabId = "overview" | "communication" | "address" | "email" | "contacts";

const TABS: { id: TabId; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "communication", label: "Communication" },
  { id: "address", label: "Address" },
  { id: "email", label: "Email intelligence" },
  { id: "contacts", label: "Contacts" },
];

export default function BrokerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const brokerId = Number(id);
  const [ws, setWs] = useState<BrokerWorkspace | null>(null);
  const [tab, setTab] = useState<TabId>("overview");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingOverview, setSavingOverview] = useState(false);

  const [domVal, setDomVal] = useState("");
  const [domPrimary, setDomPrimary] = useState(false);
  const [aliasVal, setAliasVal] = useState("");
  const [aliasType, setAliasType] = useState("display");
  const [senderVal, setSenderVal] = useState("");
  const [cName, setCName] = useState("");
  const [cEmail, setCEmail] = useState("");

  const load = useCallback(async () => {
    if (!Number.isFinite(brokerId)) {
      setError("Invalid broker id");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await getBrokerWorkspace(brokerId, { include_archived: true });
      setWs(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load");
      setWs(null);
    } finally {
      setLoading(false);
    }
  }, [brokerId]);

  useEffect(() => {
    void load();
  }, [load]);

  const broker = ws?.broker;

  const saveOverview = async (b: Broker, form: Partial<Broker>) => {
    setSavingOverview(true);
    setError(null);
    try {
      const updated = await updateBroker(b.id, form);
      setWs((prev) => (prev ? { ...prev, broker: updated } : null));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSavingOverview(false);
    }
  };

  if (!Number.isFinite(brokerId)) {
    return (
      <div className="p-8 text-rose-400">
        Invalid id.{" "}
        <Link to={OPS.BROKERS} className="text-[#f5a623]">
          Back
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 text-[#e8edf5]">
      <div className="mb-6">
        <Link to={OPS.BROKERS} className="text-sm text-[#f5a623] hover:underline">
          ← Freight brokers
        </Link>
      </div>

      {loading && <p className="text-[#64748b]">Loading…</p>}
      {error && <p className="text-rose-400">{error}</p>}

      {broker && ws && (
        <>
          <div className="mb-6 flex flex-col gap-4 border-b border-[#1a2231] pb-6 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <h1 className="font-['Barlow_Condensed'] text-3xl font-bold tracking-tight text-[#f5a623]">
                {(broker.display_name || broker.legal_name || broker.name).trim()}
              </h1>
              <p className="mt-1 text-sm text-[#94a3b8]">
                MC {broker.mc_number ?? "—"} · DOT {broker.dot_number ?? "—"} · SCAC {broker.scac ?? "—"} · ID{" "}
                {broker.id}
              </p>
              <p className="mt-2 text-xs text-[#64748b]">
                {broker.is_active === false ? (
                  <span className="text-[#fdba74]">Archived {broker.archived_at ? `· ${broker.archived_at}` : ""}</span>
                ) : (
                  <span className="text-[#86efac]">Active</span>
                )}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {broker.is_active !== false ? (
                <Button
                  type="button"
                  variant="secondary"
                  onClick={async () => {
                    await archiveBroker(brokerId);
                    await load();
                  }}
                >
                  Archive broker
                </Button>
              ) : (
                <Button
                  type="button"
                  variant="primary"
                  onClick={async () => {
                    await unarchiveBroker(brokerId);
                    await load();
                  }}
                >
                  Unarchive broker
                </Button>
              )}
            </div>
          </div>

          <div className="mb-6 flex flex-wrap gap-1 border-b border-[#1a2231]">
            {TABS.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setTab(t.id)}
                className={clsx(
                  "rounded-t-md px-3 py-2 text-xs font-medium transition",
                  tab === t.id
                    ? "bg-[#1a2231] text-[#f5a623]"
                    : "text-[#94a3b8] hover:text-[#e8edf5]"
                )}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "overview" && (
            <OverviewTab broker={broker} saving={savingOverview} onSave={saveOverview} />
          )}
          {tab === "communication" && (
            <CommunicationTab broker={broker} saving={savingOverview} onSave={saveOverview} />
          )}
          {tab === "address" && <AddressTab broker={broker} saving={savingOverview} onSave={saveOverview} />}
          {tab === "email" && (
            <EmailIntelTab
              brokerId={brokerId}
              ws={ws}
              domVal={domVal}
              setDomVal={setDomVal}
              domPrimary={domPrimary}
              setDomPrimary={setDomPrimary}
              aliasVal={aliasVal}
              setAliasVal={setAliasVal}
              aliasType={aliasType}
              setAliasType={setAliasType}
              senderVal={senderVal}
              setSenderVal={setSenderVal}
              onReload={load}
            />
          )}
          {tab === "contacts" && (
            <ContactsTab
              brokerId={brokerId}
              contacts={ws.contacts}
              cName={cName}
              setCName={setCName}
              cEmail={cEmail}
              setCEmail={setCEmail}
              onReload={load}
            />
          )}
        </>
      )}
    </div>
  );
}

function OverviewTab({
  broker,
  saving,
  onSave,
}: {
  broker: Broker;
  saving: boolean;
  onSave: (b: Broker, form: Partial<Broker>) => Promise<void>;
}) {
  const [legal, setLegal] = useState(broker.legal_name ?? "");
  const [display, setDisplay] = useState(broker.display_name ?? "");
  const [mc, setMc] = useState(broker.mc_number ?? "");
  const [dot, setDot] = useState(broker.dot_number ?? "");
  const [scac, setScac] = useState(broker.scac ?? "");
  const [classification, setClassification] = useState(broker.classification_notes ?? "");
  const [internal, setInternal] = useState(broker.internal_notes ?? "");

  useEffect(() => {
    setLegal(broker.legal_name ?? "");
    setDisplay(broker.display_name ?? "");
    setMc(broker.mc_number ?? "");
    setDot(broker.dot_number ?? "");
    setScac(broker.scac ?? "");
    setClassification(broker.classification_notes ?? "");
    setInternal(broker.internal_notes ?? "");
  }, [broker]);

  return (
    <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 space-y-4">
      <h2 className="text-sm font-semibold text-[#e8edf5]">Firm identity</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label className={LABEL}>Legal name</label>
          <input className={INPUT} value={legal} onChange={(e) => setLegal(e.target.value)} />
        </div>
        <div className="sm:col-span-2">
          <label className={LABEL}>Display name</label>
          <input className={INPUT} value={display} onChange={(e) => setDisplay(e.target.value)} />
        </div>
        <div>
          <label className={LABEL}>MC number</label>
          <input className={INPUT} value={mc} onChange={(e) => setMc(e.target.value)} />
        </div>
        <div>
          <label className={LABEL}>DOT / USDOT</label>
          <input className={INPUT} value={dot} onChange={(e) => setDot(e.target.value)} />
        </div>
        <div>
          <label className={LABEL}>SCAC</label>
          <input className={INPUT} value={scac} onChange={(e) => setScac(e.target.value)} />
        </div>
      </div>
      <div>
        <label className={LABEL}>Classification notes (how you tag this broker operationally)</label>
        <textarea
          className={clsx(INPUT, "min-h-[72px]")}
          value={classification}
          onChange={(e) => setClassification(e.target.value)}
        />
      </div>
      <div>
        <label className={LABEL}>Internal notes (not shown on documents)</label>
        <textarea className={clsx(INPUT, "min-h-[72px]")} value={internal} onChange={(e) => setInternal(e.target.value)} />
      </div>
      <Button
        type="button"
        variant="primary"
        disabled={saving}
        onClick={() =>
          onSave(broker, {
            legal_name: legal.trim() || null,
            display_name: display.trim() || null,
            mc_number: mc.trim() || null,
            dot_number: dot.trim() || null,
            scac: scac.trim() || null,
            classification_notes: classification.trim() || null,
            internal_notes: internal.trim() || null,
          })
        }
      >
        {saving ? "Saving…" : "Save overview"}
      </Button>
    </section>
  );
}

function CommunicationTab({
  broker,
  saving,
  onSave,
}: {
  broker: Broker;
  saving: boolean;
  onSave: (b: Broker, form: Partial<Broker>) => Promise<void>;
}) {
  const [web, setWeb] = useState(broker.website ?? "");
  useEffect(() => {
    setWeb(broker.website ?? "");
  }, [broker]);

  return (
    <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 space-y-4">
      <h2 className="text-sm font-semibold text-[#e8edf5]">Phones & email</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Phone primary</label>
          <input
            className={INPUT}
            value={broker.phone ?? ""}
            onChange={(e) => onSave(broker, { phone: e.target.value || null })}
          />
        </div>
        <div>
          <label className={LABEL}>Phone secondary</label>
          <input
            className={INPUT}
            value={broker.phone_secondary ?? ""}
            onChange={(e) => onSave(broker, { phone_secondary: e.target.value || null })}
          />
        </div>
        <div>
          <label className={LABEL}>Email primary</label>
          <input
            className={INPUT}
            type="email"
            value={broker.email ?? ""}
            onChange={(e) => onSave(broker, { email: e.target.value || null })}
          />
        </div>
        <div>
          <label className={LABEL}>Email secondary</label>
          <input
            className={INPUT}
            type="email"
            value={broker.email_secondary ?? ""}
            onChange={(e) => onSave(broker, { email_secondary: e.target.value || null })}
          />
        </div>
      </div>
      <div>
        <label className={LABEL}>Website</label>
        <input className={INPUT} value={web} onChange={(e) => setWeb(e.target.value)} />
      </div>
      <Button
        type="button"
        variant="primary"
        disabled={saving}
        onClick={() => onSave(broker, { website: web.trim() || null })}
      >
        {saving ? "Saving…" : "Save communication"}
      </Button>
    </section>
  );
}

function AddressTab({
  broker,
  saving,
  onSave,
}: {
  broker: Broker;
  saving: boolean;
  onSave: (b: Broker, form: Partial<Broker>) => Promise<void>;
}) {
  return (
    <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5 space-y-4">
      <h2 className="text-sm font-semibold text-[#e8edf5]">Mailing / HQ</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {(
          [
            ["address_line1", "Line 1"],
            ["address_line2", "Line 2"],
            ["address_city", "City"],
            ["address_region", "State / region"],
            ["address_postal", "Postal"],
            ["address_country", "Country (ISO-2)"],
          ] as const
        ).map(([key, lab]) => (
          <div
            key={key}
            className={key === "address_line1" || key === "address_line2" ? "sm:col-span-2" : ""}
          >
            <label className={LABEL}>{lab}</label>
            <input
              className={INPUT}
              value={String(broker[key as keyof Broker] ?? "")}
              onChange={(e) => onSave(broker, { [key]: e.target.value || null } as Partial<Broker>)}
            />
          </div>
        ))}
      </div>
      <p className="text-xs text-[#64748b]">This is booking-broker master data only — not customs broker.</p>
      <Button type="button" variant="secondary" disabled={saving}>
        Changes save as you edit
      </Button>
    </section>
  );
}

function EmailIntelTab({
  brokerId,
  ws,
  domVal,
  setDomVal,
  domPrimary,
  setDomPrimary,
  aliasVal,
  setAliasVal,
  aliasType,
  setAliasType,
  senderVal,
  setSenderVal,
  onReload,
}: {
  brokerId: number;
  ws: BrokerWorkspace;
  domVal: string;
  setDomVal: (v: string) => void;
  domPrimary: boolean;
  setDomPrimary: (v: boolean) => void;
  aliasVal: string;
  setAliasVal: (v: string) => void;
  aliasType: string;
  setAliasType: (v: string) => void;
  senderVal: string;
  setSenderVal: (v: string) => void;
  onReload: () => Promise<void>;
}) {
  return (
    <div className="space-y-6">
      <p className="text-xs text-[#64748b]">
        Intake precedence: <strong className="text-[#94a3b8]">known sender</strong> (exact email) →{" "}
        <strong className="text-[#94a3b8]">domain</strong> → <strong className="text-[#94a3b8]">alias</strong> (strict
        match).
      </p>
      <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5">
        <h2 className="mb-3 text-sm font-semibold">Known senders</h2>
        <div className="mb-3 flex flex-wrap gap-2">
          <input
            className={clsx(INPUT, "max-w-md")}
            value={senderVal}
            onChange={(e) => setSenderVal(e.target.value)}
            placeholder="exact From email e.g. ops@broker.com"
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
        <ul className="space-y-1 text-sm">
          {ws.known_senders.map((s) => (
            <li key={s.id} className="flex justify-between gap-2 font-mono text-xs text-[#cbd5e1]">
              <span>{s.email_normalized}</span>
              <span className={s.is_active ? "text-emerald-400" : "text-amber-400"}>
                {s.is_active ? "active" : "inactive"}
              </span>
            </li>
          ))}
          {ws.known_senders.length === 0 && <li className="text-[#64748b]">None</li>}
        </ul>
      </section>
      <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5">
        <h2 className="mb-3 text-sm font-semibold">Domains</h2>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input className={clsx(INPUT, "max-w-md")} value={domVal} onChange={(e) => setDomVal(e.target.value)} placeholder="broker.example.com" />
          <label className="flex items-center gap-1.5 text-xs text-[#94a3b8]">
            <input type="checkbox" checked={domPrimary} onChange={(e) => setDomPrimary(e.target.checked)} />
            Primary
          </label>
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
            Add domain
          </Button>
        </div>
        <ul className="space-y-1 text-sm">
          {ws.domains.map((d) => (
            <li key={d.id} className="flex justify-between gap-2 text-[#cbd5e1]">
              <span>
                {d.domain}
                {d.is_primary ? <span className="ml-2 text-[10px] text-amber-300/90">primary</span> : null}
              </span>
              <span className={d.is_active ? "text-emerald-400" : "text-amber-400"}>{d.is_active ? "active" : "inactive"}</span>
            </li>
          ))}
          {ws.domains.length === 0 && <li className="text-[#64748b]">None</li>}
        </ul>
      </section>
      <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5">
        <h2 className="mb-3 text-sm font-semibold">Aliases</h2>
        <div className="mb-3 flex flex-wrap gap-2">
          <input className={clsx(INPUT, "max-w-sm")} value={aliasVal} onChange={(e) => setAliasVal(e.target.value)} placeholder="Strict match string" />
          <select
            className={clsx(INPUT, "max-w-[140px]")}
            value={aliasType}
            onChange={(e) => setAliasType(e.target.value)}
          >
            <option value="display">display</option>
            <option value="legal">legal</option>
            <option value="dba">dba</option>
            <option value="other">other</option>
          </select>
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
            Add alias
          </Button>
        </div>
        <ul className="space-y-1 text-sm">
          {ws.aliases.map((a) => (
            <li key={a.id} className="flex justify-between gap-2 text-[#cbd5e1]">
              <span>
                {a.alias} <span className="text-[#64748b]">({a.alias_type})</span>
              </span>
              <span className={a.is_active ? "text-emerald-400" : "text-amber-400"}>{a.is_active ? "active" : "inactive"}</span>
            </li>
          ))}
          {ws.aliases.length === 0 && <li className="text-[#64748b]">None</li>}
        </ul>
      </section>
    </div>
  );
}

function ContactsTab({
  brokerId,
  contacts,
  cName,
  setCName,
  cEmail,
  setCEmail,
  onReload,
}: {
  brokerId: number;
  contacts: BrokerWorkspace["contacts"];
  cName: string;
  setCName: (v: string) => void;
  cEmail: string;
  setCEmail: (v: string) => void;
  onReload: () => Promise<void>;
}) {
  return (
    <section className="rounded-2xl border border-[#1a2231] bg-[#0d111a] p-5">
      <h2 className="mb-3 text-sm font-semibold">Contacts</h2>
      <div className="mb-4 grid gap-2 sm:grid-cols-2">
        <div>
          <label className={LABEL}>Name</label>
          <input className={INPUT} value={cName} onChange={(e) => setCName(e.target.value)} />
        </div>
        <div>
          <label className={LABEL}>Email</label>
          <input className={INPUT} value={cEmail} onChange={(e) => setCEmail(e.target.value)} placeholder="Optional" />
        </div>
      </div>
      <Button
        type="button"
        variant="secondary"
        className="mb-4"
        onClick={async () => {
          if (!cName.trim()) return;
          await createBrokerContact(brokerId, { name: cName.trim(), email: cEmail.trim() || null });
          setCName("");
          setCEmail("");
          await onReload();
        }}
      >
        Add contact
      </Button>
      <ul className="space-y-2 text-sm">
        {contacts.map((c) => (
          <li
            key={c.id}
            className="flex flex-wrap justify-between gap-2 border-t border-[#1a2231] pt-2 text-[#cbd5e1] first:border-t-0 first:pt-0"
          >
            <span>
              {c.name}
              {c.is_primary ? <span className="ml-2 text-[10px] text-amber-300/90">primary</span> : null}
            </span>
            <span className="text-[#94a3b8]">{c.email ?? "—"}</span>
            <span className={c.is_active ? "text-emerald-400" : "text-amber-400"}>{c.is_active ? "active" : "inactive"}</span>
          </li>
        ))}
        {contacts.length === 0 && <li className="text-[#64748b]">None</li>}
      </ul>
    </section>
  );
}
