/**
 * Single load workspace route — manual create, saved load edit, or intake verify/edit.
 * Field UI is only in LoadWorkspaceForm; this page owns layout, data, save, and side panel.
 * Slice 15A: commercial / readiness / save live here; movement assignment (driver/truck/trailer) on Trip workspace.
 */
import { useCallback, useEffect, useMemo, useRef, useState, type MutableRefObject, type ReactNode, type RefObject } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import clsx from "clsx";
import Button from "@/components/Button";
import OperatorLoadStatusChip from "@/components/OperatorLoadStatusChip";
import FollowUpDispatchDialog from "@/components/FollowUpDispatchDialog";
import {
  addLoadNote,
  confirmLoadDocumentSnapshot,
  createPlannedTrip,
  createTripForLoadAssignment,
  createLoadWorkspaceDraft,
  getDriverAssignmentHints,
  getTruckAssignmentHints,
  discardLoadWorkspaceDraft,
  fetchLoadRateConfirmationPdfObjectUrl,
  fetchLoadWorkspaceDraftRateConfirmationPdfObjectUrl,
  getLoadWorkspaceDraft,
  parseLoadWorkspaceDraftDocument,
  duplicateLoadCandidatesFromParse,
  type DuplicateLoadCandidate,
  promoteLoadWorkspaceDraft,
  parseLoadWorkspaceDraftVersionConflict,
  updateLoadWorkspaceDraft,
  type LoadWorkspaceDraft,
  getEmailThread,
  getEmailThreadMessages,
  getLoad,
  getLoadNotes,
  listBrokers,
  listBrokerContacts,
  listCustomsBrokers,
  listDrivers,
  listTrailers,
  listTrucks,
  listAuditEventsByEntity,
  cancelLoad,
  markLoadReady,
  parseLoadVersionConflict,
  parseLoadWorkspaceDocument,
  updateLoad,
  type Broker,
  type BrokerContact,
  type CustomsBroker,
  type Driver,
  type InboxMessageItem,
  type InboxThreadListItem,
  type Load,
  type LoadDocumentParseReference,
  type LoadNote,
  type AuditEventRow,
  type Trailer,
  type Truck,
} from "@/api";
import { useOperationalRefresh } from "@/core/concurrency/useOperationalRefresh";
import { loadWorkspaceRemountKey, OPS } from "@/routes";
import { sortedStops as sortStops } from "@/utils/loadStops";
import { LoadWorkspaceForm, LoadWorkspaceNotesPanel } from "@/loadWorkspace/LoadWorkspaceForm";
import {
  RateConfirmationPdfPanel,
  draftRateConfirmationPdfDownloadPath,
  loadRateConfirmationPdfDownloadPath,
} from "@/loadWorkspace/RateConfirmationPdfPanel";
import {
  baselineSignatureFromLoad,
  buildLoadPersistPayload,
  buildWorkspaceDraftJson,
  workspaceFieldsFromDraftJson,
  type WorkspaceDraftFields,
  buildVerificationTabIndexMap,
  findBestDocLineIndex,
  type DocFocusOpts,
  type LoadPersistParams,
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
import { buildParseEngineAttribution } from "@/loadWorkspace/loadParseEngineAttribution";
import { hydrateLoadWorkspaceFromParseResponse } from "@/loadWorkspace/loadParseHydration";
import {
  draftHasReadyRateConfirmationPdf,
  loadDocumentParseFromAcceptedJson,
  workspacePdfHydrationUxFromDraft,
  workspaceReferenceTextFromDraft,
} from "@/loadWorkspace/workspaceDraftPdfRestore";
import {
  applyEmptyWorkspaceFieldsFromParseResponse,
  persistWorkspaceDraftAfterParse,
  type ApplyLoadDocumentParseCallbacks,
} from "@/loadWorkspace/applyLoadDocumentParseResponse";
import {
  commercialGatePrimaryActionLabel,
  listCreateLoadHardMissing,
  draftHasParsedPdf,
  formatManualHardMissingLine,
  formatSoftNotProvidedLine,
  listCreateLoadSoftNotProvided,
  listManualCreateHardMissing,
  type WorkspaceCommercialGateOutcome,
  resolveWorkspaceCommercialGatePrompt,
} from "@/loadWorkspace/workspaceCreateLoadValidation";
import {
  createEmptyParseHydrationState,
  registerManualParseFieldEdit,
  type ParseHydrationState,
  type ParseScalarFieldKey,
} from "@/loadWorkspace/loadParseHydrationState";
import { validateDraftStopsClassifiedForSave } from "@/loadWorkspace/loadStopClassification";
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
    <div className="flex min-h-0 max-h-[200px] flex-col bg-[var(--trk-surface)]">
      <div className="shrink-0 border-b border-[var(--trk-border)] px-3 py-2">
        <span className={wsSectionTitle}>{title}</span>
        <p className="mt-1 text-[11px] leading-snug text-[var(--trk-text-muted)]">{hint}</p>
      </div>
      <div ref={docScrollRef} className="min-h-0 flex-1 overflow-y-auto p-3">
        {docLines.length ? (
          <div
            className="rounded-md border border-[var(--trk-border)] bg-[var(--trk-bg)] p-2 font-mono text-[11px] leading-snug text-[var(--trk-text)]"
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
          <p className="rounded-md border border-dashed border-[var(--trk-border)] bg-[var(--trk-bg)]/50 px-3 py-6 text-center text-xs text-[var(--trk-text-muted)]">
            Nothing to show yet — add text in Notes below.
          </p>
        )}
      </div>
    </div>
  );
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

function formatPlannedTripCreateError(err: unknown): string {
  if (!(err instanceof Error)) return "Could not create trip. Try again.";
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const detail = parsed.detail;
    if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
      const code = (detail as { code?: string }).code;
      const msg =
        typeof (detail as { detail?: unknown }).detail === "string"
          ? (detail as { detail: string }).detail
          : null;
      switch (code) {
        case "TRIP_NUMBER_PREFIX_NOT_CONFIGURED":
          return `${msg ?? "Trip number prefix is not configured."} Set it under Admin → Dispatch numbering.`;
        case "LOAD_ACTIVE_ON_OTHER_TRIP":
          return msg ?? "This load is already on another trip. Remove it there or open that trip.";
        case "DUPLICATE_TRIP_LOAD_MEMBERSHIP":
          return msg ?? "This load is already on this trip.";
        default:
          if (msg) return msg;
          break;
      }
    }
    if (typeof detail === "string") return detail;
  } catch {
    /* use raw message */
  }
  if (raw.length > 0 && raw.length < 400) return raw;
  return "Could not create trip. Try again.";
}

/** Human-readable message from FastAPI-style JSON error body in Error.message. */
function workspaceDraftClosedMessage(status: string): string {
  switch (status) {
    case "discarded":
      return "This draft was discarded.";
    case "expired":
      return "This draft has expired.";
    case "promoted":
      return "This draft was already promoted to a load.";
    default:
      return "This draft is no longer editable.";
  }
}

function formatApiErrorMessage(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  const raw = err.message?.trim() || "";
  try {
    const parsed = JSON.parse(raw) as { detail?: unknown };
    const d = parsed.detail;
    if (typeof d === "string") return d;
    if (d && typeof d === "object" && !Array.isArray(d) && typeof (d as { detail?: unknown }).detail === "string") {
      return (d as { detail: string }).detail;
    }
  } catch {
    /* use raw */
  }
  if (raw.length > 0 && raw.length < 500) return raw;
  return fallback;
}

