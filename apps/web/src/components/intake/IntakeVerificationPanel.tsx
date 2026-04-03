/**
 * Right-column verification layout for Load Intake (email → draft load).
 * Primary fields stay visible; stops/addresses then notes; secondary fields in accordion.
 */
import { type ChangeEvent, useEffect, useMemo, useRef, useState } from "react";
import type { InboxMessageAttachmentItem, InboxMessageItem } from "@/api";
import type { Load } from "@/api";
import { sortedStops } from "@/utils/loadStops";

export type IntakeKpis = {
  pendingReview: number;
  createdToday: number;
  awaitingCarrier: number;
  dispatchedWeek: number;
};

function findFirstPdf(messages: InboxMessageItem[]): { att: InboxMessageAttachmentItem; message: InboxMessageItem } | null {
  for (const m of messages) {
    for (const a of m.attachments ?? []) {
      if (a.mime_type?.includes("pdf") || (a.filename ?? "").toLowerCase().endsWith(".pdf")) {
        return { att: a, message: m };
      }
    }
  }
  return null;
}

function participantEmails(participants_json: unknown): string[] {
  if (!Array.isArray(participants_json)) return [];
  return participants_json
    .map((v) => (v && typeof v === "object" && "email" in v ? String((v as { email?: unknown }).email ?? "") : ""))
    .filter(Boolean);
}

function formatBytes(n: number | null | undefined): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fieldClass() {
  return "w-full rounded-lg border border-[#334155] bg-[#0d111a] px-3 py-2 text-sm text-[#e8edf5] placeholder:text-[#64748b] focus:border-[#f5a623] focus:outline-none focus:ring-1 focus:ring-[#f5a623]/40";
}

function labelClass() {
  return "block text-xs font-medium uppercase tracking-wide text-[#94a3b8]";
}

type Props = {
  threadSubject: string | null;
  participantsJson: unknown;
  routingReason: string | null;
  messages: InboxMessageItem[];
  /** When set, participant email prefill does not override broker email from the load. */
  linkedLoad: Load | null;
  kpis: IntakeKpis;
  canReparse: boolean;
  recomputingIntake: boolean;
  onReparse: () => void;
  canVerifyCreate: boolean;
  draftCreating: boolean;
  onVerifyCreate: () => void;
  onManualEntry: () => void;
  /** True while POST /upload-pdf is in flight. */
  uploadBusy?: boolean;
  onUploadDocumentChange: (e: ChangeEvent<HTMLInputElement>) => void;
};

