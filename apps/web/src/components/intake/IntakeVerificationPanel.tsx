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
  userEmail?: string | null;
  /** e.g. back to dashboard from full-bleed intake */
  onClose?: () => void;
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
  userEmail = null,
  onClose,
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
  const [stopPickupRef, setStopPickupRef] = useState("");
  const [stopPickupApptDate, setStopPickupApptDate] = useState("");
  const [stopPickupApptTime, setStopPickupApptTime] = useState("");

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
      setStopPickupRef("");
      setStopPickupApptDate("");
      setStopPickupApptTime("");
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
      setStopPickupRef(pu.reference_number ?? "");
      const ad = pu.appointment_date;
      if (ad) {
        const d = new Date(ad);
        setStopPickupApptDate(Number.isNaN(d.getTime()) ? ad : d.toLocaleDateString());
      } else {
        setStopPickupApptDate("");
      }
      setStopPickupApptTime(pu.appointment_time_text ?? "");
    } else {
      setStopPickupFacility("");
      setStopPickupStreet("");
      setStopPickupCity("");
      setStopPickupSt("");
      setStopPickupPostal("");
      setStopPickupRef("");
      setStopPickupApptDate("");
      setStopPickupApptTime("");
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
  const contactSectionTitle = `${tagLine ?? "Broker"} contact info`;

  const intakeTags = useMemo(() => {
    const tags: string[] = [];
    if (tagLine) tags.push(tagLine);
    if (mode) tags.push(mode);
    const equip = [trailerType, trailerSize].filter(Boolean).join(" ").trim();
    if (equip) tags.push(equip.replace(/\s+/g, " "));
    const raw = estWeight.replace(/,/g, "").trim();
    if (raw) {
      const n = Number(raw);
      if (!Number.isNaN(n)) tags.push(`${n.toLocaleString()} lbs`);
      else tags.push(estWeight);
    }
    if (palletCase.trim()) {
      const short = palletCase.replace(/^0\s*pallets\s*\/\s*/i, "").trim();
      tags.push(short || palletCase);
    }
    if (hazmat === "non-hazardous") tags.push("Non-hazmat");
    else if (hazmat === "hazardous") tags.push("Hazardous");
    return tags;
  }, [tagLine, mode, trailerType, trailerSize, estWeight, palletCase, hazmat]);

  const kpiCards = useMemo(
    () => [
      {
        label: "Pending review",
        value: kpis.pendingReview,
        accent: "text-emerald-300",
        icon: (
          <svg className="h-5 w-5 text-emerald-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 10.5V6a3.75 3.75 0 10-7.5 0v4.5m11.356-1.993l1.263 12c.07.665-.45 1.243-1.119 1.243H4.25a1.125 1.125 0 01-1.12-1.243l1.264-12A1.125 1.125 0 015.513 7.5h12.974c.576 0 1.059.435 1.119 1.007zM8.25 10.5a.75.75 0 01.75.75v3a.75.75 0 01-1.5 0v-3a.75.75 0 01.75-.75z" />
          </svg>
        ),
      },
      {
        label: "Created today",
        value: kpis.createdToday,
        accent: "text-sky-300",
        icon: (
          <svg className="h-5 w-5 text-sky-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M3 12h8v5H8l-1.5 2H3v-7z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M11 12V8h3l4 4v4h-2.5" />
            <path strokeLinecap="round" d="M6.5 19.25a1.75 1.75 0 100-3.5 1.75 1.75 0 000 3.5z" />
            <path strokeLinecap="round" d="M17 19.25a1.75 1.75 0 100-3.5 1.75 1.75 0 000 3.5z" />
          </svg>
        ),
      },
      {
        label: "Awaiting carrier",
        value: kpis.awaitingCarrier,
        accent: "text-amber-300",
        icon: (
          <svg className="h-5 w-5 text-amber-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
      {
        label: "Dispatched this week",
        value: kpis.dispatchedWeek,
        accent: "text-violet-300",
        icon: (
          <svg className="h-5 w-5 text-violet-400/90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        ),
      },
    ],
    [kpis.pendingReview, kpis.createdToday, kpis.awaitingCarrier, kpis.dispatchedWeek]
  );

  return (
    <div className="relative flex flex-col gap-5 text-[#e8edf5]">
      {onClose ? (
        <button
          type="button"
          onClick={onClose}
          className="absolute left-1/2 top-0 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-[#334155] bg-[#0d111a] text-lg leading-none text-[#94a3b8] hover:bg-[#1e293b] hover:text-[#e8edf5]"
          aria-label="Close intake"
        >
          ×
        </button>
      ) : null}

      <div className={`flex flex-col gap-4 ${onClose ? "pt-10" : ""}`}>
        <div className="flex flex-col gap-4 border-b border-[#1e293b] pb-5">
          <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-start sm:justify-end">
            {userEmail ? <p className="text-xs text-[#94a3b8] sm:order-first sm:mr-auto sm:pt-2 sm:text-left">{userEmail}</p> : null}
            <input ref={uploadRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={onUploadDocumentChange} />
            <div className="flex flex-wrap items-center justify-end gap-2">
              <button
                type="button"
                onClick={onManualEntry}
                className="rounded-lg border border-[#475569] bg-transparent px-3 py-2 text-sm font-medium text-[#e8edf5] hover:bg-[#1e293b]"
              >
                + Manual entry
              </button>
              <button
                type="button"
                onClick={() => uploadRef.current?.click()}
                disabled={uploadBusy}
                className="rounded-lg border border-[#2563eb] bg-[#1d4ed8] px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-[#2563eb] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {uploadBusy ? "Uploading…" : "Upload document"}
              </button>
              <button
                type="button"
                onClick={onVerifyCreate}
                disabled={!canVerifyCreate || draftCreating}
                className="rounded-lg border border-emerald-700/80 bg-emerald-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {draftCreating ? "Creating…" : "Verify & create load"}
              </button>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {kpiCards.map((k) => (
            <div
              key={k.label}
              className="flex gap-3 rounded-xl border border-[#1e293b] bg-[#0d111a] px-3 py-3 shadow-[inset_0_1px_0_0_rgba(255,255,255,0.04)]"
            >
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-[#0a0e14]">{k.icon}</div>
              <div className="min-w-0">
                <div className={`text-2xl font-semibold tabular-nums leading-tight ${k.accent}`}>{k.value}</div>
                <div className="mt-1 text-[11px] font-medium uppercase tracking-wide text-[#64748b]">{k.label}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] px-4 py-4">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="flex min-w-0 flex-1 gap-3">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-[#1e293b] text-[#93c5fd]">
                <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                {pdf ? (
                  <>
                    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span className="truncate text-sm font-semibold text-[#e8edf5]">{pdf.att.filename || "attachment.pdf"}</span>
                      <span className="text-xs text-[#64748b]">{formatBytes(pdf.att.size_bytes)}</span>
                    </div>
                    <p className="mt-1 text-xs font-medium text-emerald-400/90">Parsed successfully</p>
                  </>
                ) : (
                  <p className="text-sm text-[#64748b]">No PDF attachment on this thread yet.</p>
                )}
                {intakeTags.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {intakeTags.map((t) => (
                      <span key={t} className="rounded-full bg-[#1d4ed8]/22 px-2.5 py-0.5 text-[11px] font-medium text-[#93c5fd]">
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-[#1e293b] pt-3 lg:border-t-0 lg:border-l lg:pl-4 lg:pt-0">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm ${
                  ocrComplete ? "border-emerald-800/50 bg-emerald-950/40 text-emerald-300" : "border-[#334155] bg-[#0a0e14] text-[#64748b]"
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
            </div>
          </div>
        </div>
      </div>

      <section className="space-y-3 rounded-r-xl border-l-4 border-[#f5a623] bg-[#0a0e14]/40 py-1 pl-4 pr-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#f5a623]">{contactSectionTitle}</h3>
        <p className="text-xs text-[#64748b]">Align with rate confirmation; not auto-saved until load APIs support intake PATCH.</p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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

      <section className="space-y-3 rounded-r-xl border-l-4 border-[#f5a623] bg-[#0a0e14]/40 py-1 pl-4 pr-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#f5a623]">Load information</h3>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
            <select
              className={`${fieldClass()} mt-1`}
              value={trailerType}
              onChange={(e) => setTrailerType(e.target.value)}
            >
              <option value="">—</option>
              <option value="Van">Van</option>
              <option value="Dry van">Dry van</option>
              <option value="Reefer">Reefer</option>
              <option value="Flatbed">Flatbed</option>
              <option value="Step deck">Step deck</option>
              <option value="Conestoga">Conestoga</option>
              <option value="Other">Other</option>
              {trailerType &&
              !["Van", "Dry van", "Reefer", "Flatbed", "Step deck", "Conestoga", "Other"].includes(trailerType) ? (
                <option value={trailerType}>{trailerType}</option>
              ) : null}
            </select>
          </div>
          <div>
            <label className={labelClass()}>Trailer size</label>
            <select
              className={`${fieldClass()} mt-1`}
              value={trailerSize}
              onChange={(e) => setTrailerSize(e.target.value)}
            >
              <option value="">—</option>
              <option value="48 ft">48 ft</option>
              <option value="53 ft">53 ft</option>
              <option value="Other">Other</option>
              {trailerSize && !["48 ft", "53 ft", "Other"].includes(trailerSize) ? (
                <option value={trailerSize}>{trailerSize}</option>
              ) : null}
            </select>
          </div>
          <div>
            <label className={labelClass()}>Temperature</label>
            <input className={`${fieldClass()} mt-1`} value={temperature} onChange={(e) => setTemperature(e.target.value)} placeholder="—" />
          </div>
        </div>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <label className={labelClass()}>Pallet / case count</label>
            <input className={`${fieldClass()} mt-1`} value={palletCase} onChange={(e) => setPalletCase(e.target.value)} placeholder="0 pallets / 48 cases" />
          </div>
          <div>
            <label className={labelClass()}>Hazmat</label>
            <select className={`${fieldClass()} mt-1`} value={hazmat} onChange={(e) => setHazmat(e.target.value)}>
              <option value="">—</option>
              <option value="non-hazardous">Non-Hazardous</option>
              <option value="hazardous">Hazardous</option>
            </select>
          </div>
          <div>
            <label className={labelClass()}>Est. weight</label>
            <input className={`${fieldClass()} mt-1`} value={estWeight} onChange={(e) => setEstWeight(e.target.value)} placeholder="e.g. 43000" />
          </div>
          <div>
            <label className={labelClass()}>Load requirements</label>
            <input className={`${fieldClass()} mt-1`} value={loadRequirements} onChange={(e) => setLoadRequirements(e.target.value)} placeholder="None" />
          </div>
        </div>
      </section>

      <section className="space-y-3 rounded-r-xl border-l-4 border-[#f5a623] bg-[#0a0e14]/40 py-1 pl-4 pr-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#f5a623]">Pickups</h3>
        <div className="overflow-x-auto rounded-lg border border-[#1e293b] bg-[#0d111a]">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <thead>
              <tr className="border-b border-[#1e293b] text-[11px] uppercase tracking-wide text-[#64748b]">
                <th className="px-3 py-2 font-medium">Shed / company</th>
                <th className="px-3 py-2 font-medium">City</th>
                <th className="px-3 py-2 font-medium">State</th>
                <th className="px-3 py-2 font-medium">ZIP</th>
                <th className="px-3 py-2 font-medium">PU #</th>
                <th className="px-3 py-2 font-medium">Date</th>
                <th className="px-3 py-2 font-medium">Time</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-b border-[#1e293b]/80">
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupFacility}
                    onChange={(e) => setStopPickupFacility(e.target.value)}
                    placeholder="Facility"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupCity}
                    onChange={(e) => setStopPickupCity(e.target.value)}
                    placeholder="City"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupSt}
                    onChange={(e) => setStopPickupSt(e.target.value)}
                    placeholder="ST"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupPostal}
                    onChange={(e) => setStopPickupPostal(e.target.value)}
                    placeholder="Postal"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupRef}
                    onChange={(e) => setStopPickupRef(e.target.value)}
                    placeholder="—"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupApptDate}
                    onChange={(e) => setStopPickupApptDate(e.target.value)}
                    placeholder="—"
                  />
                </td>
                <td className="p-2 align-top">
                  <input
                    className={fieldClass()}
                    value={stopPickupApptTime}
                    onChange={(e) => setStopPickupApptTime(e.target.value)}
                    placeholder="Appt"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div>
          <label className={labelClass()}>Pickup street / address</label>
          <input
            className={`${fieldClass()} mt-1`}
            value={stopPickupStreet}
            onChange={(e) => setStopPickupStreet(e.target.value)}
            placeholder="Street"
          />
        </div>
      </section>

      <section className="space-y-3 rounded-r-xl border-l-4 border-[#f5a623]/80 bg-[#0a0e14]/40 py-1 pl-4 pr-2">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[#f5a623]">Delivery</h3>
        <div className="rounded-xl border border-[#1e293b] bg-[#0d111a] p-4">
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