function LoadWorkspacePage() {
  const location = useLocation();
  const navigate = useNavigate();
  const { id: idParam, draftId: draftIdParam } = useParams<{ id?: string; draftId?: string }>();
  const [searchParams] = useSearchParams();

  const draftIdFromRoute = draftIdParam ?? null;
  const isDraftWorkspace = draftIdFromRoute != null;
  const isManualCreate =
    location.pathname === OPS.LOAD_NEW || location.pathname.endsWith("/loads/new");
  const isManual = isManualCreate || isDraftWorkspace;
  const intakeThreadRaw = searchParams.get(OPS.LOAD_INTAKE_THREAD_QUERY);
  const intakeThreadId =
    intakeThreadRaw != null && intakeThreadRaw !== "" ? Number(intakeThreadRaw) : Number.NaN;
  const hasIntakeThread = Number.isFinite(intakeThreadId) && intakeThreadId > 0;

  const loadIdFromRoute =
    !isManualCreate && !isDraftWorkspace && idParam ? Number(idParam) : Number.NaN;
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

  const [customsBrokers, setCustomsBrokers] = useState<CustomsBroker[]>([]);
  const [freightBrokers, setFreightBrokers] = useState<Broker[]>([]);
  const [brokerContacts, setBrokerContacts] = useState<BrokerContact[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);
  const [load, setLoad] = useState<Load | null>(null);

  const [loadNotes, setLoadNotes] = useState<LoadNote[]>([]);
  const [newNoteBody, setNewNoteBody] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [markReadyBusy, setMarkReadyBusy] = useState(false);
  const [cancelLoadBusy, setCancelLoadBusy] = useState(false);
  const [createPlannedTripBusy, setCreatePlannedTripBusy] = useState(false);
  const [createPlannedTripError, setCreatePlannedTripError] = useState<string | null>(null);
  const [followUpDispatchOpen, setFollowUpDispatchOpen] = useState(false);
  const commercialGateResolverRef = useRef<((outcome: WorkspaceCommercialGateOutcome) => void) | null>(
    null,
  );
  const [commercialGatePrompt, setCommercialGatePrompt] = useState<{
    message: string;
    mode: "create" | "save";
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toolbarMessage, setToolbarMessage] = useState<WorkspaceToolbarMessage | null>(null);
  const [customsMessage, setCustomsMessage] = useState<string | null>(null);
  const [serverConflict, setServerConflict] = useState<{
    serverVersion: number | null;
    serverSnapshot: Load | null;
  } | null>(null);
  const [workspaceDraft, setWorkspaceDraft] = useState<LoadWorkspaceDraft | null>(null);
  const isLocalNewDraft = isManualCreate && !draftIdFromRoute;
  const isDraftEditable =
    isLocalNewDraft || (isDraftWorkspace && workspaceDraft?.status === "draft");
  const showManualDraftActions = workspaceMode === "manual" && (isDraftWorkspace || isManualCreate);
  const [draftConflict, setDraftConflict] = useState<{ serverVersion: number | null } | null>(null);
  const [baselineFormSignature, setBaselineFormSignature] = useState<string | null>(null);

  const onAssignmentDriverChange = useCallback(async (id: number | null) => {
    if (!id) {
      setTruckId(null);
      setTrailerId(null);
      setAssignmentWarnings([]);
      return;
    }
    try {
      const hints = await getDriverAssignmentHints(id);
      setAssignmentWarnings(hints.warnings ?? []);
      setTruckId(hints.truck_id ?? null);
      setTrailerId(hints.trailer_id ?? null);
    } catch {
      setAssignmentWarnings([]);
    }
  }, []);

  const onAssignmentTruckChange = useCallback(async (id: number | null) => {
    if (!id) {
      setTrailerId(null);
      setAssignmentWarnings([]);
      return;
    }
    try {
      const hints = await getTruckAssignmentHints(id);
      setAssignmentWarnings(hints.warnings ?? []);
      if (hints.driver_id != null) setDriverId(hints.driver_id);
      setTrailerId(hints.trailer_id ?? null);
    } catch {
      setAssignmentWarnings([]);
    }
  }, []);

  const onCreatePlannedTrip = useCallback(async () => {
    if (
      !load ||
      load.active_trip_id != null ||
      load.open_planned_trip_id != null ||
      load.open_future_movement_plan_id != null
    )
      return;
    const lid = load.id;
    setCreatePlannedTripBusy(true);
    setCreatePlannedTripError(null);
    try {
      const created = await createPlannedTrip({
        status: "planned",
        job_type: "freight_load",
        load_ids: [lid],
      });
      navigate(OPS.TRIP_DETAIL(created.id));
    } catch (e) {
      setCreatePlannedTripError(formatPlannedTripCreateError(e));
    } finally {
      setCreatePlannedTripBusy(false);
    }
  }, [load, navigate]);

  const [intakeMessages, setIntakeMessages] = useState<InboxMessageItem[]>([]);
  const [intakeThread, setIntakeThread] = useState<InboxThreadListItem | null>(null);
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [intakeError, setIntakeError] = useState<string | null>(null);

  const [draftStops, setDraftStops] = useState<DraftStop[]>(() =>
    isManual ? initialManualCreateStops() : [],
  );

  const [status, setStatus] = useState(isManual ? "draft" : "");
  const [loadNumber, setLoadNumber] = useState("");
  const [brokerId, setBrokerId] = useState<number | null>(null);
  const [brokerContactId, setBrokerContactId] = useState<number | null>(null);
  const [brokerNameSnapshot, setBrokerNameSnapshot] = useState("");
  const [brokerContactNameSnapshot, setBrokerContactNameSnapshot] = useState("");
  const [brokerContactPhoneSnapshot, setBrokerContactPhoneSnapshot] = useState("");
  const [brokerContactExtensionSnapshot, setBrokerContactExtensionSnapshot] = useState("");
  const [brokerContactEmailSnapshot, setBrokerContactEmailSnapshot] = useState("");
  const [brokerLoadReference, setBrokerLoadReference] = useState("");
  const [loadReferences, setLoadReferences] = useState<LoadDocumentParseReference[]>([]);
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
  const [assignmentWarnings, setAssignmentWarnings] = useState<string[]>([]);
  const [customsBrokerId, setCustomsBrokerId] = useState<number | null>(null);
  const [internalNotes, setInternalNotes] = useState("");
  const [parseBusy, setParseBusy] = useState(false);
  const [parseElapsedSec, setParseElapsedSec] = useState(0);
  const [parseWarnings, setParseWarnings] = useState<string[]>([]);
  const [duplicateReview, setDuplicateReview] = useState<{
    file: File;
    candidates: DuplicateLoadCandidate[];
  } | null>(null);
  /** Labels for field groups applied by the latest successful PDF parse (read-only summary). */
  const [lastParseAppliedLabels, setLastParseAppliedLabels] = useState<string[] | null>(null);
  const [lastParseEngineAttribution, setLastParseEngineAttribution] = useState<string | null>(null);
  const [workspaceReferenceText, setWorkspaceReferenceText] = useState("");
  const [workspacePdfPreviewUrl, setWorkspacePdfPreviewUrl] = useState<string | null>(null);
  const parseHydrationRef = useRef<ParseHydrationState>(createEmptyParseHydrationState());
  const pdfInputRef = useRef<HTMLInputElement | null>(null);
  const docScrollRef = useRef<HTMLDivElement | null>(null);
  const docLineRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());
  const [activeDocLine, setActiveDocLine] = useState<number | null>(null);
  const loadConcurrencyRef = useRef<number | null>(null);
  const formDirtyRef = useRef(false);

  useEffect(() => {
    loadConcurrencyRef.current = load?.concurrency_version ?? null;
  }, [load?.concurrency_version]);

  useEffect(() => {
    if (!parseBusy) {
      setParseElapsedSec(0);
      return;
    }
    const started = Date.now();
    setParseElapsedSec(0);
    const id = window.setInterval(() => {
      setParseElapsedSec(Math.max(0, Math.floor((Date.now() - started) / 1000)));
    }, 1000);
    return () => window.clearInterval(id);
  }, [parseBusy]);

  useEffect(() => {
    setCreatePlannedTripError(null);
  }, [load?.id]);

  const docLines = useMemo(() => {
    const raw = workspaceReferenceText.trim() ? workspaceReferenceText : internalNotes || "";
    if (!raw.trim()) return [];
    return raw.split(/\r?\n/);
  }, [workspaceReferenceText, internalNotes]);

  const replaceWorkspacePdfPreviewUrl = useCallback((next: string | null) => {
    setWorkspacePdfPreviewUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return next;
    });
  }, []);

  const rateConPdfOpenInNewTabPath = useMemo(() => {
    if (workspaceMode === "detail" && load?.id) {
      return loadRateConfirmationPdfDownloadPath(load.id);
    }
    if (isDraftWorkspace && draftIdFromRoute) {
      return draftRateConfirmationPdfDownloadPath(draftIdFromRoute);
    }
    return null;
  }, [workspaceMode, load?.id, isDraftWorkspace, draftIdFromRoute]);

  useEffect(() => {
    return () => {
      if (workspacePdfPreviewUrl) URL.revokeObjectURL(workspacePdfPreviewUrl);
    };
  }, [workspacePdfPreviewUrl]);

  useEffect(() => {
    if (workspaceMode !== "detail" || !Number.isFinite(loadIdFromRoute)) {
      return;
    }
    let cancelled = false;
    void fetchLoadRateConfirmationPdfObjectUrl(loadIdFromRoute).then((url) => {
      if (!cancelled) replaceWorkspacePdfPreviewUrl(url);
    });
    return () => {
      cancelled = true;
    };
  }, [workspaceMode, loadIdFromRoute, replaceWorkspacePdfPreviewUrl]);

  const restoreDraftPdfArtifacts = useCallback(
    async (draft: LoadWorkspaceDraft) => {
      setWorkspaceReferenceText(workspaceReferenceTextFromDraft(draft));
      const ux = workspacePdfHydrationUxFromDraft(draft);
      setParseWarnings(ux.warnings);
      setLastParseAppliedLabels(ux.appliedLabels);
      if (draftHasReadyRateConfirmationPdf(draft)) {
        const url = await fetchLoadWorkspaceDraftRateConfirmationPdfObjectUrl(draft.id);
        replaceWorkspacePdfPreviewUrl(url);
      } else {
        replaceWorkspacePdfPreviewUrl(null);
      }
    },
    [replaceWorkspacePdfPreviewUrl],
  );

  const focusDoc = useCallback(
    (opts: DocFocusOpts) => {
      const bestIdx = findBestDocLineIndex(docLines, opts);
      if (bestIdx < 0) return;
      setActiveDocLine(bestIdx);
      requestAnimationFrame(() => {
        const lineEl = docLineRefs.current.get(bestIdx);
        const scrollEl = docScrollRef.current;
        if (!lineEl) return;
        if (scrollEl) {
          const lineRect = lineEl.getBoundingClientRect();
          const scrollRect = scrollEl.getBoundingClientRect();
          const lineHeight = lineRect.height;
          const viewHeight = scrollEl.clientHeight;
          const relativeTop = lineRect.top - scrollRect.top + scrollEl.scrollTop;
          scrollEl.scrollTo({
            top: Math.max(0, relativeTop - viewHeight / 2 + lineHeight / 2),
            behavior: "smooth",
          });
        } else {
          lineEl.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      });
    },
    [docLines],
  );

  const hydrateFromWorkspaceFields = useCallback((fields: WorkspaceDraftFields) => {
    setStatus(fields.status);
    setLoadNumber(fields.loadNumber);
    setBrokerId(fields.brokerId);
    setBrokerContactId(fields.brokerContactId);
    setBrokerNameSnapshot(fields.brokerNameSnapshot);
    setBrokerContactNameSnapshot(fields.brokerContactNameSnapshot);
    setBrokerContactPhoneSnapshot(fields.brokerContactPhoneSnapshot);
    setBrokerContactExtensionSnapshot(fields.brokerContactExtensionSnapshot);
    setBrokerContactEmailSnapshot(fields.brokerContactEmailSnapshot);
    setBrokerLoadReference(fields.brokerLoadReference);
    setLoadReferences(fields.loadReferences);
    setFreightMode(fields.freightMode);
    setEquipmentType(fields.equipmentType);
    setTrailerType(fields.trailerType);
    setTrailerSize(fields.trailerSize);
    setCommodity(fields.commodity);
    setEstimatedWeight(fields.estimatedWeight);
    setHazmat(fields.hazmat);
    setTemperatureRequirement(fields.temperatureRequirement);
    setPalletCaseCount(fields.palletCaseCount);
    setRate(fields.rate);
    setCustomerRate(fields.customerRate);
    setMiles(fields.miles);
    setDriverId(null);
    setTruckId(null);
    setTrailerId(null);
    setCustomsBrokerId(fields.customsBrokerId);
    setInternalNotes(fields.internalNotes);
    setDraftStops(fields.draftStops);
  }, []);

  const getParseHydrationCallbacks = useCallback(
    (): ApplyLoadDocumentParseCallbacks => ({
      setBrokerNameSnapshot,
      setBrokerId,
      setBrokerContactId,
      setBrokerContacts,
      setBrokerContactNameSnapshot,
      setBrokerContactPhoneSnapshot,
      setBrokerContactEmailSnapshot,
      setBrokerLoadReference,
      setLoadReferences,
      setFreightMode,
      setEquipmentType,
      setTrailerType,
      setTrailerSize,
      setCommodity,
      setEstimatedWeight,
      setTemperatureRequirement,
      setRate,
      setCustomerRate,
      setMiles,
      setInternalNotes,
      existingInternalNotes: internalNotes,
      setDraftStops,
    }),
    [internalNotes],
  );

  const applyWorkspaceDraft = useCallback(
    (draft: LoadWorkspaceDraft, opts?: { restorePdf?: boolean }) => {
      setWorkspaceDraft(draft);
      const fields = workspaceFieldsFromDraftJson(draft.draft_json ?? {});
      hydrateFromWorkspaceFields(fields);
      if (opts?.restorePdf) {
        void restoreDraftPdfArtifacts(draft);
      }
      const accepted = loadDocumentParseFromAcceptedJson(draft.accepted_parse_json ?? null);
      if (accepted) {
        applyEmptyWorkspaceFieldsFromParseResponse(fields, accepted, getParseHydrationCallbacks());
        if (accepted.raw_text) {
          setWorkspaceReferenceText(accepted.raw_text);
        }
      }
    },
    [hydrateFromWorkspaceFields, restoreDraftPdfArtifacts, getParseHydrationCallbacks],
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
    setLoadReferences(Array.isArray(l.references) ? l.references : []);
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
          loadNumber,
          brokerId,
          brokerContactId,
          brokerNameSnapshot,
          brokerContactNameSnapshot,
          brokerContactPhoneSnapshot,
          brokerContactExtensionSnapshot,
          brokerContactEmailSnapshot,
          brokerLoadReference,
          loadReferences,
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
          customsBrokerId,
          internalNotes,
          draftStops,
        }),
      ),
    [
      loadNumber,
      brokerId,
      brokerContactId,
      brokerNameSnapshot,
      brokerContactNameSnapshot,
      brokerContactPhoneSnapshot,
      brokerContactExtensionSnapshot,
      brokerContactEmailSnapshot,
      brokerLoadReference,
      loadReferences,
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

  const trackParseManualScalar = useCallback((key: ParseScalarFieldKey, value: string) => {
    registerManualParseFieldEdit(parseHydrationRef.current, key, value);
  }, []);

  const setBrokerNameSnapshotTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("brokerNameSnapshot", v);
      setBrokerNameSnapshot(v);
    },
    [trackParseManualScalar],
  );
  const setBrokerLoadReferenceTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("brokerLoadReference", v);
      setBrokerLoadReference(v);
    },
    [trackParseManualScalar],
  );
  const setFreightModeTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("freightMode", v);
      setFreightMode(v);
    },
    [trackParseManualScalar],
  );
  const setEquipmentTypeTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("equipmentType", v);
      setEquipmentType(v);
    },
    [trackParseManualScalar],
  );
  const setTrailerTypeTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("trailerType", v);
      setTrailerType(v);
    },
    [trackParseManualScalar],
  );
  const setTrailerSizeTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("trailerSize", v);
      setTrailerSize(v);
    },
    [trackParseManualScalar],
  );
  const setCommodityTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("commodity", v);
      setCommodity(v);
    },
    [trackParseManualScalar],
  );
  const setEstimatedWeightTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("estimatedWeight", v);
      setEstimatedWeight(v);
    },
    [trackParseManualScalar],
  );
  const setTemperatureRequirementTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("temperatureRequirement", v);
      setTemperatureRequirement(v);
    },
    [trackParseManualScalar],
  );
  const setRateTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("rate", v);
      setRate(v);
    },
    [trackParseManualScalar],
  );
  const setCustomerRateTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("customerRate", v);
      setCustomerRate(v);
    },
    [trackParseManualScalar],
  );
  const setMilesTracked = useCallback(
    (v: string) => {
      trackParseManualScalar("miles", v);
      setMiles(v);
    },
    [trackParseManualScalar],
  );

  const onParseWorkspacePdf = useCallback(
    async (file: File, continueAnyway = false) => {
      if (!canWorkspaceParsePdf) return;
      if (workspaceMode !== "manual" && isDraftWorkspace && (!draftIdFromRoute || !workspaceDraft)) return;
      // Local PDF duplicate review must complete BEFORE semantic AI and form hydration.
      if (!continueAnyway) setDuplicateReview(null);
      // Load Lab / parser: hydrate commercial fields only — no trip creation, assignment, dispatch_trips, or dispatched status.
      setParseBusy(true);
      setParseWarnings([]);
      setToolbarMessage(null);
      setLastParseAppliedLabels(null);
      setLastParseEngineAttribution(null);
      const parseWallStarted = performance.now();
      try {
        if (workspaceMode === "manual") {
          const { id: manualDraftId, draft: manualDraft } = await ensureServerDraft({
            syncRoute: false,
          });
          const persisted = await parseLoadWorkspaceDraftDocument(manualDraftId, file, {
            expectedConcurrencyVersion: manualDraft.concurrency_version,
            continueAnyway,
          });
          const parseRequestMs = performance.now() - parseWallStarted;
          const res = persisted.parse;
          const duplicateCandidates = duplicateLoadCandidatesFromParse(res);
          if (duplicateCandidates !== null) {
            setDuplicateReview({ file, candidates: duplicateCandidates });
            return; // No accepted parse, stored PDF replacement or form hydration.
          }
          setDuplicateReview(null);
          setWorkspaceDraft(persisted.draft);
          setWorkspaceReferenceText(res.raw_text || "");
          replaceWorkspacePdfPreviewUrl(URL.createObjectURL(file));
          const hydration = await hydrateLoadWorkspaceFromParseResponse(
            res,
            getParseHydrationCallbacks(),
            parseHydrationRef.current,
          );
          parseHydrationRef.current = hydration.parseHydrationState;
          setParseWarnings(hydration.warnings);
          const engineLine =
            buildParseEngineAttribution(res.context ?? undefined, {
              parseRequestMs,
              totalMs: performance.now() - parseWallStarted,
            }) ?? hydration.engineAttribution;
          setLastParseEngineAttribution(engineLine);
          setToolbarMessage({
            text: engineLine ? `${hydration.toolbar.text} — ${engineLine}` : hydration.toolbar.text,
            tone: hydration.toolbar.tone,
          });
          setLastParseAppliedLabels(hydration.appliedLabels);
          setDraftConflict(null);
          const saved = await persistWorkspaceDraftAfterParse({
            draftId: manualDraftId,
            draftVersion: persisted.draft.concurrency_version,
            res,
            summary: hydration.summary,
            status,
            seed: {
              loadNumber,
              hazmat,
              palletCaseCount,
              customsBrokerId,
              existingInternalNotes: internalNotes,
            },
            updateDraft: updateLoadWorkspaceDraft,
            buildDraftJson: buildWorkspaceDraftJson,
          });
          setWorkspaceDraft({
            ...persisted.draft,
            concurrency_version: saved.concurrency_version,
            draft_json: saved.draft_json ?? persisted.draft.draft_json,
          });
          navigate(OPS.LOAD_DRAFT(manualDraftId), { replace: true });
          return;
        }

        const res = await parseLoadWorkspaceDocument(file, {
          emailThreadId: hasIntakeThread ? intakeThreadId : undefined,
          loadId: !isManual && Number.isFinite(loadIdFromRoute) ? loadIdFromRoute : undefined,
          continueAnyway,
        });
        const duplicateCandidates = duplicateLoadCandidatesFromParse(res);
        if (duplicateCandidates !== null) {
          setDuplicateReview({ file, candidates: duplicateCandidates });
          return; // Do not hydrate the form from an empty review-only parse.
        }
        setDuplicateReview(null);
        const parseRequestMs = performance.now() - parseWallStarted;
        const hydration = await hydrateLoadWorkspaceFromParseResponse(
          res,
          {
            setBrokerNameSnapshot,
            setBrokerId,
            setBrokerContactId,
            setBrokerContacts,
            setBrokerContactNameSnapshot,
            setBrokerContactPhoneSnapshot,
            setBrokerContactEmailSnapshot,
            setBrokerLoadReference,
            setLoadReferences,
            setFreightMode,
            setEquipmentType,
            setTrailerType,
            setTrailerSize,
            setCommodity,
            setEstimatedWeight,
            setTemperatureRequirement,
            setRate,
            setCustomerRate,
            setMiles,
            setInternalNotes,
            existingInternalNotes: internalNotes,
            setDraftStops,
          },
          parseHydrationRef.current,
        );
        parseHydrationRef.current = hydration.parseHydrationState;
        setParseWarnings(hydration.warnings);
        const engineLine =
          buildParseEngineAttribution(res.context ?? undefined, {
            parseRequestMs,
            totalMs: performance.now() - parseWallStarted,
          }) ?? hydration.engineAttribution;
        setLastParseEngineAttribution(engineLine);
        const tone: WorkspaceToolbarTone = hydration.toolbar.tone;
        setToolbarMessage({
          text: engineLine ? `${hydration.toolbar.text} — ${engineLine}` : hydration.toolbar.text,
          tone,
        });
        setLastParseAppliedLabels(hydration.appliedLabels);
      } catch (e: unknown) {
        const c = parseLoadWorkspaceDraftVersionConflict(e);
        if (c && isDraftWorkspace) {
          setDraftConflict({ serverVersion: c.server_version });
          setToolbarMessage({
            text: "Draft was modified elsewhere — reload before parsing again.",
            tone: "warning",
          });
        } else {
          const msg = e instanceof Error ? e.message : "PDF parse failed";
          setToolbarMessage({ text: msg, tone: "error" });
        }
        setLastParseAppliedLabels(null);
        setLastParseEngineAttribution(null);
      } finally {
        setParseBusy(false);
      }
    },
    [
      canWorkspaceParsePdf,
      hasIntakeThread,
      intakeThreadId,
      internalNotes,
      isManual,
      loadIdFromRoute,
      isDraftWorkspace,
      draftIdFromRoute,
      workspaceDraft,
      replaceWorkspacePdfPreviewUrl,
      getParseHydrationCallbacks,
      loadNumber,
      hazmat,
      palletCaseCount,
      customsBrokerId,
      status,
      navigate,
    ],
  );

  useOperationalRefresh({
    intervalMs: null,
    enabled: workspaceMode !== "manual" && Number.isFinite(loadIdFromRoute) && !loading,
    isDirty: formDirty,
    onRefresh: () => void refreshLoadFromServer(),
  });

  useEffect(() => {
    if (workspaceMode === "manual" && isManualCreate) {
      setLoading(false);
      setError(null);
      return;
    }

    if (workspaceMode === "manual" && isDraftWorkspace && draftIdFromRoute) {
      let cancelled = false;
      setLoading(true);
      setError(null);
      const draftId = draftIdFromRoute;
      Promise.all([
        getLoadWorkspaceDraft(draftId),
        listCustomsBrokers({ page: 1, size: 200, include_inactive: false }),
        listBrokers({ page: 1, size: 200, sort: "name_asc" }),
        listDrivers({ limit: 500, include_inactive: false }),
        listTrucks({ page: 1, size: 200, status: ["active"] }),
        listTrailers({ page: 1, size: 200, status: ["active"] }),
      ])
        .then(([draft, customsPaged, brPaged, dr, trk, trl]) => {
          if (cancelled) return;
          if (draft.status !== "draft") {
            setError(workspaceDraftClosedMessage(draft.status));
            setWorkspaceDraft(draft);
            return;
          }
          applyWorkspaceDraft(draft, { restorePdf: true });
          setCustomsBrokers(customsPaged.items || []);
          setFreightBrokers(brPaged.items || []);
          setDrivers(dr);
          setTrucks(trk.items || []);
          setTrailers(trl.items || []);
        })
        .catch((e) => {
          if (!cancelled) setError((e as Error)?.message || "Failed to load workspace draft");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
      return () => {
        cancelled = true;
      };
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
  }, [
    workspaceMode,
    loadIdFromRoute,
    hydrateFromLoad,
    isManualCreate,
    isDraftWorkspace,
    draftIdFromRoute,
    navigate,
    applyWorkspaceDraft,
  ]);

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

  const workspacePersistParams = (): LoadPersistParams => ({
    loadNumber,
    brokerId,
    brokerContactId,
    brokerNameSnapshot,
    brokerContactNameSnapshot,
    brokerContactPhoneSnapshot,
    brokerContactExtensionSnapshot,
    brokerContactEmailSnapshot,
    brokerLoadReference,
    loadReferences,
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
    customsBrokerId,
    internalNotes,
    draftStops,
  });

  const buildWorkspacePersistPayload = () => buildLoadPersistPayload(workspacePersistParams());

  function currentWorkspaceFields(): WorkspaceDraftFields {
    const p = workspacePersistParams();
    return {
      status,
      loadNumber: p.loadNumber,
      brokerId: p.brokerId,
      brokerContactId: p.brokerContactId,
      brokerNameSnapshot: p.brokerNameSnapshot,
      brokerContactNameSnapshot: p.brokerContactNameSnapshot,
      brokerContactPhoneSnapshot: p.brokerContactPhoneSnapshot,
      brokerContactExtensionSnapshot: p.brokerContactExtensionSnapshot,
      brokerContactEmailSnapshot: p.brokerContactEmailSnapshot,
      brokerLoadReference: p.brokerLoadReference,
      loadReferences: p.loadReferences ?? [],
      freightMode: p.mode,
      equipmentType: p.equipmentType,
      trailerType: p.trailerType,
      trailerSize: p.trailerSize,
      commodity: p.commodity,
      estimatedWeight: p.estimatedWeight,
      hazmat: p.hazmat,
      temperatureRequirement: p.temperatureRequirement,
      palletCaseCount: p.palletCaseCount,
      rate: p.rate,
      customerRate: p.customerRate,
      miles: p.miles,
      driverId: null,
      truckId: null,
      trailerAssetId: null,
      customsBrokerId: p.customsBrokerId,
      internalNotes: p.internalNotes,
      draftStops: p.draftStops,
    };
  }

  /** Always read latest form state — gate must not use a stale useCallback closure after parse hydration. */
  const currentWorkspaceFieldsRef = useRef(currentWorkspaceFields);
  currentWorkspaceFieldsRef.current = currentWorkspaceFields;

  const hasParsedPdfIntoDraft = draftHasParsedPdf(workspaceDraft, parseHydrationRef.current);
  const manualCreateHardMissing = listManualCreateHardMissing(currentWorkspaceFields());
  const createSoftNotProvided = listCreateLoadSoftNotProvided(
    currentWorkspaceFields(),
    freightBrokers,
  );
  const createUnderButtonLine = hasParsedPdfIntoDraft
    ? formatSoftNotProvidedLine(createSoftNotProvided)
    : formatManualHardMissingLine(manualCreateHardMissing);
  const createLoadBlockedByHardGate =
    !hasParsedPdfIntoDraft && manualCreateHardMissing.length > 0;

  async function ensureServerDraft(
    options: { syncRoute?: boolean } = {},
  ): Promise<{ id: string; draft: LoadWorkspaceDraft }> {
    const syncRoute = options.syncRoute !== false;
    if (workspaceDraft?.status === "draft" && workspaceDraft.id) {
      const id = workspaceDraft.id;
      if (syncRoute && draftIdFromRoute !== id) {
        navigate(OPS.LOAD_DRAFT(id), { replace: true });
      }
      return { id, draft: workspaceDraft };
    }
    if (draftIdFromRoute && workspaceDraft) {
      return { id: draftIdFromRoute, draft: workspaceDraft };
    }
    const created = await createLoadWorkspaceDraft({
      source_channel: "manual",
      draft_json: buildWorkspaceDraftJson({ ...workspacePersistParams(), status }),
    });
    setWorkspaceDraft(created);
    if (syncRoute) {
      navigate(OPS.LOAD_DRAFT(created.id), { replace: true });
    }
    return { id: created.id, draft: created };
  }

  const closeCommercialGate = useCallback((outcome: WorkspaceCommercialGateOutcome) => {
    setCommercialGatePrompt(null);
    const resolve = commercialGateResolverRef.current;
    commercialGateResolverRef.current = null;
    resolve?.(outcome);
  }, []);

  const requestWorkspaceCommercialGate = useCallback(
    (mode: "create" | "save"): Promise<WorkspaceCommercialGateOutcome> => {
      const prompt = resolveWorkspaceCommercialGatePrompt(
        currentWorkspaceFieldsRef.current(),
        freightBrokers,
        mode,
      );
      if (prompt.outcome === "blocked") {
        window.alert(prompt.alertMessage);
        return Promise.resolve("blocked");
      }
      return new Promise((resolve) => {
        commercialGateResolverRef.current = resolve;
        setCommercialGatePrompt({ message: prompt.message, mode: prompt.mode });
      });
    },
    [freightBrokers],
  );

  const showMarkReadyAction =
    load != null &&
    (workspaceMode === "detail" || workspaceMode === "intake") &&
    (load.status || "").toLowerCase() === "draft";

  const showCancelLoadAction =
    load != null &&
    (workspaceMode === "detail" || workspaceMode === "intake") &&
    ["draft", "ready"].includes((load.status || "").toLowerCase());

  function formatLoadCancelError(err: unknown): string {
    if (!(err instanceof Error)) return "Could not cancel load.";
    const raw = err.message?.trim() || "";
    try {
      const parsed = JSON.parse(raw) as { detail?: unknown };
      const detail = parsed.detail;
      if (detail && typeof detail === "object" && detail !== null && !Array.isArray(detail)) {
        const code = (detail as { code?: string }).code;
        switch (code) {
          case "LOAD_CANCEL_ACTIVE_TRIP_EXECUTION":
            return "This load is active on an assigned or in-progress trip. Close custody on the trip before cancelling commercially.";
          case "LOAD_CANCEL_UNRESOLVED_CUSTODY":
            return "Custody must be resolved (unknown or delivered) before commercial cancel.";
          case "LOAD_CANCEL_STATUS_NOT_ALLOWED":
            return "This load status cannot be cancelled from here.";
          default:
            break;
        }
        const msg =
          typeof (detail as { detail?: unknown }).detail === "string"
            ? (detail as { detail: string }).detail
            : null;
        if (msg) return msg;
      }
    } catch {
      /* use raw */
    }
    if (raw.length > 0 && raw.length < 400) return raw;
    return "Could not cancel load.";
  }

  async function onCancelLoad() {
    if (!load) return;
    const reason = window.prompt("Cancellation reason (required):");
    if (reason == null) return;
    const trimmed = reason.trim();
    if (!trimmed) {
      setToolbarMessage({ text: "Cancellation reason is required.", tone: "warning" });
      return;
    }
    const ok = window.confirm(
      "Cancel this commercial load?\n\nThe load record, trip memberships, and custody history are preserved. This does not delete the load or post payroll adjustments.\n\nContinue?",
    );
    if (!ok) return;
    const expectedVersion = load.concurrency_version ?? 1;
    setCancelLoadBusy(true);
    setToolbarMessage(null);
    setError(null);
    try {
      const updated = await cancelLoad(load.id, expectedVersion, trimmed);
      setLoad(updated);
      hydrateFromLoad(updated);
      setToolbarMessage({ text: "Load cancelled.", tone: "success" });
    } catch (e: unknown) {
      const mc = parseLoadVersionConflict(e);
      if (mc) {
        setServerConflict({
          serverVersion: mc.server_version,
          serverSnapshot: mc.server_snapshot,
        });
        setToolbarMessage({ text: "Cancel conflicted — reload and retry.", tone: "warning" });
        if (mc.server_snapshot) {
          setLoad(mc.server_snapshot);
          hydrateFromLoad(mc.server_snapshot);
        }
      } else {
        setToolbarMessage({ text: formatLoadCancelError(e), tone: "error" });
      }
    } finally {
      setCancelLoadBusy(false);
    }
  }

  async function onDiscardDraft() {
    if (!isDraftEditable) return;
    if (isLocalNewDraft) {
      navigate(OPS.LOADS, { replace: true });
      return;
    }
    if (!draftIdFromRoute) return;
    const confirmed = window.confirm(
      "Discard this draft? Saved data and the PDF will be removed. This cannot be undone.",
    );
    if (!confirmed) return;
    setSaving(true);
    setToolbarMessage(null);
    try {
      await discardLoadWorkspaceDraft(draftIdFromRoute, { discard_reason: "operator_discard" });
      navigate(OPS.LOADS, { replace: true });
    } catch (e: unknown) {
      setToolbarMessage({ text: formatApiErrorMessage(e, "Could not discard draft"), tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function onSaveDraft() {
    if (!isDraftEditable) return;
    setSaving(true);
    setToolbarMessage(null);
    setDraftConflict(null);
    try {
      const { id, draft } = await ensureServerDraft();
      const updated = await updateLoadWorkspaceDraft(id, {
        expected_concurrency_version: draft.concurrency_version,
        draft_json: buildWorkspaceDraftJson({ ...workspacePersistParams(), status }),
      });
      applyWorkspaceDraft(updated, { restorePdf: true });
      setToolbarMessage({
        text: "Draft saved for later. Use Create load when you are ready to assign it.",
        tone: "success",
      });
    } catch (e: unknown) {
      const c = parseLoadWorkspaceDraftVersionConflict(e);
      if (c) {
        setDraftConflict({ serverVersion: c.server_version });
        setToolbarMessage({
          text: "Draft was modified elsewhere — see conflict details above.",
          tone: "warning",
        });
      } else {
        setToolbarMessage({ text: formatApiErrorMessage(e, "Could not save draft"), tone: "error" });
      }
    } finally {
      setSaving(false);
    }
  }

  async function onReloadDraftVersion() {
    if (!draftIdFromRoute) return;
    const confirmed = window.confirm(
      "Reload the server draft? Unsaved changes in this tab will be replaced with the server version.",
    );
    if (!confirmed) return;
    setSaving(true);
    setToolbarMessage(null);
    setDraftConflict(null);
    try {
      const remote = await getLoadWorkspaceDraft(draftIdFromRoute);
      if (remote.status !== "draft") {
        setError("This workspace draft is no longer editable.");
        return;
      }
      applyWorkspaceDraft(remote, { restorePdf: true });
      setToolbarMessage({ text: "Loaded latest draft from server.", tone: "neutral" });
    } catch (e: unknown) {
      setToolbarMessage({ text: formatApiErrorMessage(e, "Could not reload draft"), tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  async function onPromoteDraft() {
    if (!isDraftEditable) return;
    if (createLoadBlockedByHardGate) {
      setToolbarMessage({
        text: createUnderButtonLine ?? "Complete required fields before creating a load.",
        tone: "warning",
      });
      return;
    }
    if (!hasParsedPdfIntoDraft) {
      const createGate = await requestWorkspaceCommercialGate("create");
      if (createGate === "cancelled") return;
    }
    setSaving(true);
    setToolbarMessage(null);
    setDraftConflict(null);
    try {
      const { id, draft } = await ensureServerDraft({ syncRoute: false });
      const saved = await updateLoadWorkspaceDraft(id, {
        expected_concurrency_version: draft.concurrency_version,
        draft_json: buildWorkspaceDraftJson({ ...workspacePersistParams(), status }),
      });
      applyWorkspaceDraft(saved);
      const result = await promoteLoadWorkspaceDraft(id, {
        expected_concurrency_version: saved.concurrency_version,
        promotion_idempotency_key: crypto.randomUUID(),
      });
      const loadId = Number(result.load_id);
      if (!Number.isFinite(loadId) || loadId <= 0) {
        throw new Error("Create load succeeded but the server did not return a load id.");
      }
      if (driverId != null && driverId > 0) {
        const trip = await createTripForLoadAssignment(loadId, {
          driver_id: driverId,
          truck_id: truckId,
          trailer_id: trailerId,
        });
        navigate(OPS.TRIP_DETAIL(trip.id), { replace: true });
      } else {
        navigate(OPS.DASHBOARD, { replace: true });
      }
    } catch (e: unknown) {
      const c = parseLoadWorkspaceDraftVersionConflict(e);
      if (c) {
        setDraftConflict({ serverVersion: c.server_version });
        setToolbarMessage({
          text: "Draft was modified elsewhere — save or reload before creating the load.",
          tone: "warning",
        });
      } else {
        setToolbarMessage({ text: formatApiErrorMessage(e, "Could not create load"), tone: "error" });
      }
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
    const stopErr = validateDraftStopsClassifiedForSave(draftStops);
    if (stopErr) {
      setToolbarMessage({ text: stopErr, tone: "warning" });
      return;
    }
    const expectedVersion = load.concurrency_version ?? 1;
    setSaving(true);
    setToolbarMessage(null);
    setError(null);
    try {
      const updated = await updateLoad(load.id, {
        ...buildWorkspacePersistPayload(),
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
        setToolbarMessage({ text: formatApiErrorMessage(e, "Save failed"), tone: "error" });
      }
    } finally {
      setSaving(false);
    }
  }

  async function onMarkReady() {
    if (!load) return;
    const expectedVersion = load.concurrency_version ?? 1;
    setMarkReadyBusy(true);
    setToolbarMessage(null);
    setError(null);
    try {
      const afterSave = await updateLoad(load.id, {
        ...buildWorkspacePersistPayload(),
        expected_concurrency_version: expectedVersion,
      });
      setLoad(afterSave);
      hydrateFromLoad(afterSave);
      setServerConflict(null);
      try {
        const ready = await markLoadReady(load.id, afterSave.concurrency_version ?? 1);
        setLoad(ready);
        hydrateFromLoad(ready);
        setToolbarMessage({ text: "Load marked ready.", tone: "success" });
        setServerConflict(null);
      } catch (me: unknown) {
        const mc = parseLoadVersionConflict(me);
        if (mc) {
          setServerConflict({
            serverVersion: mc.server_version,
            serverSnapshot: mc.server_snapshot,
          });
          setToolbarMessage({
            text: "Saved, but mark ready conflicted — see details above.",
            tone: "warning",
          });
          if (mc.server_snapshot) {
            setLoad(mc.server_snapshot);
            hydrateFromLoad(mc.server_snapshot);
          }
        } else {
          setToolbarMessage({
            text: formatApiErrorMessage(me, "Could not mark load ready."),
            tone: "error",
          });
        }
      }
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
        setToolbarMessage({ text: formatApiErrorMessage(e, "Save failed"), tone: "error" });
      }
    } finally {
      setMarkReadyBusy(false);
    }
  }

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

  if (!isManual && !isDraftWorkspace && (!idParam || !Number.isFinite(loadIdFromRoute))) {
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
  const hasActiveDispatchTrip = load?.active_dispatch_trip_id != null;

  const lidLabel = workspaceMode === "manual" ? "#NEW" : load ? `#${load.id}` : "#—";
  const intakeQueueUrl = hasIntakeThread ? `${OPS.INTAKE}?thread=${intakeThreadId}` : OPS.INTAKE;
  const toolBtnSecondary =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-[11px] font-semibold text-[var(--trk-text-muted)] shadow-sm hover:border-[var(--trk-border-strong)] hover:bg-[var(--trk-border)]";

  /** Compare the server snapshot against the current form state; return human-readable diffs. */
  function getConflictDiffs(snap: Load): Array<{ label: string; server: string; yours: string }> {
    const f = buildWorkspacePersistPayload() as Record<string, unknown>;

    const fmt = (v: unknown, money = false): string => {
      if (v == null || v === "") return "—";
      return money ? `$${v}` : String(v);
    };

    const checks: Array<{ label: string; snapKey: keyof Load; formKey: string; money?: boolean }> = [
      { label: "TruckERP ID",   snapKey: "load_number",            formKey: "load_number" },
      { label: "Broker",        snapKey: "broker_name_snapshot",   formKey: "broker_name_snapshot" },
      { label: "Load Number",   snapKey: "broker_load_reference",  formKey: "broker_load_reference" },
      { label: "Rate",          snapKey: "rate",                   formKey: "rate",          money: true },
      { label: "Customer rate", snapKey: "customer_rate",          formKey: "customer_rate", money: true },
      { label: "Miles",         snapKey: "miles",                  formKey: "miles" },
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
    const serverRefs = JSON.stringify(snap.references ?? []);
    const formRefs = JSON.stringify(f.references ?? []);
    if (serverRefs !== formRefs) {
      diffs.push({ label: "References", server: serverRefs, yours: formRefs });
    }
    return diffs;
  }

  return (
    <div className="flex min-h-screen flex-col bg-[var(--trk-bg)] text-[var(--trk-text)]">
      {duplicateReview ? (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/65 p-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Possible duplicate load"
            className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-[var(--trk-border-strong)] bg-[var(--trk-surface)] p-5 text-[var(--trk-text)] shadow-xl"
          >
            <h2 className="text-base font-semibold">This PDF is already on an existing Load</h2>
            <p className="mt-2 text-xs text-[var(--trk-text-muted)]">
              Exact PDF match found before AI parsing. Review the existing Load.
              Cancel saves the AI cost; Continue anyway performs the normal parse.
            </p>
            {duplicateReview.candidates.map((match) => (
              <div key={match.load_id} className="mt-3 space-y-1 rounded border border-[var(--trk-border)] p-3 text-xs">
                <div className="font-semibold">
                  <Link className="underline" to={OPS.LOAD_DETAIL(match.load_id)}>
                    Load {match.load_number}
                  </Link>
                  <span className="ml-2 font-normal">Commercial: {match.load_status}</span>
                </div>
                <div>Broker: {match.broker_name || "Not recorded"} · Broker reference: {match.broker_load_reference || "—"}</div>
                <div>{match.pickup || "Pickup unknown"} → {match.delivery || "Delivery unknown"}</div>
                <div>
                  Trip: {match.trip_id == null ? "None" : `#${match.trip_id} (${match.trip_status || "unknown"})`}
                  {" · "}Driver: {match.driver_id ?? "—"} · Truck: {match.truck_id ?? "—"} · Trailer: {match.trailer_id ?? "—"}
                </div>
                <p className="text-[10px] text-[var(--trk-text-muted)]">
                  Trip information describes a matching Load's assignment, not necessarily today's physical equipment.
                </p>
              </div>
            ))}
            <div className="mt-4 flex flex-wrap justify-end gap-2">
              <button
                type="button"
                disabled={parseBusy}
                className={toolBtnSecondary}
                onClick={() => {
                  setDuplicateReview(null);
                  setToolbarMessage({ text: "Duplicate PDF cancelled before AI parsing.", tone: "warning" });
                }}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={parseBusy}
                className={toolBtnSecondary}
                onClick={() => void onParseWorkspacePdf(duplicateReview.file, true)}
              >
                Continue anyway — parse PDF
              </button>
            </div>
          </div>
        </div>
      ) : null}
      <header className="z-10 shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
        <div className="flex flex-wrap items-center gap-3 px-4 py-2.5">
            <button type="button" onClick={() => navigate(OPS.LOADS)} className={toolBtnSecondary}>
              ← Loads
            </button>
            <div className="flex min-w-0 items-baseline gap-2">
              <span className="font-mono text-[11px] text-[var(--trk-text-muted)]">{lidLabel}</span>
              <h1 className="truncate text-[14px] font-semibold tracking-tight text-[var(--trk-heading)]">
                {workspaceMode === "manual" ? "New load" : loadNumber || load?.load_number || "Load"}
              </h1>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {workspaceMode !== "manual" && load ? (
                <OperatorLoadStatusChip
                  load={{
                    status: load.status,
                    active_trip_id: load.active_trip_id,
                    open_planned_trip_id: load.open_planned_trip_id,
                    open_future_movement_plan_id: load.open_future_movement_plan_id,
                    custody_owner: load.custody_owner,
                  }}
                />
              ) : (
                <OperatorLoadStatusChip load={{ status: "draft" }} />
              )}
              {workspaceMode === "detail" ? (
                <span className="rounded border border-emerald-800 bg-emerald-950/40 px-2 py-0.5 text-[10.5px] font-semibold text-emerald-400">
                  DETAIL
                </span>
              ) : null}
              {workspaceMode === "manual" ? (
                <span className="rounded bg-[var(--trk-btn-primary)] px-2 py-0.5 text-[10.5px] font-semibold text-[var(--trk-btn-text)]">
                  Manual
                </span>
              ) : null}
              {workspaceMode === "intake" ? (
                <span className="rounded border border-sky-800 bg-sky-950/40 px-2 py-0.5 text-[10.5px] font-semibold text-sky-300">
                  Intake
                </span>
              ) : null}
            </div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
          <button type="button" className={toolBtnSecondary} onClick={() => navigate(OPS.LOADS)}>
            Load directory
          </button>
          <button
            type="button"
            className={toolBtnSecondary}
            data-testid="load-workspace-dispatch-nav"
            onClick={() => navigate(OPS.TRIP_CONTAINER)}
          >
            Dispatch
          </button>
          {workspaceMode === "intake" ? (
            <button type="button" className={toolBtnSecondary} onClick={() => navigate(intakeQueueUrl)}>
              Intake queue
            </button>
          ) : null}
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
              disabled={
                saving ||
                markReadyBusy ||
                cancelLoadBusy ||
                parseBusy ||
                loading ||
                (isDraftWorkspace && !isDraftEditable)
              }
              onClick={() => pdfInputRef.current?.click()}
            >
              {parseBusy
                ? parseElapsedSec > 0
                  ? `Parsing… ${parseElapsedSec}s`
                  : "Parsing…"
                : "Upload & parse PDF"}
            </Button>
          ) : null}
          {showManualDraftActions ? (
            <>
              <Button
                variant="secondary"
                type="button"
                disabled={saving || markReadyBusy || !isDraftEditable}
                onClick={() => void onDiscardDraft()}
              >
                Discard
              </Button>
              <Button
                variant="secondary"
                type="button"
                disabled={saving || markReadyBusy || parseBusy || !isDraftEditable}
                onClick={() => void onSaveDraft()}
              >
                {saving ? "Saving…" : "Save for later"}
              </Button>
              <Button
                variant="primary"
                type="button"
                disabled={saving || markReadyBusy || parseBusy || !isDraftEditable || createLoadBlockedByHardGate}
                title={createUnderButtonLine ?? undefined}
                onClick={() => void onPromoteDraft()}
              >
                {saving ? "Creating…" : "Create load"}
              </Button>
              {createUnderButtonLine ? (
                <p className="w-full text-[11px] text-amber-400/90 sm:w-auto">{createUnderButtonLine}</p>
              ) : null}
            </>
          ) : workspaceMode === "manual" ? null : (
            <>
              <Button
                variant="primary"
                type="button"
                disabled={saving || markReadyBusy || cancelLoadBusy}
                onClick={() => void onSave()}
              >
                {saving ? "Saving…" : "Save load"}
              </Button>
              {showMarkReadyAction ? (
                <Button
                  variant="secondary"
                  type="button"
                  className="!border-[var(--trk-btn-primary)] !bg-[var(--trk-btn-primary)] !text-[var(--trk-btn-text)] hover:!bg-amber-400"
                  disabled={saving || markReadyBusy || cancelLoadBusy || loading || parseBusy}
                  title="Saves your edits, then marks this load ready when broker, load reference, and pickup + delivery stops are set."
                  onClick={() => void onMarkReady()}
                >
                  {markReadyBusy ? "Marking ready…" : "Mark ready"}
                </Button>
              ) : null}
              {showCancelLoadAction ? (
                <Button
                  variant="secondary"
                  type="button"
                  data-testid="load-workspace-cancel-load"
                  disabled={saving || markReadyBusy || cancelLoadBusy || loading}
                  onClick={() => void onCancelLoad()}
                >
                  {cancelLoadBusy ? "Cancelling…" : "Cancel load"}
                </Button>
              ) : null}
            </>
          )}
          {toolbarMessage ? (
            <span
              className={clsx(
                "max-w-full text-[11px] sm:max-w-md",
                workspaceToolbarToneClassName(toolbarMessage.tone),
              )}
            >
              {toolbarMessage.text}
            </span>
          ) : null}
            </div>
        </div>
        {workspaceMode === "detail" && load ? (
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 border-t border-[var(--trk-border)] bg-[var(--trk-bg)] px-4 py-1.5 text-[11.5px] text-[var(--trk-text-muted)]">
            <span>
              <span className="font-medium text-[var(--trk-text)]">Trip</span>{" "}
              {load.trip_number?.trim() ? (
                <span className="font-mono">{load.trip_number.trim()}</span>
              ) : (
                "No trip number"
              )}
            </span>
            <span className="text-[var(--trk-border-strong)]">·</span>
            {load.open_future_movement_plan_id != null ? (
              <Link
                to={OPS.FUTURE_MOVEMENT_PLAN_DETAIL(load.open_future_movement_plan_id)}
                className="font-semibold text-[var(--trk-heading)] hover:underline"
              >
                Open future movement plan →
              </Link>
            ) : null}
            {load.open_future_movement_plan_id != null ? (
              <span className="text-[var(--trk-border-strong)]">·</span>
            ) : null}
            {load.active_trip_id != null ? (
              <>
                <Link
                  to={OPS.TRIP_DETAIL(load.active_trip_id)}
                  className="font-semibold text-[var(--trk-heading)] hover:underline"
                >
                  View / Assign on Trip →
                </Link>
                {load.status === "ready" &&
                load.open_planned_trip_id == null &&
                load.open_future_movement_plan_id == null ? (
                  <>
                    <span className="text-[var(--trk-border-strong)]">·</span>
                    <button
                      type="button"
                      className="font-semibold text-[var(--trk-heading)] hover:underline"
                      onClick={() => setFollowUpDispatchOpen(true)}
                    >
                      Follow-up dispatch →
                    </button>
                  </>
                ) : null}
              </>
            ) : load.open_planned_trip_id != null ? (
              <Link
                to={OPS.TRIP_DETAIL(load.open_planned_trip_id)}
                className="font-semibold text-[var(--trk-heading)] hover:underline"
              >
                Open planned trip
                {load.open_planned_trip_number?.trim()
                  ? ` (${load.open_planned_trip_number.trim()})`
                  : ""}{" "}
                →
              </Link>
            ) : (
              <button
                type="button"
                disabled={createPlannedTripBusy}
                title="Creates the trip container and opens the trip workspace to assign equipment."
                onClick={() => void onCreatePlannedTrip()}
                className="font-semibold text-[var(--trk-heading)] hover:underline disabled:cursor-not-allowed disabled:opacity-50"
              >
                {createPlannedTripBusy ? "Creating trip…" : "Create Planned Trip →"}
              </button>
            )}
            <span className="text-[var(--trk-border-strong)]">·</span>
            <span>{hasActiveDispatchTrip ? "Dispatch linked" : "No dispatch trip"}</span>
            {(load.created_at || load.updated_at) && (
              <>
                <span className="text-[var(--trk-border-strong)]">·</span>
                <span>
                  {load.created_at ? `Created ${new Date(load.created_at).toLocaleString()}` : ""}
                  {load.created_at && load.updated_at ? " · " : ""}
                  {load.updated_at ? `Updated ${new Date(load.updated_at).toLocaleString()}` : ""}
                </span>
              </>
            )}
          </div>
        ) : null}
        {workspaceMode === "detail" && load && createPlannedTripError ? (
          <p className="border-t border-[var(--trk-border)] px-4 py-1 text-[11px] text-red-700">{createPlannedTripError}</p>
        ) : null}
        {workspaceMode === "detail" && load && followUpDispatchOpen ? (
          <FollowUpDispatchDialog
            load={load}
            drivers={drivers}
            trucks={trucks}
            trailers={trailers}
            onClose={() => setFollowUpDispatchOpen(false)}
            onSaved={() => {
              void getLoad(load.id).then((fresh) => setLoad(fresh));
            }}
          />
        ) : null}
        {commercialGatePrompt ? (
          <div
            className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4"
            role="dialog"
            aria-modal="true"
            aria-labelledby="workspace-commercial-gate-title"
          >
            <div className="max-w-md rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] p-4 shadow-lg">
              <h2
                id="workspace-commercial-gate-title"
                className="text-sm font-semibold text-[var(--trk-heading)]"
              >
                {commercialGatePrompt.mode === "save" ? "Save for later" : "Create load"}
              </h2>
              <p className="mt-2 whitespace-pre-wrap text-sm text-[var(--trk-text)]">
                {commercialGatePrompt.message}
              </p>
              <div className="mt-4 flex flex-wrap justify-end gap-2">
                <Button type="button" variant="secondary" onClick={() => closeCommercialGate("cancelled")}>
                  Cancel
                </Button>
                <Button type="button" onClick={() => closeCommercialGate("proceed")}>
                  {commercialGatePrimaryActionLabel(commercialGatePrompt.mode)}
                </Button>
              </div>
            </div>
          </div>
        ) : null}
        {draftConflict && isDraftWorkspace ? (
          <div className="border-t border-amber-900/50 bg-amber-950/25 px-4 py-2.5">
            <div className="mx-auto flex max-w-[1600px] flex-wrap items-start justify-between gap-3">
              <p className="flex-1 text-xs text-amber-100/95">
                <span className="font-semibold">Conflict:</span> Workspace draft was modified elsewhere
                {draftConflict.serverVersion != null ? (
                  <span className="text-amber-200/85"> (server version {draftConflict.serverVersion})</span>
                ) : null}. Your open edits were not overwritten.
              </p>
              <div className="flex shrink-0 flex-wrap gap-2">
                <Button type="button" variant="secondary" onClick={() => setDraftConflict(null)}>
                  Dismiss
                </Button>
                <Button type="button" onClick={() => void onReloadDraftVersion()}>
                  Reload server draft
                </Button>
              </div>
            </div>
          </div>
        ) : null}
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

      {lastParseEngineAttribution ||
      parseWarnings.length > 0 ||
      (lastParseAppliedLabels && lastParseAppliedLabels.length > 0) ? (
      <div className="shrink-0 border-b border-[var(--trk-border)] bg-[var(--trk-surface)]">
        {lastParseEngineAttribution ? (
          <div className="mx-auto max-w-[1600px] border-b border-[var(--trk-border)] bg-sky-50/80 px-4 py-2 dark:bg-sky-950/30">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-sky-800 dark:text-sky-200/90">
              Parse engine
            </div>
            <p className="mt-0.5 font-mono text-[11px] leading-snug text-sky-950 dark:text-sky-100">
              {lastParseEngineAttribution}
            </p>
          </div>
        ) : null}
        {parseWarnings.length > 0 ? (
          <div className="mx-auto max-w-[1600px] px-4 py-2">
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
      ) : null}

      <div className="mx-auto grid min-h-0 w-full max-w-[1600px] flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="flex max-h-[42vh] min-h-0 flex-col gap-3 overflow-y-auto border-b border-[var(--trk-border)] bg-[var(--trk-bg)] p-3 lg:sticky lg:top-0 lg:max-h-[calc(100vh-7rem)] lg:border-b-0 lg:border-r lg:border-[var(--trk-border)]">
          {workspaceMode === "intake" && hasIntakeThread ? (
            <div className="min-h-[160px] overflow-hidden rounded-lg border border-[var(--trk-border)]">
            <IntakeEmailRail
              threadId={intakeThreadId}
              loading={intakeLoading}
              error={intakeError}
              messages={intakeMessages}
            />
            </div>
          ) : (
            <div className="space-y-2">
            {workspacePdfPreviewUrl ? (
              <RateConfirmationPdfPanel
                objectUrl={workspacePdfPreviewUrl}
                openInNewTabPath={rateConPdfOpenInNewTabPath}
              />
            ) : null}
            <div className="overflow-hidden rounded-lg border border-[var(--trk-border)]">
            <ReferenceTextRail
              title={workspaceMode === "manual" ? "Rate confirmation" : "Source document"}
              hint={
                workspaceMode === "manual" ? (
                  workspaceReferenceText.trim() ? (
                    <>Extracted PDF text for verification. Click or tab a field to highlight matching lines.</>
                  ) : (
                    <>
                      Mirrors <code className="rounded bg-[var(--trk-border)] px-1 text-[10px]">internal_notes</code>. Edit in Notes below.
                      Click or tab fields to highlight lines.
                    </>
                  )
                ) : (
                  <>
                    Text from <code className="rounded bg-[var(--trk-border)] px-1 text-[10px]">internal_notes</code>. Edit in Notes below.
                  </>
                )
              }
              docLines={docLines}
              docScrollRef={docScrollRef}
              docLineRefs={docLineRefs}
              activeDocLine={activeDocLine}
            />
            </div>
            </div>
          )}
          {sectionConfig.visible.includes("Notes") ? (
            <LoadWorkspaceNotesPanel
              internalNotes={internalNotes}
              setInternalNotes={setInternalNotes}
              showOperationalNotesTimeline={workspaceMode !== "manual"}
              loadNotes={workspaceMode === "manual" ? [] : loadNotes}
              newNoteBody={workspaceMode === "manual" ? "" : newNoteBody}
              setNewNoteBody={workspaceMode === "manual" ? () => {} : setNewNoteBody}
              onAddNote={workspaceMode === "manual" ? () => {} : () => void onAddNote()}
              saving={saving || markReadyBusy}
            />
          ) : null}
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
            saving={saving || markReadyBusy}
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
            renderNotes={false}
            focusDoc={focusDoc}
            verificationTabIndex={verificationTabIndex}
            status={status}
            loadNumber={loadNumber}
            setLoadNumber={setLoadNumber}
            brokerId={brokerId}
            setBrokerId={setBrokerId}
            brokerContactId={brokerContactId}
            setBrokerContactId={setBrokerContactId}
            brokerNameSnapshot={brokerNameSnapshot}
            setBrokerNameSnapshot={setBrokerNameSnapshotTracked}
            brokerContactNameSnapshot={brokerContactNameSnapshot}
            setBrokerContactNameSnapshot={setBrokerContactNameSnapshot}
            brokerContactPhoneSnapshot={brokerContactPhoneSnapshot}
            setBrokerContactPhoneSnapshot={setBrokerContactPhoneSnapshot}
            brokerContactExtensionSnapshot={brokerContactExtensionSnapshot}
            setBrokerContactExtensionSnapshot={setBrokerContactExtensionSnapshot}
            brokerContactEmailSnapshot={brokerContactEmailSnapshot}
            setBrokerContactEmailSnapshot={setBrokerContactEmailSnapshot}
            brokerLoadReference={brokerLoadReference}
            setBrokerLoadReference={setBrokerLoadReferenceTracked}
            loadReferences={loadReferences}
            freightMode={freightMode}
            setFreightMode={setFreightModeTracked}
            equipmentType={equipmentType}
            setEquipmentType={setEquipmentTypeTracked}
            trailerType={trailerType}
            setTrailerType={setTrailerTypeTracked}
            trailerSize={trailerSize}
            setTrailerSize={setTrailerSizeTracked}
            commodity={commodity}
            setCommodity={setCommodityTracked}
            estimatedWeight={estimatedWeight}
            setEstimatedWeight={setEstimatedWeightTracked}
            hazmat={hazmat}
            setHazmat={setHazmat}
            temperatureRequirement={temperatureRequirement}
            setTemperatureRequirement={setTemperatureRequirementTracked}
            palletCaseCount={palletCaseCount}
            setPalletCaseCount={setPalletCaseCount}
            rate={rate}
            setRate={setRateTracked}
            customerRate={customerRate}
            setCustomerRate={setCustomerRateTracked}
            miles={miles}
            setMiles={setMilesTracked}
            driverId={driverId}
            truckId={truckId}
            trailerAssetId={trailerId}
            setDriverId={showManualDraftActions ? setDriverId : undefined}
            setTruckId={showManualDraftActions ? setTruckId : undefined}
            setTrailerAssetId={showManualDraftActions ? setTrailerId : undefined}
            assignmentWarnings={assignmentWarnings}
            onAssignmentDriverChange={showManualDraftActions ? onAssignmentDriverChange : undefined}
            onAssignmentTruckChange={showManualDraftActions ? onAssignmentTruckChange : undefined}
            activeTripId={workspaceMode === "detail" && load ? load.active_trip_id ?? null : null}
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

/** Remount when switching between /loads/new, /loads/draft/:id, and /loads/:id (Task 12). */
export default function LoadWorkspacePageRoute() {
  const location = useLocation();
  return <LoadWorkspacePage key={loadWorkspaceRemountKey(location.pathname)} />;
}