export function IntakeVerificationPanel({
  threadSubject,
  participantsJson,
  routingReason,
  messages,
  linkedLoad,
  kpis,
  canReparse,
  recomputingIntake,
  onReparse,
  canVerifyCreate,
  draftCreating,
  onVerifyCreate,
  onManualEntry,
  uploadBusy = false,
  onUploadDocumentChange,
}: Props) {
  const uploadRef = useRef<HTMLInputElement>(null);
  const pdf = useMemo(() => findFirstPdf(messages), [messages]);
  const ocrComplete = Boolean(pdf);

  const emails = useMemo(() => participantEmails(participantsJson), [participantsJson]);
  const [contactName, setContactName] = useState("");
  const [contactPhone, setContactPhone] = useState("");
  const [contactEmail, setContactEmail] = useState("");
  const [contactFax, setContactFax] = useState("");

  const [mode, setMode] = useState("");
  const [trailerType, setTrailerType] = useState("");
  const [trailerSize, setTrailerSize] = useState("");
  const [temperature, setTemperature] = useState("");
  const [palletCase, setPalletCase] = useState("");
  const [hazmat, setHazmat] = useState("");
  const [estWeight, setEstWeight] = useState("");
  const [loadRequirements, setLoadRequirements] = useState("");

  const [stopPickupFacility, setStopPickupFacility] = useState("");
  const [stopPickupStreet, setStopPickupStreet] = useState("");
  const [stopPickupCity, setStopPickupCity] = useState("");
  const [stopPickupSt, setStopPickupSt] = useState("");
  const [stopPickupPostal, setStopPickupPostal] = useState("");

  const [stopDropFacility, setStopDropFacility] = useState("");
  const [stopDropStreet, setStopDropStreet] = useState("");
  const [stopDropCity, setStopDropCity] = useState("");
  const [stopDropSt, setStopDropSt] = useState("");
  const [stopDropPostal, setStopDropPostal] = useState("");

  const [notes, setNotes] = useState("");
  const [moreOpen, setMoreOpen] = useState(false);
  const [extraRefs, setExtraRefs] = useState("");
  const [secondaryContact, setSecondaryContact] = useState("");
  const [specialHandling, setSpecialHandling] = useState("");
  const [internalComments, setInternalComments] = useState("");

  useEffect(() => {
    if (linkedLoad) return;
    const first = emails[0] ?? "";
    setContactEmail((prev) => (prev && first && prev !== first ? prev : first));
  }, [emails, linkedLoad]);

  useEffect(() => {
    const l = linkedLoad;
    if (!l) {
      setContactName("");
      setContactPhone("");
      setContactEmail("");
      setContactFax("");
      setMode("");
      setTrailerType("");
      setTrailerSize("");
      setTemperature("");
      setPalletCase("");
      setHazmat("");
      setEstWeight("");
      setLoadRequirements("");
      setStopPickupFacility("");
      setStopPickupStreet("");
      setStopPickupCity("");
      setStopPickupSt("");
      setStopPickupPostal("");
      setStopDropFacility("");
      setStopDropStreet("");
      setStopDropCity("");
      setStopDropSt("");
      setStopDropPostal("");
      setNotes("");
      setInternalComments("");
      return;
    }
    setContactName(l.broker_contact_name_snapshot ?? l.broker_contact?.name ?? "");
    const ext = l.broker_contact?.extension;
    const ph = l.broker_contact_phone_snapshot ?? l.broker_contact?.phone ?? "";
    setContactPhone(ext ? `${ph} x${ext}` : ph);
    setContactEmail(l.broker_contact_email_snapshot ?? l.broker_contact?.email ?? "");
    setContactFax("");

    setMode(l.mode ?? "");
    setTrailerType(l.trailer_type ?? "");
    setTrailerSize(l.trailer_size ?? "");
    setTemperature(l.temperature_requirement ?? "");
    setPalletCase(l.pallet_case_count ?? "");
    setHazmat(l.hazmat_flag === true ? "hazardous" : l.hazmat_flag === false ? "non-hazardous" : "");
    setEstWeight(l.estimated_weight != null ? String(l.estimated_weight) : "");
    setLoadRequirements(l.commodity ?? "");
    setInternalComments(l.internal_notes?.slice(0, 500) ?? "");

    const stops = sortedStops(l.stops ?? []);
    const pu = stops.find((s) => (s.stop_type || "").toUpperCase() === "PICKUP");
    const dr =
      [...stops].reverse().find((s) => {
        const t = (s.stop_type || "").toUpperCase();
        return t === "DROP" || t === "DELIVERY";
      }) ?? null;

    if (pu) {
      setStopPickupFacility(pu.facility_name ?? "");
      setStopPickupStreet(pu.street ?? "");
      setStopPickupCity(pu.city ?? "");
      setStopPickupSt(pu.state_or_province ?? "");
      setStopPickupPostal(pu.postal_code ?? "");
    } else {
      setStopPickupFacility("");
      setStopPickupStreet("");
      setStopPickupCity("");
      setStopPickupSt("");
      setStopPickupPostal("");
    }
    if (dr) {
      setStopDropFacility(dr.facility_name ?? "");
      setStopDropStreet(dr.street ?? "");
      setStopDropCity(dr.city ?? "");
      setStopDropSt(dr.state_or_province ?? "");
      setStopDropPostal(dr.postal_code ?? "");
    } else {
      setStopDropFacility("");
      setStopDropStreet("");
      setStopDropCity("");
      setStopDropSt("");
      setStopDropPostal("");
    }
    setNotes("");
  }, [linkedLoad]);

  const tagLine = (threadSubject || "").toLowerCase().includes("tql") ? "TQL" : null;

  return (
    <div className="flex flex-col gap-4 text-[#e8edf5]">
      {/* Top action row — OCR / re-parse live here, not in file strip */}
      <div className="flex flex-wrap items-center justify-end gap-2 border-b border-[#1e293b] pb-4">
        <button
          type="button"
          onClick={onManualEntry}
          className="rounded-lg border border-[#475569] bg-transparent px-3 py-2 text-sm font-medium text-[#e8edf5] hover:bg-[#1e293b]"
        >
          Manual entry
        </button>
        <button
          type="button"
          onClick={() => uploadRef.current?.click()}
          disabled={uploadBusy}
          className="rounded-lg border border-[#2563eb] bg-[#1d4ed8]/20 px-3 py-2 text-sm font-medium text-[#93c5fd] hover:bg-[#1d4ed8]/35 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {uploadBusy ? "Uploading…" : "Upload document"}
        </button>
        <input ref={uploadRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={onUploadDocumentChange} />
        <span
          className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm ${
            ocrComplete ? "border-emerald-900/60 bg-emerald-950/30 text-emerald-300" : "border-[#334155] bg-[#0d111a] text-[#64748b]"
          }`}
          title="Based on PDF attachment presence on this thread; server-side OCR status is not exposed yet"
        >
          {ocrComplete ? "✓ OCR complete" : "No PDF on thread"}
        </span>
        <button
          type="button"
          onClick={onReparse}
          disabled={!canReparse || recomputingIntake}
          className="rounded-lg border border-[#475569] bg-[#0f1420] px-3 py-2 text-sm font-medium text-[#94a3b8] hover:bg-[#1e293b] disabled:cursor-not-allowed disabled:opacity-40"
          title={!canReparse ? "Re-parse uses Gmail intake rules on this thread" : "Re-run PDF / intake classification"}
        >
          {recomputingIntake ? "Re-parsing…" : "Re-parse"}
        </button>
        <button
          type="button"
          onClick={onVerifyCreate}
          disabled={!canVerifyCreate || draftCreating}
          className="rounded-lg border border-emerald-800/60 bg-emerald-900/30 px-3 py-2 text-sm font-semibold text-emerald-200 hover:bg-emerald-900/45 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {draftCreating ? "Creating…" : "Verify & create load"}
        </button>
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Pending review", value: kpis.pendingReview, accent: "text-emerald-300" },
          { label: "Created today", value: kpis.createdToday, accent: "text-sky-300" },
          { label: "Awaiting carrier", value: kpis.awaitingCarrier, accent: "text-amber-300" },
          { label: "Dispatched this week", value: kpis.dispatchedWeek, accent: "text-violet-300" },
        ].map((k) => (
          <div key={k.label} className="rounded-xl border border-[#1e293b] bg-[#0d111a] px-3 py-3">
            <div className={`text-2xl font-semibold tabular-nums ${k.accent}`}>{k.value}</div>
            <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-[#64748b]">{k.label}</div>
          </div>
        ))}
      </div>

      {/* File strip — metadata only; OCR actions moved up */}
      <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] px-4 py-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-[#94a3b8]">Document</p>
        {pdf ? (
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium text-[#e8edf5]">{pdf.att.filename || "attachment.pdf"}</span>
            <span className="text-xs text-[#64748b]">{formatBytes(pdf.att.size_bytes)}</span>
            <span className="rounded-full border border-[#334155] bg-[#0a0e14] px-2 py-0.5 text-[11px] text-[#94a3b8]">Parsed (preview)</span>
          </div>
        ) : (
          <p className="mt-2 text-sm text-[#64748b]">No PDF attachment on this thread yet.</p>
        )}
        {(tagLine || pdf) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {tagLine && (
              <span className="rounded-full bg-[#1d4ed8]/25 px-2 py-0.5 text-[11px] text-[#93c5fd]">{tagLine}</span>
            )}
            {pdf && (
              <>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-[#94a3b8]">FTL</span>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-[#94a3b8]">Van 53ft</span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Doc order: contact → load info */}
      <section className="space-y-3 rounded-xl border-l-4 border-[#f5a623]/70 pl-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[#cbd5e1]">Broker / contact (verify)</h3>
        <p className="text-xs text-[#64748b]">Align with rate confirmation; not auto-saved until load APIs support intake PATCH.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <label className={labelClass()}>Name</label>
            <input className={`${fieldClass()} mt-1`} value={contactName} onChange={(e) => setContactName(e.target.value)} placeholder="—" />
          </div>
          <div>
            <label className={labelClass()}>Phone</label>
            <input className={`${fieldClass()} mt-1`} value={contactPhone} onChange={(e) => setContactPhone(e.target.value)} placeholder="—" />
          </div>
          <div>
            <label className={labelClass()}>Email</label>
            <input className={`${fieldClass()} mt-1`} value={contactEmail} onChange={(e) => setContactEmail(e.target.value)} placeholder="—" />
          </div>
          <div>
            <label className={labelClass()}>Fax</label>
            <input className={`${fieldClass()} mt-1`} value={contactFax} onChange={(e) => setContactFax(e.target.value)} placeholder="—" />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-xl border-l-4 border-emerald-700/50 pl-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[#cbd5e1]">Load information</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <div>
            <label className={labelClass()}>Mode</label>
            <select className={`${fieldClass()} mt-1`} value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="">—</option>
              <option value="FTL">FTL</option>
              <option value="LTL">LTL</option>
              <option value="PTL">PTL</option>
            </select>
          </div>
          <div>
            <label className={labelClass()}>Trailer type</label>
            <input className={`${fieldClass()} mt-1`} value={trailerType} onChange={(e) => setTrailerType(e.target.value)} placeholder="Dry van, reefer…" />
          </div>
          <div>
            <label className={labelClass()}>Trailer size</label>
            <input className={`${fieldClass()} mt-1`} value={trailerSize} onChange={(e) => setTrailerSize(e.target.value)} placeholder="53 ft" />
          </div>
          <div>
            <label className={labelClass()}>Temperature</label>
            <input className={`${fieldClass()} mt-1`} value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="—" />
          </div>
          <div>
            <label className={labelClass()}>Pallet / case count</label>
            <input className={`${fieldClass()} mt-1`} value={palletCase} onChange={(e) => setPalletCase(e.target.value)} placeholder="0 pallets / 48 cases" />
          </div>
          <div>
            <label className={labelClass()}>Hazmat</label>
            <select className={`${fieldClass()} mt-1`} value={hazmat} onChange={(e) => setHazmat(e.target.value)}>
              <option value="">—</option>
              <option value="non-hazardous">Non-hazardous</option>
              <option value="hazardous">Hazardous</option>
            </select>
          </div>
          <div>
            <label className={labelClass()}>Est. weight (lb)</label>
            <input className={`${fieldClass()} mt-1`} value={estWeight} onChange={(e) => setEstWeight(e.target.value)} placeholder="—" />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass()}>Load requirements</label>
            <input className={`${fieldClass()} mt-1`} value={loadRequirements} onChange={(e) => setLoadRequirements(e.target.value)} placeholder="Team, tarps, etc." />
          </div>
        </div>
      </section>

      {/* Stops: pickup / drop main + address */}
      <section className="space-y-4">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-[#cbd5e1]">Stops & addresses</h3>
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] p-4">
            <p className="mb-3 text-xs font-semibold text-[#f5a623]">Pickup</p>
            <div className="space-y-2">
              <input className={fieldClass()} value={stopPickupFacility} onChange={(e) => setStopPickupFacility(e.target.value)} placeholder="Facility" />
              <input className={fieldClass()} value={stopPickupStreet} onChange={(e) => setStopPickupStreet(e.target.value)} placeholder="Street" />
              <div className="grid grid-cols-2 gap-2">
                <input className={fieldClass()} value={stopPickupCity} onChange={(e) => setStopPickupCity(e.target.value)} placeholder="City" />
                <input className={fieldClass()} value={stopPickupSt} onChange={(e) => setStopPickupSt(e.target.value)} placeholder="ST" />
              </div>
              <input className={fieldClass()} value={stopPickupPostal} onChange={(e) => setStopPickupPostal(e.target.value)} placeholder="Postal" />
            </div>
          </div>
          <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] p-4">
            <p className="mb-3 text-xs font-semibold text-[#f5a623]">Delivery</p>
            <div className="space-y-2">
              <input className={fieldClass()} value={stopDropFacility} onChange={(e) => setStopDropFacility(e.target.value)} placeholder="Facility" />
              <input className={fieldClass()} value={stopDropStreet} onChange={(e) => setStopDropStreet(e.target.value)} placeholder="Street" />
              <div className="grid grid-cols-2 gap-2">
                <input className={fieldClass()} value={stopDropCity} onChange={(e) => setStopDropCity(e.target.value)} placeholder="City" />
                <input className={fieldClass()} value={stopDropSt} onChange={(e) => setStopDropSt(e.target.value)} placeholder="ST" />
              </div>
              <input className={fieldClass()} value={stopDropPostal} onChange={(e) => setStopDropPostal(e.target.value)} placeholder="Postal" />
            </div>
          </div>
        </div>
      </section>

      {/* Notes after address per spec */}
      <section>
        <label className={labelClass()}>Notes</label>
        <textarea
          className={`${fieldClass()} mt-1 min-h-[100px] resize-y`}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Operational notes after you verify pickup/drop…"
        />
        {routingReason && <p className="mt-2 text-xs text-[#64748b]">Routing: {routingReason}</p>}
      </section>

      {/* Expandable secondary fields */}
      <div className="rounded-xl border border-[#1e293b] bg-[#0a0e14]">
        <button
          type="button"
          onClick={() => setMoreOpen((o) => !o)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-semibold text-[#cbd5e1] hover:bg-[#0d111a]"
        >
          More fields
          <span className="text-[#64748b]">{moreOpen ? "▲" : "▼"}</span>
        </button>
        {moreOpen && (
          <div className="space-y-3 border-t border-[#1e293b] px-4 py-4">
            <div>
              <label className={labelClass()}>Extra references / PO</label>
              <input className={`${fieldClass()} mt-1`} value={extraRefs} onChange={(e) => setExtraRefs(e.target.value)} placeholder="Customer ref, BOL, etc." />
            </div>
            <div>
              <label className={labelClass()}>Secondary contact</label>
              <input className={`${fieldClass()} mt-1`} value={secondaryContact} onChange={(e) => setSecondaryContact(e.target.value)} />
            </div>
            <div>
              <label className={labelClass()}>Special handling</label>
              <textarea className={`${fieldClass()} mt-1 min-h-[72px]`} value={specialHandling} onChange={(e) => setSpecialHandling(e.target.value)} />
            </div>
            <div>
              <label className={labelClass()}>Internal comments / excerpt</label>
              <textarea
                className={`${fieldClass()} mt-1 min-h-[100px] font-mono text-xs`}
                value={internalComments}
                onChange={(e) => setInternalComments(e.target.value)}
                title="Prefilled from linked load internal_notes when present"
              />
            </div>
            <p className="text-xs text-[#64748b]">
              Customs / compliance and optional shipment controls stay here until intake PATCH is wired. Linked load: open full record in Loads for customs snapshot.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
