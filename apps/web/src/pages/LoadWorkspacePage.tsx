/**
 * Single load workspace route — manual create, saved load edit, or intake verify/edit.
 * Field UI is only in LoadWorkspaceForm; this page owns layout, data, save, and side panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode, type RefObject } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import clsx from "clsx";
import Button from "@/components/Button";
import StatusBadge from "@/components/StatusBadge";
import {
  addLoadNote,
  confirmLoadDocumentSnapshot,
  createLoad,
  getEmailThread,
  getEmailThreadMessages,
  getDriverAssignmentHints,
  getLoad,
  getLoadNotes,
  getTruckSuggestedTrailer,
  listBrokers,
  listBrokerContacts,
  listCustomsBrokers,
  listDrivers,
  listTrailers,
  listTrucks,
  listAuditEventsByEntity,
  parseLoadVersionConflict,
  parseLoadWorkspaceDocument,
  resolveBrokerIdentity,
  updateLoad,
  type Broker,
  type BrokerContact,
  type CustomsBroker,
  type Driver,
  type InboxMessageItem,
  type InboxThreadListItem,
  type Load,
  type LoadDocumentParseStop,
  type LoadNote,
  type AuditEventRow,
  type Trailer,
  type Truck,
} from "@/api";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { OPS } from "@/routes";
import { formatRouteFromStops, sortedStops as sortStops } from "@/utils/loadStops";
import { matchBrokerContactFromParsed } from "@/utils/matchBrokerFromSnapshot";
import { DispatchAssignmentStrip } from "@/loadWorkspace/DispatchAssignmentStrip";
import { LoadWorkspaceForm } from "@/loadWorkspace/LoadWorkspaceForm";
import {
  baselineSignatureFromLoad,
  buildLoadPersistPayload,
  buildVerificationTabIndexMap,
  emptyIntakeProposed,
  initialManualCreateStops,
  newDraftStop,
  SECTION_CONFIG,
  stopsToDraft,
  wsSectionTitle,
  type DraftStop,
  type IntakeProposedFields,
  type LoadWorkspaceMode,
} from "@/loadWorkspace/loadWorkspaceShared";
import { buildWorkspacePdfParseAppliedLabels } from "@/loadWorkspace/loadParseAppliedLabels";
import { filterMeaningfulParsedStops } from "@/loadWorkspace/loadParseStops";
import { describeWorkspacePdfParseOutcome } from "@/loadWorkspace/loadParseOutcome";
import { SectionSettlement } from "@/components/load/SectionSettlement";

type WorkspaceToolbarTone = "success" | "warning" | "error" | "neutral";

type WorkspaceToolbarMessage = {
  text: string;
  tone: WorkspaceToolbarTone;
};

function workspaceToolbarToneClassName(tone: WorkspaceToolbarTone): string {
  switch (tone) {
    case "success":
      return "text-emerald-700";
    case "warning":
      return "text-amber-600 dark:text-amber-200/95";
    case "error":
      return "text-red-700";
    case "neutral":
    default:
      return "text-[var(--trk-text-muted)]";
  }
}

function formatWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

function recipientPreview(raw: unknown): string {
  if (!raw) return "—";
  if (Array.isArray(raw)) {
    const values = raw
      .map((v) => {
        if (typeof v === "string") return v;
        if (v && typeof v === "object" && "email" in v) return String((v as { email?: unknown }).email ?? "");
        return "";
      })
      .filter(Boolean);
    return values.length ? values.join(", ") : "—";
  }
  return "—";
}

function WorkspaceModeReadout({ mode }: { mode: LoadWorkspaceMode }) {
  const items: { id: LoadWorkspaceMode; label: string }[] = [
    { id: "manual", label: "Manual" },
    { id: "intake", label: "Intake" },
    { id: "detail", label: "Detail" },
  ];
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Mode</span>
      <div
        className="inline-flex rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-0.5"
        role="group"
        aria-label="Workspace mode (determined by route, not clickable)"
      >
        {items.map((x) => (
          <span
            key={x.id}
            className={`rounded px-2.5 py-1 text-[11px] font-semibold ${
              mode === x.id ? "bg-amber-500 text-[var(--trk-btn-text)] shadow-sm" : "text-[var(--trk-text-muted)]"
            }`}
            aria-current={mode === x.id ? "true" : undefined}
          >
            {x.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function IntakeEmailRail({
  threadId,
  loading,
  error,
  messages,
}: {
  threadId: number;
  loading: boolean;
  error: string | null;
  messages: InboxMessageItem[];
}) {
  const head = messages[0];
  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--trk-surface)]">
      <div className="flex shrink-0 items-center justify-between border-b border-[var(--trk-border)] px-3.5 py-2.5">
        <span className={wsSectionTitle}>Source email</span>
        <span className="text-[10px] text-[var(--trk-text-muted)]">Thread #{threadId}</span>
      </div>
      {head ? (
        <div className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3.5 py-2.5">
          <div className="text-xs font-semibold text-[var(--trk-text)]">{head.from_email || "—"}</div>
          {head.subject ? <div className="line-clamp-2 text-[11px] text-[var(--trk-text-muted)]">{head.subject}</div> : null}
          <div className="text-[10px] text-[var(--trk-text-muted)]">
            {formatWhen(head.received_at || head.sent_at || head.created_at)}
          </div>
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto bg-[var(--trk-bg)] p-3">
        {loading ? <div className="text-xs text-[var(--trk-text-muted)]">Loading messages…</div> : null}
        {!loading && error ? <div className="text-xs text-red-400">{error}</div> : null}
        {!loading && !error && messages.length === 0 ? (
          <div className="text-xs text-[var(--trk-text-muted)]">No messages in this thread.</div>
        ) : null}
        {!loading && !error
          ? messages.map((m) => {
              const outbound = (m.direction || "").toLowerCase() === "outbound";
              return (
                <div key={m.id} className={`mb-3 flex ${outbound ? "justify-end" : "justify-start"}`}>
                  <article
                    className={`max-w-[min(100%,280px)] rounded-lg border px-2.5 py-2 text-[11px] leading-relaxed ${
                      outbound ? "border-[var(--trk-accent)]/30 bg-[var(--trk-surface-2)]" : "border-[var(--trk-border)] bg-[var(--trk-surface)]"
                    }`}
                  >
                    <div className="mb-1.5 space-y-0.5 text-[10px] text-[var(--trk-text-muted)]">
                      <div>From: {m.from_email || "—"}</div>
                      <div>{formatWhen(m.received_at || m.sent_at || m.created_at)}</div>
                      {m.subject ? <div className="text-[var(--trk-text)]">{m.subject}</div> : null}
                    </div>
                    <p className="whitespace-pre-wrap text-[var(--trk-text)]">{m.body_text || m.snippet || "—"}</p>
                    {m.attachments && m.attachments.length > 0 ? (
                      <ul className="mt-1.5 space-y-0.5 text-[10px] text-[var(--trk-text-muted)]">
                        {m.attachments.map((a) => (
                          <li key={a.id}>
                            {a.filename || a.external_attachment_id}
                            {a.mime_type ? ` · ${a.mime_type}` : ""}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                </div>
              );
            })
          : null}
      </div>
    </div>
  );
}

function ReferenceTextRail({
  title,
  hint,
  docLines,
  docScrollRef,
  docLineRefs,
  activeDocLine,
}: {
  title: string;
  hint: ReactNode;
  docLines: string[];
  docScrollRef: RefObject<HTMLDivElement>;
  docLineRefs: MutableRefObject<Map<number, HTMLDivElement | null>>;
  activeDocLine: number | null;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-[var(--trk-surface)]">
      <div className="shrink-0 border-b border-[var(--trk-border)] px-3.5 py-2.5">
        <span className={wsSectionTitle}>{title}</span>
        <p className="mt-1 text-[11px] leading-snug text-[var(--trk-text-muted)]">{hint}</p>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {docLines.length ? (
          <div
            ref={docScrollRef}
            className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-2 font-mono text-[11px] leading-snug text-[var(--trk-text)]"
          >
            {docLines.map((line, i) => (
              <div
                key={i}
                ref={(el) => {
                  docLineRefs.current.set(i, el);
                }}
                className="whitespace-pre-wrap break-words rounded px-1 py-0.5"
                style={activeDocLine === i ? { background: "rgba(245,166,35,0.2)" } : undefined}
              >
                {line || " "}
              </div>
            ))}
          </div>
        ) : (
          <p className="rounded-md border border-dashed border-[var(--trk-border)] bg-[var(--trk-surface)]/50 px-3 py-6 text-center text-xs text-[var(--trk-text-muted)]">
            Nothing to show yet — use internal notes in the form.
          </p>
        )}
      </div>
    </div>
  );
}

function extractedStopsToDraft(stops: LoadDocumentParseStop[]): DraftStop[] {
  const ts = Date.now();
  return stops.map((s, i) => {
    const t = (s.stop_type || "").toLowerCase();
    let stop_type: DraftStop["stop_type"] = "DELIVERY";
    if (t === "pickup") stop_type = "PICKUP";
    else if (t === "drop") stop_type = "DROP";
    else if (t === "delivery") stop_type = "DELIVERY";
    return {
      id: 0,
      load_id: 0,
      stop_type,
      sequence: s.sequence ?? i,
      facility_name: s.facility_name ?? null,
      street: s.street ?? null,
      city: s.city ?? null,
      state_or_province: s.state_or_province ?? null,
      postal_code: s.postal_code ?? null,
      country: s.country ?? null,
      reference_number: s.reference_number ?? null,
      appointment_type: s.appointment_type ?? null,
      appointment_date: s.appointment_date ?? null,
      appointment_time_text: s.appointment_time_text ?? null,
      scheduled_at: null,
      notes: s.notes ?? null,
      commodity_notes: null,
      created_at: null,
      updated_at: null,
      _key: `pdf-${ts}-${i}-${Math.random().toString(36).slice(2, 8)}`,
    };
  });
}

function ContextRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="text-xs text-[var(--trk-text-muted)]">{label}</dt>
      <dd className={`mt-0.5 text-[var(--trk-text)] ${mono ? "font-mono text-xs break-all" : ""}`}>{value || "—"}</dd>
    </div>
  );
}

export default function LoadWorkspacePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { id: idParam } = useParams<{ id: string }>();
  const [searchParams] = useSearchParams();

  const isManual = location.pathname === OPS.LOAD_NEW || location.pathname.endsWith("/loads/new");
  const intakeThreadRaw = searchParams.get(OPS.LOAD_INTAKE_THREAD_QUERY);
  const intakeThreadId =
    intakeThreadRaw != null && intakeThreadRaw !== "" ? Number(intakeThreadRaw) : Number.NaN;
  const hasIntakeThread = Number.isFinite(intakeThreadId) && intakeThreadId > 0;

  const loadIdFromRoute = !isManual && idParam ? Number(idParam) : Number.NaN;
  const modeParam = searchParams.get("mode");
  const workspaceMode: LoadWorkspaceMode = isManual
    ? "manual"
    : hasIntakeThread
      ? "intake"
      : modeParam === "payroll"
        ? "payroll"
        : modeParam === "audit"
          ? "audit"
          : "detail";

  const sectionConfig = SECTION_CONFIG[workspaceMode];

  const dispatchAssignRaw = searchParams.get(OPS.LOAD_DISPATCH_ASSIGN_QUERY);
  const dispatchAssignContext =
    dispatchAssignRaw !== null && dispatchAssignRaw !== "0" && dispatchAssignRaw !== "false";

  const [customsBrokers, setCustomsBrokers] = useState<CustomsBroker[]>([]);
  const [freightBrokers, setFreightBrokers] = useState<Broker[]>([]);
  const [brokerContacts, setBrokerContacts] = useState<BrokerContact[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [load, setLoad] = useState<Load | null>(null);

  const showDispatchAssignmentStrip =
    workspaceMode === "detail" &&
    !isManual &&
    load != null &&
    (load.status || "").toLowerCase() === "unassigned" &&
    dispatchAssignContext;

  const [loadNotes, setLoadNotes] = useState<LoadNote[]>([]);
  const [newNoteBody, setNewNoteBody] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toolbarMessage, setToolbarMessage] = useState<WorkspaceToolbarMessage | null>(null);
  const [customsMessage, setCustomsMessage] = useState<string | null>(null);
  const [serverConflict, setServerConflict] = useState<{
    serverVersion: number | null;
    serverSnapshot: Load | null;
  } | null>(null);
  const [baselineFormSignature, setBaselineFormSignature] = useState<string | null>(null);

  const [intakeMessages, setIntakeMessages] = useState<InboxMessageItem[]>([]);
  const [intakeThread, setIntakeThread] = useState<InboxThreadListItem | null>(null);
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);

  const [draftStops, setDraftStops] = useState<DraftStop[]>(() =>
    isManual ? initialManualCreateStops() : [],
  );

  const [status, setStatus] = useState(isManual ? "unassigned" : "");
  const [loadNumber, setLoadNumber] = useState("");
  const [brokerId, setBrokerId] = useState<number | null>(null);
  const [brokerContactId, setBrokerContactId] = useState<number | null>(null);
  const [brokerNameSnapshot, setBrokerNameSnapshot] = useState("");
  const [brokerContactNameSnapshot, setBrokerContactNameSnapshot] = useState("");
  const [brokerContactPhoneSnapshot, setBrokerContactPhoneSnapshot] = useState("");
  const [brokerContactExtensionSnapshot, setBrokerContactExtensionSnapshot] = useState("");
  const [brokerContactEmailSnapshot, setBrokerContactEmailSnapshot] = useState("");
  const [brokerLoadReference, setBrokerLoadReference] = useState("");
  const [freightMode, setFreightMode] = useState("");
  const [equipmentType, setEquipmentType] = useState("");
  const [trailerType, setTrailerType] = useState("");
  const [trailerSize, setTrailerSize] = useState("");
  const [commodity, setCommodity] = useState("");
  const [estimatedWeight, setEstimatedWeight] = useState("");
  const [hazmat, setHazmat] = useState<"unset" | "yes" | "no">("unset");
  const [temperatureRequirement, setTemperatureRequirement] = useState("");
  const [palletCaseCount, setPalletCaseCount] = useState("");
  const [rate, setRate] = useState("");
  const [customerRate, setCustomerRate] = useState("");
  const [miles, setMiles] = useState("");
  const [driverId, setDriverId] = useState<number | null>(null);
  const [truckId, setTruckId] = useState<number | null>(null);
  const [trailerId, setTrailerId] = useState<number | null>(null);
  const [customsBrokerId, setCustomsBrokerId] = useState<number | null>(null);
  const [internalNotes, setInternalNotes] = useState("");
  const [parseBusy, setParseBusy] = useState(false);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  /** Labels for field groups applied by the latest successful PDF parse (read-only summary). */
  const [lastParseAppliedLabels, setLastParseAppliedLabels] = useState<string[] | null>(null);
  const pdfInputRef = useRef<HTMLInputElement | null>(null);
  const docScrollRef = useRef<HTMLDivElement | null>(null);
  const docLineRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());
  const [activeDocLine, setActiveDocLine] = useState<number | null>(null);
  const loadConcurrencyRef = useRef<number | null>(null);
  const formDirtyRef = useRef(false);

  useEffect(() => {
    loadConcurrencyRef.current = load?.concurrency_version ?? null;
  }, [load?.concurrency_version]);

  const docLines = useMemo(() => {
    const raw = internalNotes || "";
    if (!raw.trim()) return [];
    return raw.split(/\r?\n/);
  }, [internalNotes]);

  const focusDoc = useCallback(
    (opts: { tokens: string[]; fallbackToken?: string }) => {
      if (!docLines.length) return;
      const tokens = (opts.tokens || [])
        .map((t) => (t || "").trim())
        .filter(Boolean)
        .slice(0, 6);
      const needle = (tokens[0] || opts.fallbackToken || "").toLowerCase();
      if (!needle) return;
      let bestIdx = -1;
      let bestScore = -1;
      for (let i = 0; i < docLines.length; i++) {
        const line = docLines[i].toLowerCase();
        if (!line) continue;
        let score = 0;
        for (const t of tokens) {
          const tl = t.toLowerCase();
          if (tl && line.includes(tl)) score += Math.min(8, tl.length);
        }
        if (line.includes(needle)) score += 10;
        if (score > bestScore) {
          bestScore = score;
          bestIdx = i;
        }
      }
      if (bestIdx < 0) return;
      setActiveDocLine(bestIdx);
      requestAnimationFrame(() => {
        const el = docLineRefs.current.get(bestIdx);
        if (el) el.scrollIntoView({ block: "center", behavior: "smooth" });
      });
    },
    [docLines],
  );

  const hydrateFromLoad = useCallback((l: Load) => {
    setStatus(l.status);
    setLoadNumber(l.load_number || "");
    setBrokerId(l.broker_id ?? null);
    setBrokerContactId(l.broker_contact_id ?? null);
    if (l.broker_contact) {
      setBrokerContacts([{
        id: l.broker_contact.id,
        broker_id: l.broker_contact.broker_id,
        name: l.broker_contact.name,
        first_name: null,
        last_name: null,
        role: null,
        department: null,
        phone: l.broker_contact.phone ?? null,
        extension: l.broker_contact.extension ?? null,
        fax: null,
        email: l.broker_contact.email ?? null,
        is_primary: false,
        notes: null,
        is_active: true,
        archived_at: null,
        created_at: "",
        updated_at: "",
      }]);
    }
    setBrokerNameSnapshot(l.broker_name_snapshot ?? "");
    setBrokerContactNameSnapshot(l.broker_contact_name_snapshot ?? "");
    setBrokerContactPhoneSnapshot(l.broker_contact_phone_snapshot ?? "");
    setBrokerContactExtensionSnapshot(l.broker_contact_extension_snapshot ?? "");
    setBrokerContactEmailSnapshot(l.broker_contact_email_snapshot ?? "");
    setBrokerLoadReference(l.broker_load_reference ?? "");
    setFreightMode(l.mode ?? "");
    setEquipmentType(l.equipment_type ?? "");
    setTrailerType(l.trailer_type ?? "");
    setTrailerSize(l.trailer_size ?? "");
    setCommodity(l.commodity ?? "");
    setEstimatedWeight(l.estimated_weight != null ? String(l.estimated_weight) : "");
    if (l.hazmat_flag === true) setHazmat("yes");
    else if (l.hazmat_flag === false) setHazmat("no");
    else setHazmat("unset");
    setTemperatureRequirement(l.temperature_requirement ?? "");
    setPalletCaseCount(l.pallet_case_count ?? "");
    setRate(l.rate != null ? String(l.rate) : "");
    setCustomerRate(l.customer_rate != null ? String(l.customer_rate) : "");
    setMiles(l.miles != null ? String(l.miles) : "");
    setDriverId(l.driver_id ?? null);
    setTruckId(l.truck_id ?? null);
    setTrailerId(l.trailer_id ?? null);
    setCustomsBrokerId(l.customs_broker_id ?? null);
    setInternalNotes(l.internal_notes ?? "");
    setDraftStops(stopsToDraft(l.stops));
  }, []);

  const currentFormSignature = useMemo(
    () =>
      JSON.stringify(
        buildLoadPersistPayload({
          status,
          loadNumber,
          brokerId,
          brokerContactId,
          brokerNameSnapshot,
          brokerContactNameSnapshot,
          brokerContactPhoneSnapshot,
          brokerContactExtensionSnapshot,
          brokerContactEmailSnapshot,
          brokerLoadReference,
          mode: freightMode,
          equipmentType,
          trailerType,
          trailerSize,
          commodity,
          estimatedWeight,
          hazmat,
          temperatureRequirement,
          palletCaseCount,
          rate,
          customerRate,
          miles,
          driverId,
          truckId,
          trailerId,
          customsBrokerId,
          internalNotes,
          draftStops,
        }),
      ),
    [
      status,
      loadNumber,
      brokerId,
      brokerContactId,
      brokerNameSnapshot,
      brokerContactNameSnapshot,
      brokerContactPhoneSnapshot,
      brokerContactExtensionSnapshot,
      brokerContactEmailSnapshot,
      brokerLoadReference,
      freightMode,
      equipmentType,
      trailerType,
      trailerSize,
      commodity,
      estimatedWeight,
      hazmat,
      temperatureRequirement,
      palletCaseCount,
      rate,
      customerRate,
      miles,
      driverId,
      truckId,
      trailerId,
      customsBrokerId,
      internalNotes,
      draftStops,
    ],
  );

  const formDirty =
    workspaceMode !== "manual" &&
    baselineFormSignature !== null &&
    currentFormSignature !== baselineFormSignature;

  useEffect(() => {
    formDirtyRef.current = formDirty;
  }, [formDirty]);

  useEffect(() => {
    if (workspaceMode === "manual") {
      setBaselineFormSignature(null);
      return;
    }
    if (!load || loading) return;
    setBaselineFormSignature(baselineSignatureFromLoad(load));
  }, [workspaceMode, load, loading]);

  const refreshLoadFromServer = useCallback(async () => {
    if (workspaceMode === "manual" || !Number.isFinite(loadIdFromRoute)) return;
    const lid = loadIdFromRoute;
    try {
      const remote = await getLoad(lid);
      const localVer = loadConcurrencyRef.current;
      if (
        formDirtyRef.current &&
        localVer != null &&
        remote.concurrency_version != null &&
        remote.concurrency_version !== localVer
      ) {
        setServerConflict({
          serverVersion: remote.concurrency_version ?? null,
          serverSnapshot: remote,
        });
        return;
      }
      if (!formDirtyRef.current) {
        const notes = await getLoadNotes(lid).catch(() => [] as LoadNote[]);
        setLoad(remote);
        hydrateFromLoad(remote);
        setLoadNotes(Array.isArray(notes) ? notes : []);
        setServerConflict(null);
        setToolbarMessage(null);
      }
    } catch {
      /* background refresh — ignore */
    }
  }, [workspaceMode, loadIdFromRoute, hydrateFromLoad]);

  const canWorkspaceParsePdf =
    workspaceMode === "manual" || workspaceMode === "intake" || workspaceMode === "detail";

  const onParseWorkspacePdf = useCallback(
    async (file: File) => {
      if (!canWorkspaceParsePdf) return;
      setParseBusy(true);
      setParseWarnings([]);
      setToolbarMessage(null);
      setLastParseAppliedLabels(null);
      try {
        const res = await parseLoadWorkspaceDocument(file, {
          emailThreadId: hasIntakeThread ? intakeThreadId : undefined,
          loadId: !isManual && Number.isFinite(loadIdFromRoute) ? loadIdFromRoute : undefined,
        });
        const ex = res.extracted;
        let resolvedBrokerIdForSummary: number | null = null;
        let brokerContactMatchedForSummary = false;
        const brokerNameSnap = ex.broker_name_snapshot?.trim() ?? "";
        if (brokerNameSnap) {
          setBrokerNameSnapshot(brokerNameSnap);
        }
        const mcSnap = ex.broker_mc_number_snapshot?.trim() ?? "";
        const dotSnap = ex.broker_dot_number_snapshot?.trim() ?? "";
        if (mcSnap || dotSnap) {
          let resolvedBrokerId: number | null = null;
          try {
            const resolved = await resolveBrokerIdentity({
              mc_number: mcSnap || undefined,
              dot_number: dotSnap || undefined,
            });
            resolvedBrokerId = resolved.broker_id ?? null;
          } catch {
            resolvedBrokerId = null;
          }
          resolvedBrokerIdForSummary = resolvedBrokerId;
          setBrokerId(resolvedBrokerId);
          setBrokerContactId(null);
          if (resolvedBrokerId != null) {
            try {
              const paged = await listBrokerContacts(resolvedBrokerId, {
                page: 1,
                size: 200,
                include_archived: false,
              });
              const items = paged.items || [];
              setBrokerContacts(items);
              const matchedContact = matchBrokerContactFromParsed(items, {
                name: ex.broker_contact_name_snapshot,
                email: ex.broker_contact_email_snapshot,
                phone: ex.broker_contact_phone_snapshot,
              });
              if (matchedContact) {
                brokerContactMatchedForSummary = true;
                setBrokerContactId(matchedContact.id);
              }
            } catch {
              setBrokerContacts([]);
            }
          } else {
            setBrokerContacts([]);
          }
        }
        if (ex.broker_contact_name_snapshot?.trim()) {
          setBrokerContactNameSnapshot(ex.broker_contact_name_snapshot.trim());
        }
        if (ex.broker_contact_phone_snapshot?.trim()) {
          setBrokerContactPhoneSnapshot(ex.broker_contact_phone_snapshot.trim());
        }
        if (ex.broker_contact_email_snapshot?.trim()) {
          setBrokerContactEmailSnapshot(ex.broker_contact_email_snapshot.trim());
        }
        if (ex.broker_load_reference?.trim()) setBrokerLoadReference(ex.broker_load_reference.trim());
        if (ex.mode?.trim()) setFreightMode(ex.mode.trim());
        if (ex.equipment_type?.trim()) setEquipmentType(ex.equipment_type.trim());
        if (ex.trailer_type?.trim()) setTrailerType(ex.trailer_type.trim());
        if (ex.trailer_size?.trim()) setTrailerSize(ex.trailer_size.trim());
        if (ex.commodity?.trim()) setCommodity(ex.commodity.trim());
        if (ex.estimated_weight != null) setEstimatedWeight(String(ex.estimated_weight));
        if (ex.temperature_requirement?.trim()) {
          setTemperatureRequirement(ex.temperature_requirement.trim());
        }
        if (ex.rate != null) setRate(String(ex.rate));
        if (ex.customer_rate != null) setCustomerRate(String(ex.customer_rate));
        if (ex.miles != null) setMiles(String(Math.round(ex.miles)));
        let notesBody = res.raw_text?.trim() || "";
        if (ex.customs_broker_name?.trim()) {
          const cline = `Customs broker (from document): ${ex.customs_broker_name.trim()}`;
          notesBody = notesBody ? `${notesBody}\n\n---\n${cline}` : cline;
        }
        setInternalNotes(notesBody);
        const meaningfulStops = filterMeaningfulParsedStops(ex.stops ?? []);
        if (meaningfulStops.length > 0) {
          setDraftStops(extractedStopsToDraft(meaningfulStops));
        }
        setParseWarnings(res.warnings ?? []);
        const outcome = describeWorkspacePdfParseOutcome(res.extracted, res.raw_text, res.warnings ?? []);
        const tone: WorkspaceToolbarTone =
          outcome.tone === "success" ? "success" : outcome.tone === "warning" ? "warning" : "neutral";
        setToolbarMessage({ text: outcome.headline, tone });
        const appliedLabels = buildWorkspacePdfParseAppliedLabels(res.extracted, res.raw_text, {
          mcOrDotAttempted: Boolean(mcSnap || dotSnap),
          resolvedBrokerId: resolvedBrokerIdForSummary,
          brokerContactMatched: brokerContactMatchedForSummary,
        });
        setLastParseAppliedLabels(appliedLabels.length > 0 ? appliedLabels : null);
      } catch (e: unknown) {
        const msg = e instanceof Error ? e.message : "PDF parse failed";
        setToolbarMessage({ text: msg, tone: "error" });
        setLastParseAppliedLabels(null);
      } finally {
        setParseBusy(false);
      }
    },
    [canWorkspaceParsePdf, hasIntakeThread, intakeThreadId, isManual, loadIdFromRoute],
  );

  useOperationalRefresh({
    intervalMs: null,
    enabled: workspaceMode !== "manual" && Number.isFinite(loadIdFromRoute) && !loading,
    isDirty: formDirty,
    onRefresh: () => void refreshLoadFromServer(),
  });

  useEffect(() => {
    if (workspaceMode === "manual") {
      setLoading(true);
      setError(null);
      Promise.all([
        listCustomsBrokers({ page: 1, size: 200, include_inactive: false }),
        listBrokers({ page: 1, size: 200, sort: "name_asc" }),
        listDrivers({ limit: 500, include_inactive: false }),
        listTrucks({ page: 1, size: 200, status: ["active"] }),
        listTrailers({ page: 1, size: 200, status: ["active"] }),
      ])
        .then(([customsPaged, brPaged, dr, trk, trl]) => {
          setCustomsBrokers(customsPaged.items || []);
          setFreightBrokers(brPaged.items || []);
          setDrivers(dr);
          setTrucks(trk.items || []);
          setTrailers(trl.items || []);
        })
        .catch((e) => setError(e?.message || "Failed to load workspace"))
        .finally(() => setLoading(false));
      return;
    }

    if (!Number.isFinite(loadIdFromRoute)) {
      setLoading(false);
      setError("Invalid load ID");
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);
    const lid = loadIdFromRoute;
    Promise.all([
      getLoad(lid),
      listCustomsBrokers({ page: 1, size: 200, include_inactive: false }),
      listBrokers({ page: 1, size: 200, sort: "name_asc" }),
      listDrivers({ limit: 500, include_inactive: false }),
      listTrucks({ page: 1, size: 200, status: ["active"] }),
      listTrailers({ page: 1, size: 200, status: ["active"] }),
      getLoadNotes(lid).catch(() => [] as LoadNote[]),
    ])
      .then(([l, customsPaged, brPaged, dr, trk, trl, notes]) => {
        if (cancelled) return;
        setLoad(l);
        hydrateFromLoad(l);
        setCustomsBrokers(customsPaged.items || []);
        setFreightBrokers(brPaged.items || []);
        setDrivers(dr);
        setTrucks(trk.items || []);
        setTrailers(trl.items || []);
        setLoadNotes(Array.isArray(notes) ? notes : []);
      })
      .catch((e) => {
        if (!cancelled) setError(e?.message || "Failed to load");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [workspaceMode, loadIdFromRoute, hydrateFromLoad]);

  useEffect(() => {
    if (workspaceMode !== "intake" || !hasIntakeThread) {
      setIntakeMessages([]);
      setIntakeThread(null);
      setIntakeError(null);
      setIntakeLoading(false);
      return;
    }
    let cancelled = false;
    setIntakeLoading(true);
    setIntakeError(null);
    Promise.all([
      getEmailThreadMessages(intakeThreadId),
      getEmailThread(intakeThreadId),
    ])
      .then(([msgs, thread]) => {
        if (cancelled) return;
        setIntakeMessages(msgs ?? []);
        setIntakeThread(thread);
      })
      .catch((err: unknown) => {
        if (!cancelled) setIntakeError(err instanceof Error ? err.message : "Failed to load thread");
      })
      .finally(() => {
        if (!cancelled) setIntakeLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceMode, hasIntakeThread, intakeThreadId]);

  useEffect(() => {
    if (!brokerId) {
      setBrokerContacts([]);
      return;
    }
    listBrokerContacts(brokerId, { page: 1, size: 200, include_archived: false })
      .then((p) => setBrokerContacts(p.items || []))
      .catch(() => setBrokerContacts([]));
  }, [brokerId]);

  const intakeProposed = useMemo((): IntakeProposedFields | null => {
    if (workspaceMode !== "intake" || !intakeThread) return null;
    return {
      ...emptyIntakeProposed(),
      brokerNameSnapshot: intakeThread.linked_broker_name ?? null,
      pickupDeliverySummary: intakeThread.pickup_delivery_summary ?? null,
    };
  }, [workspaceMode, intakeThread]);

  const contextSummary = useMemo(() => {
    if (!load) return "";
    return [
      load.broker_match_method && `Match: ${load.broker_match_method.replace(/_/g, " ")}`,
      load.broker_match_confidence_tier && `Tier ${load.broker_match_confidence_tier}`,
    ]
      .filter(Boolean)
      .join(" · ");
  }, [load]);

  const contextStops = useMemo(() => {
    if (!load?.stops?.length) return [];
    return sortStops(load.stops);
  }, [load]);

  const sortedDraftStops = useMemo(
    () => [...draftStops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0)),
    [draftStops],
  );

  const verificationTabIndex = useMemo(
    () => buildVerificationTabIndexMap(sortedDraftStops),
    [sortedDraftStops],
  );

  async function onCreate() {
    setSaving(true);
    setToolbarMessage(null);
    try {
      const payload = buildLoadPersistPayload({
        status,
        loadNumber,
        brokerId,
        brokerContactId,
        brokerNameSnapshot,
        brokerContactNameSnapshot,
        brokerContactPhoneSnapshot,
        brokerContactExtensionSnapshot,
        brokerContactEmailSnapshot,
        brokerLoadReference,
        mode: freightMode,
        equipmentType,
        trailerType,
        trailerSize,
        commodity,
        estimatedWeight,
        hazmat,
        temperatureRequirement,
        palletCaseCount,
        rate,
        customerRate,
        miles,
        driverId,
        truckId,
        trailerId,
        customsBrokerId,
        internalNotes,
        draftStops,
      });
      const created = await createLoad(payload);
      navigate(OPS.LOAD_DETAIL(created.id), { replace: true });
    } catch (e: unknown) {
      setToolbarMessage({ text: (e as Error)?.message || "Could not create load", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function onReloadServerVersion() {
    if (!load) return;
    setSaving(true);
    setToolbarMessage(null);
    setServerConflict(null);
    try {
      const [remote, notes] = await Promise.all([
        getLoad(load.id),
        getLoadNotes(load.id).catch(() => [] as LoadNote[]),
      ]);
      setLoad(remote);
      hydrateFromLoad(remote);
      setLoadNotes(Array.isArray(notes) ? notes : []);
      setToolbarMessage({ text: "Loaded latest from server.", tone: "neutral" });
    } catch (e: unknown) {
      setToolbarMessage({ text: (e as Error)?.message || "Could not reload", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function onSave() {
    if (!load) return;
    const expectedVersion = load.concurrency_version ?? 1;
    setSaving(true);
    setToolbarMessage(null);
    setError(null);
    try {
      const updated = await updateLoad(load.id, {
        ...buildLoadPersistPayload({
          status,
          loadNumber,
          brokerId,
          brokerContactId,
          brokerNameSnapshot,
          brokerContactNameSnapshot,
          brokerContactPhoneSnapshot,
          brokerContactExtensionSnapshot,
          brokerContactEmailSnapshot,
          brokerLoadReference,
          mode: freightMode,
          equipmentType,
          trailerType,
          trailerSize,
          commodity,
          estimatedWeight,
          hazmat,
          temperatureRequirement,
          palletCaseCount,
          rate,
          customerRate,
          miles,
          driverId,
          truckId,
          trailerId,
          customsBrokerId,
          internalNotes,
          draftStops,
        }),
        expected_concurrency_version: expectedVersion,
      });
      setLoad(updated);
      hydrateFromLoad(updated);
      setToolbarMessage({ text: "Saved.", tone: "success" });
      setServerConflict(null);
    } catch (e: unknown) {
      const c = parseLoadVersionConflict(e);
      if (c) {
        setServerConflict({
          serverVersion: c.server_version,
          serverSnapshot: c.server_snapshot,
        });
        setToolbarMessage({
          text: "Load was modified elsewhere — see conflict details above.",
          tone: "warning",
        });
      } else {
        setToolbarMessage({ text: (e as Error)?.message || "Save failed", tone: "error" });
      }
    } finally {
      setSaving(false);
    }
  }

  const applyDriverAssignmentHints = useCallback(async (did: number) => {
    try {
      const h = await getDriverAssignmentHints(did);
      setTruckId(h.truck_id ?? null);
      let nextTrailer = h.trailer_id ?? null;
      if (h.truck_id != null && nextTrailer == null) {
        const t = await getTruckSuggestedTrailer(h.truck_id);
        nextTrailer = t.trailer_id ?? null;
      }
      setTrailerId(nextTrailer);
    } catch {
      /* hints are optional */
    }
  }, []);

  const onDispatchStripDriverSelect = useCallback(
    (id: number | null) => {
      setDriverId(id);
      if (id != null) void applyDriverAssignmentHints(id);
      else {
        setTruckId(null);
        setTrailerId(null);
      }
    },
    [applyDriverAssignmentHints],
  );

  const onDispatchStripTruckSelect = useCallback((id: number | null) => {
    setTruckId(id);
    if (id == null) return;
    getTruckSuggestedTrailer(id)
      .then((t) => {
        if (t.trailer_id != null) setTrailerId(t.trailer_id);
      })
      .catch(() => {});
  }, []);

  const onDispatchStripTrailerSelect = useCallback((id: number | null) => {
    setTrailerId(id);
  }, []);

  const onDispatchAssign = useCallback(async () => {
    if (!load || driverId == null) return;
    const expectedVersion = load.concurrency_version ?? 1;
    setSaving(true);
    setToolbarMessage(null);
    setError(null);
    try {
      const updated = await updateLoad(load.id, {
        expected_concurrency_version: expectedVersion,
        status: "assigned",
        driver_id: driverId,
        truck_id: truckId,
        trailer_id: trailerId,
      });
      setLoad(updated);
      hydrateFromLoad(updated);
      setToolbarMessage({
        text: "Load assigned (trip number starts at Dispatched).",
        tone: "success",
      });
      setServerConflict(null);
      const sp = new URLSearchParams(searchParams);
      sp.delete(OPS.LOAD_DISPATCH_ASSIGN_QUERY);
      const next = sp.toString() ? `?${sp.toString()}` : "";
      navigate({ pathname: location.pathname, search: next }, { replace: true });
    } catch (e: unknown) {
      const c = parseLoadVersionConflict(e);
      if (c) {
        setServerConflict({
          serverVersion: c.server_version,
          serverSnapshot: c.server_snapshot,
        });
        setToolbarMessage({
          text: "Load was modified elsewhere — see conflict details above.",
          tone: "warning",
        });
      } else {
        setToolbarMessage({ text: (e as Error)?.message || "Assignment failed", tone: "error" });
      }
    } finally {
      setSaving(false);
    }
  }, [load, driverId, truckId, trailerId, hydrateFromLoad, searchParams, navigate, location.pathname]);

  async function onCustomsBrokerSelect(ev: React.ChangeEvent<HTMLSelectElement>) {
    if (!load || load.document_snapshot_confirmed_at) return;
    const v = ev.target.value;
    const next = v === "" ? null : Number(v);
    const prev = load.customs_broker_id ?? null;
    const expectedVersion = load.concurrency_version ?? 1;
    setCustomsBrokerId(next);
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await updateLoad(load.id, {
        customs_broker_id: next,
        expected_concurrency_version: expectedVersion,
      });
      setLoad(updated);
      setCustomsBrokerId(updated.customs_broker_id ?? null);
      setCustomsMessage("Customs broker updated.");
      setServerConflict(null);
    } catch (e: unknown) {
      setCustomsBrokerId(prev);
      const c = parseLoadVersionConflict(e);
      if (c) {
        setServerConflict({
          serverVersion: c.server_version,
          serverSnapshot: c.server_snapshot,
        });
        setCustomsMessage("Load was modified elsewhere — see conflict details above.");
      } else {
        setCustomsMessage((e as Error)?.message || "Could not update customs broker");
      }
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmSnapshot() {
    if (!load) return;
    const expectedVersion = load.concurrency_version ?? 1;
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await confirmLoadDocumentSnapshot(load.id, expectedVersion);
      setLoad(updated);
      hydrateFromLoad(updated);
      setCustomsMessage("Document snapshot confirmed.");
      setServerConflict(null);
    } catch (e: unknown) {
      const c = parseLoadVersionConflict(e);
      if (c) {
        setServerConflict({
          serverVersion: c.server_version,
          serverSnapshot: c.server_snapshot,
        });
        setCustomsMessage("Load was modified elsewhere — see conflict details above.");
      } else {
        setCustomsMessage((e as Error)?.message || "Confirm failed");
      }
    } finally {
      setSaving(false);
    }
  }

  async function onAddNote() {
    if (!load || !newNoteBody.trim()) return;
    setSaving(true);
    try {
      await addLoadNote(load.id, newNoteBody.trim());
      setNewNoteBody("");
      const notes = await getLoadNotes(load.id);
      setLoadNotes(notes);
    } catch (e: unknown) {
      setToolbarMessage({ text: (e as Error)?.message || "Could not add note", tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  function updateStop(key: string, patch: Partial<DraftStop>) {
    setDraftStops((rows) => rows.map((r) => (r._key === key ? { ...r, ...patch } : r)));
  }

  function removeStop(key: string) {
    setDraftStops((rows) => rows.filter((r) => r._key !== key));
  }

  function addStop() {
    const maxSeq =
      draftStops.length === 0 ? 0 : Math.max(...draftStops.map((s) => s.sequence ?? 0)) + 1;
    setDraftStops((rows) => [...rows, newDraftStop(maxSeq)]);
  }

  function moveStop(key: string, dir: -1 | 1) {
    setDraftStops((rows) => {
      const sorted = [...rows].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
      const i = sorted.findIndex((r) => r._key === key);
      const j = i + dir;
      if (i < 0 || j < 0 || j >= sorted.length) return rows;
      const a = sorted[i];
      const b = sorted[j];
      const seqA = a.sequence;
      const seqB = b.sequence;
      return rows.map((r) => {
        if (r._key === a._key) return { ...r, sequence: seqB };
        if (r._key === b._key) return { ...r, sequence: seqA };
        return r;
      });
    });
  }

  const onCustomsBrokerChangeManual = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    setCustomsBrokerId(v === "" ? null : Number(v));
  };

  if (!isManual && (!idParam || !Number.isFinite(loadIdFromRoute))) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">Invalid load ID</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 p-4 text-[var(--trk-text-muted)]">
        <div
          className="h-9 w-9 animate-spin rounded-full border-2 border-[var(--trk-border)] border-t-[var(--trk-accent)]"
          aria-hidden
        />
        <p className="text-sm">Loading…</p>
      </div>
    );
  }

  if (workspaceMode === "manual" && error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">{error}</p>
        <Button variant="secondary" onClick={() => navigate(OPS.LOADS)} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );
  }

  if (workspaceMode !== "manual" && error) {
    return (
      <div className="p-4">
        <p className="text-sm text-red-600">{error}</p>
        <Button variant="secondary" onClick={() => navigate(OPS.LOADS)} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );
  }

  if (workspaceMode !== "manual" && !load) {
    return (
      <div className="p-4">
        <p className="text-sm text-[var(--trk-text-muted)]">Load not found</p>
        <Button variant="secondary" onClick={() => navigate(OPS.LOADS)} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );
  }

  const confirmed = Boolean(load?.document_snapshot_confirmed_at);
  const routeSubtitle = load ? formatRouteFromStops(load.stops) : "—";
  const hasActiveDispatchTrip = load?.active_dispatch_trip_id != null;

  const lidLabel = workspaceMode === "manual" ? "#NEW" : load ? `#${load.id}` : "#—";
  const headerTitle =
    workspaceMode === "manual"
      ? "New load"
      : `${loadNumber || load!.load_number || "Load"}${
          brokerNameSnapshot.trim() ? ` · ${brokerNameSnapshot.trim()}` : ""
        }`;
  const intakeQueueUrl = hasIntakeThread ? `${OPS.INTAKE}?thread=${intakeThreadId}` : OPS.INTAKE;
  const toolBtnSecondary =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-text-muted)] shadow-sm hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)]";

  /** Compare the server snapshot against the current form state; return human-readable diffs. */
  function getConflictDiffs(snap: Load): Array<{ label: string; server: string; yours: string }> {
    const form = buildLoadPersistPayload({
      status, loadNumber, brokerId, brokerContactId,
      brokerNameSnapshot, brokerContactNameSnapshot, brokerContactPhoneSnapshot,
      brokerContactExtensionSnapshot, brokerContactEmailSnapshot, brokerLoadReference,
      mode: freightMode, equipmentType, trailerType, trailerSize,
      commodity, estimatedWeight, hazmat, temperatureRequirement, palletCaseCount,
      rate, customerRate, miles,
      driverId, truckId, trailerId, customsBrokerId, internalNotes, draftStops,
    });
    const f = form as Record<string, unknown>;

    const fmt = (v: unknown, money = false): string => {
      if (v == null || v === "") return "—";
      return money ? `$${v}` : String(v);
    };

    const checks: Array<{ label: string; snapKey: keyof Load; formKey: string; money?: boolean }> = [
      { label: "Status",        snapKey: "status",                 formKey: "status" },
      { label: "Load #",        snapKey: "load_number",            formKey: "load_number" },
      { label: "Broker",        snapKey: "broker_name_snapshot",   formKey: "broker_name_snapshot" },
      { label: "Broker ref",    snapKey: "broker_load_reference",  formKey: "broker_load_reference" },
      { label: "Rate",          snapKey: "rate",                   formKey: "rate",          money: true },
      { label: "Customer rate", snapKey: "customer_rate",          formKey: "customer_rate", money: true },
      { label: "Miles",         snapKey: "miles",                  formKey: "miles" },
      { label: "Driver",        snapKey: "driver_id",              formKey: "driver_id" },
      { label: "Truck",         snapKey: "truck_id",               formKey: "truck_id" },
      { label: "Trailer",       snapKey: "trailer_id",             formKey: "trailer_id" },
      { label: "Equipment",     snapKey: "equipment_type",         formKey: "equipment_type" },
      { label: "Trailer type",  snapKey: "trailer_type",           formKey: "trailer_type" },
      { label: "Commodity",     snapKey: "commodity",              formKey: "commodity" },
      { label: "Est. weight",   snapKey: "estimated_weight",       formKey: "estimated_weight" },
    ];

    const diffs: Array<{ label: string; server: string; yours: string }> = [];
    for (const { label, snapKey, formKey, money } of checks) {
      const serverVal = snap[snapKey];
      const formVal = f[formKey];
      if (String(serverVal ?? "") !== String(formVal ?? "")) {
        diffs.push({ label, server: fmt(serverVal, money), yours: fmt(formVal, money) });
      }
    }
    return diffs;
  }

  return (
    <div className="flex min-h-screen flex-col bg-[var(--trk-bg)] text-[var(--trk-text)]">
      <header className="z-10 shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-3 px-4 py-2">
          <div className="flex min-w-0 flex-1 flex-wrap items-center gap-3">
            <button type="button" onClick={() => navigate(OPS.LOADS)} className={toolBtnSecondary}>
              ← Loads
            </button>
            <div className="min-w-0 flex-1">
              <div className="font-mono text-[11px] text-[var(--trk-text-muted)]">{lidLabel}</div>
              <h1 className="truncate text-[15px] font-semibold tracking-tight text-[var(--trk-text)]">{headerTitle}</h1>
              {workspaceMode === "detail" && load ? (
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-[var(--trk-text-muted)]">
                  {load.trip_number?.trim() ? (
                    <span>
                      Trip <span className="font-mono text-[var(--trk-text-muted)]">{load.trip_number.trim()}</span>
                    </span>
                  ) : (
                    <span className="italic">No trip number</span>
                  )}
                  <span>·</span>
                  <span>{hasActiveDispatchTrip ? "Dispatch linked" : "No dispatch trip"}</span>
                  {routeSubtitle !== "—" ? (
                    <>
                      <span>·</span>
                      <span className="max-w-[240px] truncate sm:max-w-md">{routeSubtitle}</span>
                    </>
                  ) : null}
                  {(load.created_at || load.updated_at) && (
                    <>
                      <span>·</span>
                      <span className="text-[10px] text-[var(--trk-text-muted)]">
                        {load.created_at ? `Created ${new Date(load.created_at).toLocaleString()}` : ""}
                        {load.created_at && load.updated_at ? " · " : ""}
                        {load.updated_at ? `Updated ${new Date(load.updated_at).toLocaleString()}` : ""}
                      </span>
                    </>
                  )}
                </div>
              ) : null}
              {workspaceMode === "manual" ? (
                <p className="mt-0.5 text-[11px] text-[var(--trk-text-muted)]">Create saves the load and opens it for edits.</p>
              ) : workspaceMode === "intake" ? (
                <p className="mt-0.5 text-[11px] text-[var(--trk-text-muted)]">Source rail + save updates this load.</p>
              ) : null}
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {workspaceMode !== "manual" && load ? <StatusBadge status={status} /> : null}
              {workspaceMode === "manual" ? (
                <span className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)]">
                  Manual
                </span>
              ) : null}
              {workspaceMode === "intake" ? (
                <span className="rounded border border-sky-200 bg-sky-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-sky-800">
                  Intake
                </span>
              ) : null}
              {workspaceMode === "detail" ? (
                <span className="rounded border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-emerald-800">
                  Detail
                </span>
              ) : null}
              {showDispatchAssignmentStrip ? (
                <span className="rounded border border-[var(--trk-heading)]/40 bg-[var(--trk-heading)]/15 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-heading)]">
                  Dispatch · Assign
                </span>
              ) : null}
            </div>
          </div>
          <WorkspaceModeReadout mode={workspaceMode} />
        </div>
        {serverConflict && workspaceMode !== "manual" ? (
          <div className="border-t border-amber-900/50 bg-amber-950/25 px-4 py-2.5">
            <div className="mx-auto flex max-w-[1600px] flex-wrap items-start justify-between gap-3">
              <div className="flex-1 space-y-1.5">
                <p className="text-xs text-amber-100/95">
                  <span className="font-semibold">Conflict:</span> Load was modified elsewhere
                  {serverConflict.serverVersion != null ? (
                    <span className="text-amber-200/85"> (server version {serverConflict.serverVersion})</span>
                  ) : null}.{" "}
                  Your open edits were not overwritten. Reload to align with the server, or dismiss to keep editing (a save
                  may return 409 until you reload).
                </p>
                {serverConflict.serverSnapshot ? (() => {
                  const diffs = getConflictDiffs(serverConflict.serverSnapshot);
                  return diffs.length > 0 ? (
                    <ul className="space-y-0.5">
                      {diffs.map((d) => (
                        <li key={d.label} className="text-[11px] text-amber-200/80">
                          Server has: {d.label}={d.server}, your version: {d.label}={d.yours}
                        </li>
                      ))}
                    </ul>
                  ) : null;
                })() : null}
              </div>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button type="button" variant="secondary" onClick={() => setServerConflict(null)}>
                  Dismiss
                </Button>
                <Button type="button" onClick={() => void onReloadServerVersion()}>
                  Reload server version
                </Button>
              </div>
            </div>
          </div>
        ) : null}
      </header>

      {showDispatchAssignmentStrip ? (
        <DispatchAssignmentStrip
          drivers={drivers}
          trucks={trucks}
          trailers={trailers}
          driverId={driverId}
          truckId={truckId}
          trailerId={trailerId}
          onDriverSelect={onDispatchStripDriverSelect}
          onTruckSelect={onDispatchStripTruckSelect}
          onTrailerSelect={onDispatchStripTrailerSelect}
          onAssign={() => void onDispatchAssign()}
          saving={saving}
        />
      ) : null}

      <div className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-2 px-4 py-2">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Workspace</span>
          <button type="button" className={toolBtnSecondary} onClick={() => navigate(OPS.LOADS)}>
            Load directory
          </button>
          <button type="button" className={toolBtnSecondary} onClick={() => navigate(OPS.DISPATCH)}>
            Dispatch
          </button>
          {workspaceMode === "intake" ? (
            <button type="button" className={toolBtnSecondary} onClick={() => navigate(intakeQueueUrl)}>
              Intake queue
            </button>
          ) : null}
          <span className="mx-1 hidden h-5 w-px bg-[var(--trk-border)] sm:inline-block" aria-hidden />
          <span className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Actions</span>
          <input
            ref={pdfInputRef}
            type="file"
            accept="application/pdf,.pdf"
            className="hidden"
            aria-hidden
            onChange={(e) => {
              const f = e.target.files?.[0];
              e.target.value = "";
              if (f) void onParseWorkspacePdf(f);
            }}
          />
          {canWorkspaceParsePdf ? (
            <Button
              variant="secondary"
              type="button"
              disabled={saving || parseBusy || loading}
              onClick={() => pdfInputRef.current?.click()}
            >
              {parseBusy ? "Parsing…" : "Upload & parse PDF"}
            </Button>
          ) : null}
          {workspaceMode === "manual" ? (
            <Button variant="primary" type="button" disabled={saving} onClick={() => void onCreate()}>
              {saving ? "Creating…" : "Create load"}
            </Button>
          ) : (
            <Button variant="primary" type="button" disabled={saving} onClick={() => void onSave()}>
              {saving ? "Saving…" : "Save load"}
            </Button>
          )}
          {toolbarMessage ? (
            <span
              className={clsx(
                "ml-auto max-w-full text-[11px] sm:max-w-md",
                workspaceToolbarToneClassName(toolbarMessage.tone),
              )}
            >
              {toolbarMessage.text}
            </span>
          ) : null}
        </div>
        {parseWarnings.length > 0 ? (
          <div className="mx-auto max-w-[1600px] border-t border-[var(--trk-border)] px-4 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-amber-600 dark:text-amber-200/90">
              Parse notes
            </div>
            <ul className="mt-1 max-h-32 list-disc space-y-0.5 overflow-y-auto pl-4 text-[11px] leading-snug text-[var(--trk-text)]">
              {parseWarnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {lastParseAppliedLabels && lastParseAppliedLabels.length > 0 ? (
          <div className="mx-auto max-w-[1600px] border-t border-[var(--trk-border)] px-4 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
              Parsed fields applied
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {lastParseAppliedLabels.map((label, i) => (
                <span
                  key={`${i}-${label}`}
                  className="rounded border border-[var(--trk-border)] bg-[var(--trk-bg)] px-2 py-0.5 font-mono text-[10px] text-[var(--trk-text-muted)]"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="mx-auto flex min-h-0 w-full max-w-[1600px] flex-1 flex-col overflow-hidden lg:flex-row">
        <aside className="flex max-h-[38vh] min-h-0 shrink-0 flex-col border-b border-[var(--trk-border)] bg-[var(--trk-surface)] lg:max-h-none lg:w-[320px] lg:border-b-0 lg:border-r lg:border-[var(--trk-border)]">
          {workspaceMode === "intake" && hasIntakeThread ? (
            <IntakeEmailRail
              threadId={intakeThreadId}
              loading={intakeLoading}
              error={intakeError}
              messages={intakeMessages}
            />
          ) : (
            <ReferenceTextRail
              title={workspaceMode === "manual" ? "Rate confirmation" : "Source document"}
              hint={
                workspaceMode === "manual" ? (
                  <>
                    Mirrors <code className="rounded bg-[var(--trk-border)] px-1 text-[10px]">internal_notes</code> from the form.
                    Tab fields to highlight lines.
                  </>
                ) : (
                  <>
                    Text from <code className="rounded bg-[var(--trk-border)] px-1 text-[10px]">internal_notes</code>. Edit under
                    Notes in the form.
                  </>
                )
              }
              docLines={docLines}
              docScrollRef={docScrollRef}
              docLineRefs={docLineRefs}
              activeDocLine={activeDocLine}
            />
          )}
        </aside>

        <main className="min-h-0 flex-1 overflow-y-auto bg-[var(--trk-bg)] p-3 lg:p-4">
          {workspaceMode !== "manual" && load?.review_required ? (
            <div className="mb-3 flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-500" aria-hidden />
              <p className="text-[11px] leading-snug text-amber-300">
                Review required — verify intake / broker match before relying on this load.
              </p>
            </div>
          ) : null}

          {workspaceMode !== "manual" && load ? (
            <details className="mb-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] shadow-sm">
              <summary className="cursor-pointer list-none px-3 py-2 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)] marker:content-none [&::-webkit-details-marker]:hidden">
                System context · trip, match, resolved labels
              </summary>
              <div className="border-t border-[var(--trk-border)] px-3 py-3 text-xs">
                <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <ContextRow label="Trip number" value={load.trip_number?.trim() || "—"} mono />
                  <ContextRow label="Dispatch trip" value={hasActiveDispatchTrip ? "Linked" : "—"} />
                  <ContextRow label="Match method" value={load.broker_match_method?.replace(/_/g, " ") || "—"} />
                  <ContextRow label="Confidence tier" value={load.broker_match_confidence_tier || "—"} />
                </dl>
                {load.broker_match_explanation?.trim() ? (
                  <p className="mt-3 whitespace-pre-wrap text-xs text-[var(--trk-text-muted)]">{load.broker_match_explanation.trim()}</p>
                ) : null}
                {load.is_duplicate_of_load_id != null ? (
                  <p className="mt-3 text-xs">
                    <span className="text-[var(--trk-text-muted)]">Possible duplicate — </span>
                    <Link
                      to={OPS.LOAD_DETAIL(load.is_duplicate_of_load_id)}
                      className="font-medium text-indigo-600 hover:underline"
                    >
                      Open linked load
                    </Link>
                  </p>
                ) : null}
                <div className="mt-4 border-t border-[var(--trk-border)] pt-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Resolved labels</p>
                  <dl className="grid grid-cols-1 gap-2 sm:grid-cols-2 text-sm">
                    <ContextRow label="Broker" value={load.broker?.name || "—"} />
                    <ContextRow label="Broker contact" value={load.broker_contact?.name || "—"} />
                    <ContextRow
                      label="Driver"
                      value={load.driver ? `${load.driver.first_name} ${load.driver.last_name}`.trim() : "—"}
                    />
                    <ContextRow label="Truck" value={load.truck ? load.truck.unit_number : "—"} />
                    <ContextRow
                      label="Trailer"
                      value={
                        load.trailer
                          ? [load.trailer.unit_number, load.trailer.trailer_type].filter(Boolean).join(" · ")
                          : "—"
                      }
                    />
                    <ContextRow label="Customs broker" value={load.customs_broker?.legal_name || "—"} />
                  </dl>
                </div>
                {contextStops.length > 0 ? (
                  <div className="mt-4 border-t border-[var(--trk-border)] pt-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">
                      Stop schedules (read-only)
                    </p>
                    <ul className="space-y-1 text-xs text-[var(--trk-text-muted)]">
                      {contextStops.map((s, i) => (
                        <li key={s.id || `ctx-${i}`}>
                          Stop {(s.sequence ?? i) + 1}
                          {s.scheduled_at
                            ? ` — ${new Date(s.scheduled_at).toLocaleString(undefined, {
                                dateStyle: "short",
                                timeStyle: "short",
                              })}`
                            : " — —"}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {(load.document_snapshot_confirmed_at || load.customs_snapshot) && (
                  <div className="mt-4 border-t border-[var(--trk-border)] pt-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-[var(--trk-text-muted)]">Customs snapshot</p>
                    <dl className="space-y-1 text-xs">
                      <ContextRow
                        label="Confirmed at"
                        value={
                          load.document_snapshot_confirmed_at
                            ? new Date(load.document_snapshot_confirmed_at).toLocaleString()
                            : "—"
                        }
                      />
                      <ContextRow label="Snapshot version" value={String(load.document_snapshot_version ?? 0)} />
                    </dl>
                    {load.customs_snapshot && (
                      <ul className="mt-2 space-y-0.5 text-xs text-[var(--trk-text-muted)]">
                        <li>{load.customs_snapshot.legal_name_snapshot || "—"}</li>
                        <li>{load.customs_snapshot.phone_primary_snapshot || ""}</li>
                        <li>{load.customs_snapshot.generic_email_snapshot || ""}</li>
                      </ul>
                    )}
                  </div>
                )}
              </div>
              {contextSummary ? (
                <p className="mt-2 border-t border-[var(--trk-border)] pt-2 text-[11px] text-amber-400/85">{contextSummary}</p>
              ) : null}
            </details>
          ) : null}

          <LoadWorkspaceForm
            mode={workspaceMode}
            visibleSections={sectionConfig.visible}
            editableSections={sectionConfig.editable}
            intakeProposed={intakeProposed}
            saving={saving}
            freightBrokers={freightBrokers}
            brokerContacts={brokerContacts}
            drivers={drivers}
            trucks={trucks}
            trailers={trailers}
            customsBrokers={customsBrokers}
            customsMessage={workspaceMode === "manual" ? null : customsMessage}
            customsBrokerLocked={workspaceMode === "manual" ? false : confirmed}
            onCustomsBrokerChange={
              workspaceMode === "manual"
                ? onCustomsBrokerChangeManual
                : (e) => void onCustomsBrokerSelect(e)
            }
            onConfirmSnapshot={workspaceMode === "manual" ? undefined : onConfirmSnapshot}
            showOperationalNotesTimeline={workspaceMode !== "manual"}
            loadNotes={workspaceMode === "manual" ? [] : loadNotes}
            newNoteBody={workspaceMode === "manual" ? "" : newNoteBody}
            setNewNoteBody={workspaceMode === "manual" ? () => {} : setNewNoteBody}
            onAddNote={workspaceMode === "manual" ? () => {} : () => void onAddNote()}
            focusDoc={focusDoc}
            verificationTabIndex={verificationTabIndex}
            status={status}
            setStatus={setStatus}
            loadNumber={loadNumber}
            setLoadNumber={setLoadNumber}
            brokerId={brokerId}
            setBrokerId={setBrokerId}
            brokerContactId={brokerContactId}
            setBrokerContactId={setBrokerContactId}
            brokerNameSnapshot={brokerNameSnapshot}
            setBrokerNameSnapshot={setBrokerNameSnapshot}
            brokerContactNameSnapshot={brokerContactNameSnapshot}
            setBrokerContactNameSnapshot={setBrokerContactNameSnapshot}
            brokerContactPhoneSnapshot={brokerContactPhoneSnapshot}
            setBrokerContactPhoneSnapshot={setBrokerContactPhoneSnapshot}
            brokerContactExtensionSnapshot={brokerContactExtensionSnapshot}
            setBrokerContactExtensionSnapshot={setBrokerContactExtensionSnapshot}
            brokerContactEmailSnapshot={brokerContactEmailSnapshot}
            setBrokerContactEmailSnapshot={setBrokerContactEmailSnapshot}
            brokerLoadReference={brokerLoadReference}
            setBrokerLoadReference={setBrokerLoadReference}
            freightMode={freightMode}
            setFreightMode={setFreightMode}
            equipmentType={equipmentType}
            setEquipmentType={setEquipmentType}
            trailerType={trailerType}
            setTrailerType={setTrailerType}
            trailerSize={trailerSize}
            setTrailerSize={setTrailerSize}
            commodity={commodity}
            setCommodity={setCommodity}
            estimatedWeight={estimatedWeight}
            setEstimatedWeight={setEstimatedWeight}
            hazmat={hazmat}
            setHazmat={setHazmat}
            temperatureRequirement={temperatureRequirement}
            setTemperatureRequirement={setTemperatureRequirement}
            palletCaseCount={palletCaseCount}
            setPalletCaseCount={setPalletCaseCount}
            rate={rate}
            setRate={setRate}
            customerRate={customerRate}
            setCustomerRate={setCustomerRate}
            miles={miles}
            setMiles={setMiles}
            driverId={driverId}
            setDriverId={setDriverId}
            truckId={truckId}
            setTruckId={setTruckId}
            trailerAssetId={trailerId}
            setTrailerAssetId={setTrailerId}
            customsBrokerId={customsBrokerId}
            internalNotes={internalNotes}
            setInternalNotes={setInternalNotes}
            draftStops={draftStops}
            sortedDraftStops={sortedDraftStops}
            updateStop={updateStop}
            removeStop={removeStop}
            addStop={addStop}
            moveStop={moveStop}
          />

          {/* Settlement — visible in payroll and audit modes */}
          {sectionConfig.visible.includes("Settlement") && load ? (
            <SectionSettlement load={load} />
          ) : null}

          {/* AuditTimeline — visible in audit mode */}
          {sectionConfig.visible.includes("AuditTimeline") ? (
            <section className="mt-2.5 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] shadow-sm overflow-hidden">
              <div className="flex items-center justify-between gap-2 border-b border-[var(--trk-border)] bg-[var(--trk-surface)] px-3.5 py-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--trk-text-muted)]">Audit timeline</span>
              </div>
              <LoadAuditTimeline loadId={load?.id ?? null} />
            </section>
          ) : null}
        </main>
      </div>
    </div>
  );
}

function formatAuditValue(v: unknown): string {
  if (v === null) return "null";
  if (v === undefined) return "—";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try {
    return JSON.stringify(v);
  } catch {
    return String(v);
  }
}

function loadAuditActionLabel(action: string): string {
  switch (action) {
    case "load_created":
      return "Load created";
    case "load_updated":
      return "Load updated";
    case "load_status_changed":
      return "Status changed";
    case "load_assigned":
      return "Driver assignment changed";
    case "load_dispatched":
      return "Load dispatched";
    case "document_snapshot_confirmed":
      return "Document snapshot confirmed";
    case "customs_broker_changed":
      return "Customs broker changed";
    case "note_added":
      return "Note added";
    default:
      return action;
  }
}

function LoadAuditTimeline({ loadId }: { loadId: number | null }) {
  const [rows, setRows] = useState<AuditEventRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const fetchRows = useCallback(async () => {
    if (!loadId) return;
    try {
      setErr(null);
      const r = await listAuditEventsByEntity("load", String(loadId), { limit: 100 });
      setRows(r);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed to load audit");
      setRows([]);
    }
  }, [loadId]);

  useEffect(() => {
    void fetchRows();
  }, [fetchRows]);

  if (!loadId) {
    return <div className="px-3.5 py-6 text-center text-xs text-[var(--trk-text-muted)]">Select a load to view audit history.</div>;
  }
  if (err) {
    return <div className="px-3.5 py-6 text-center text-xs text-[var(--trk-danger)]">{err}</div>;
  }
  if (rows === null) {
    return <div className="px-3.5 py-6 text-center text-xs text-[var(--trk-text-muted)]">Loading…</div>;
  }
  if (rows.length === 0) {
    return <div className="px-3.5 py-6 text-center text-xs text-[var(--trk-text-muted)]">No audit events.</div>;
  }

  return (
    <div className="px-3.5 py-2">
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.id} className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
            <div className="flex items-baseline justify-between gap-2">
              <div className="text-xs text-[var(--trk-text)]">
                <span className="font-semibold">{loadAuditActionLabel(r.action)}</span>
                <span className="ml-2 text-[11px] text-[var(--trk-text-muted)]">{r.source}</span>
                {r.visibility && r.visibility !== "normal" ? (
                  <span className="ml-2 text-[11px] text-[var(--trk-text-muted)]">{r.visibility}</span>
                ) : null}
              </div>
              <div className="text-[11px] text-[var(--trk-text-muted)]">{new Date(r.event_at).toLocaleString()}</div>
            </div>

            {r.changed_fields && Object.keys(r.changed_fields).length > 0 ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-[11px] text-[var(--trk-text-muted)]">Show changes</summary>
                <div className="mt-2 space-y-1 text-[11px] text-[var(--trk-text-muted)]">
                  {Object.entries(r.changed_fields).map(([k, v]) => (
                    <div key={k}>
                      <span className="text-[var(--trk-text)]">{k}</span>:{" "}
                      {(v as any)?.redacted ? (
                        <span className="text-[var(--trk-danger)]">redacted</span>
                      ) : (
                        <>
                          {formatAuditValue((v as any)?.before)} → {formatAuditValue((v as any)?.after)}
                        </>
                      )}
                    </div>
                  ))}
                </div>
              </details>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
