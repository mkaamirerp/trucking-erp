/**
 * Single load workspace route — manual create, saved load edit, or intake verify/edit.
 * Field UI is only in LoadWorkspaceForm; this page owns layout, data, save, and side panel.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import Button from "@/components/Button";
import StatusBadge from "@/components/StatusBadge";
import {
  addLoadNote,
  confirmLoadDocumentSnapshot,
  createLoad,
  getEmailThreadMessages,
  getLoad,
  getLoadNotes,
  listBrokers,
  listBrokerContacts,
  listCustomsBrokers,
  listDrivers,
  listTrailers,
  listTrucks,
  updateLoad,
  type Broker,
  type BrokerContact,
  type CustomsBroker,
  type Driver,
  type InboxMessageItem,
  type Load,
  type LoadNote,
  type Trailer,
  type Truck,
} from "@/api";
import { OPS } from "@/routes";
import { formatRouteFromStops, sortedStops as sortStops } from "@/utils/loadStops";
import { LoadWorkspaceForm } from "@/loadWorkspace/LoadWorkspaceForm";
import {
  buildLoadPersistPayload,
  buildVerificationTabIndexMap,
  initialManualCreateStops,
  newDraftStop,
  sectionTitleClass,
  stopsToDraft,
  type DraftStop,
  type LoadWorkspaceMode,
} from "@/loadWorkspace/loadWorkspaceShared";

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

function IntakeEmailSidePanel({
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
  return (
    <div className="sticky top-20 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className={sectionTitleClass}>Source email</div>
      <p className="mb-3 text-xs text-gray-500">
        Thread #{threadId}. Cross-check against fields on the right; editing is only in the load form.
      </p>
      <div className="max-h-[min(70vh,36rem)] overflow-auto rounded-md border border-gray-200 bg-slate-900 p-3">
        {loading ? <div className="text-sm text-slate-400">Loading messages…</div> : null}
        {!loading && error ? <div className="text-sm text-red-400">{error}</div> : null}
        {!loading && !error && messages.length === 0 ? (
          <div className="text-sm text-slate-500">No messages in this thread.</div>
        ) : null}
        {!loading && !error
          ? messages.map((m) => {
              const outbound = (m.direction || "").toLowerCase() === "outbound";
              return (
                <div key={m.id} className={`mb-4 flex ${outbound ? "justify-end" : "justify-start"}`}>
                  <article
                    className={`w-full max-w-[820px] rounded-xl border p-3 ${
                      outbound ? "border-blue-800 bg-slate-950" : "border-slate-700 bg-slate-950/80"
                    }`}
                  >
                    <div className="mb-2 grid gap-1 text-xs text-slate-400 md:grid-cols-2">
                      <span>From: {m.from_email || "—"}</span>
                      <span className="md:text-right">{formatWhen(m.received_at || m.sent_at || m.created_at)}</span>
                      <span className="md:col-span-2">To: {recipientPreview(m.to_json)}</span>
                      {m.subject ? <span className="md:col-span-2">Subject: {m.subject}</span> : null}
                    </div>
                    <p className="whitespace-pre-wrap text-sm leading-6 text-slate-100">
                      {m.body_text || m.snippet || "No message body available."}
                    </p>
                    {m.attachments && m.attachments.length > 0 ? (
                      <ul className="mt-2 space-y-1 text-xs text-slate-400">
                        {m.attachments.map((a) => (
                          <li key={a.id}>
                            <span className="text-slate-200">{a.filename || a.external_attachment_id}</span>
                            {a.mime_type ? <span className="text-slate-500"> · {a.mime_type}</span> : null}
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
      <dt className="text-xs text-gray-500">{label}</dt>
      <dd className={`mt-0.5 text-gray-900 ${mono ? "font-mono text-xs break-all" : ""}`}>{value || "—"}</dd>
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
  const workspaceMode: LoadWorkspaceMode = isManual ? "manual" : hasIntakeThread ? "intake" : "detail";

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
  const [error, setError] = useState<string | null>(null);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [customsMessage, setCustomsMessage] = useState<string | null>(null);

  const [intakeMessages, setIntakeMessages] = useState<InboxMessageItem[]>([]);
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
  const docScrollRef = useRef<HTMLDivElement | null>(null);
  const docLineRefs = useRef<Map<number, HTMLDivElement | null>>(new Map());
  const [activeDocLine, setActiveDocLine] = useState<number | null>(null);

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
      setIntakeError(null);
      setIntakeLoading(false);
      return;
    }
    let cancelled = false;
    setIntakeLoading(true);
    setIntakeError(null);
    getEmailThreadMessages(intakeThreadId)
      .then((msgs) => {
        if (!cancelled) setIntakeMessages(msgs ?? []);
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
    setSaveMessage(null);
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
      setSaveMessage((e as Error)?.message || "Could not create load");
    } finally {
      setSaving(false);
    }
  }

  async function onSave() {
    if (!load) return;
    setSaving(true);
    setSaveMessage(null);
    setError(null);
    try {
      const updated = await updateLoad(
        load.id,
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
      );
      setLoad(updated);
      hydrateFromLoad(updated);
      setSaveMessage("Saved.");
    } catch (e: unknown) {
      setSaveMessage((e as Error)?.message || "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function onCustomsBrokerSelect(ev: React.ChangeEvent<HTMLSelectElement>) {
    if (!load || load.document_snapshot_confirmed_at) return;
    const v = ev.target.value;
    const next = v === "" ? null : Number(v);
    setCustomsBrokerId(next);
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await updateLoad(load.id, { customs_broker_id: next });
      setLoad(updated);
      setCustomsBrokerId(updated.customs_broker_id ?? null);
      setCustomsMessage("Customs broker updated.");
    } catch (e: unknown) {
      setCustomsMessage((e as Error)?.message || "Could not update customs broker");
    } finally {
      setSaving(false);
    }
  }

  async function onConfirmSnapshot() {
    if (!load) return;
    setSaving(true);
    setCustomsMessage(null);
    try {
      const updated = await confirmLoadDocumentSnapshot(load.id);
      setLoad(updated);
      hydrateFromLoad(updated);
      setCustomsMessage("Document snapshot confirmed.");
    } catch (e: unknown) {
      setCustomsMessage((e as Error)?.message || "Confirm failed");
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
      setSaveMessage((e as Error)?.message || "Could not add note");
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
      <div className="flex min-h-[40vh] flex-col items-center justify-center gap-2 p-4 text-gray-600">
        <div
          className="h-9 w-9 animate-spin rounded-full border-2 border-gray-200 border-t-indigo-600"
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
        <p className="text-sm text-gray-600">Load not found</p>
        <Button variant="secondary" onClick={() => navigate(OPS.LOADS)} className="mt-2">
          Back to Loads
        </Button>
      </div>
    );
  }

  const confirmed = Boolean(load?.document_snapshot_confirmed_at);
  const routeSubtitle = load ? formatRouteFromStops(load.stops) : "—";
  const hasActiveDispatchTrip = load?.active_dispatch_trip_id != null;

  const shellBg = workspaceMode === "manual" ? "bg-slate-50" : "bg-gray-50";

  return (
    <div className={`min-h-screen ${shellBg} text-gray-900`}>
      <header className="sticky top-0 z-10 border-b border-gray-200 bg-white shadow-sm">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="min-w-0 flex-1">
            {workspaceMode === "manual" ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-bold tracking-tight text-gray-900">New load</h1>
                  <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-slate-600 ring-1 ring-inset ring-slate-200/80">
                    Manual entry
                  </span>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Save creates the load and opens it for ongoing edits.
                </p>
              </>
            ) : workspaceMode === "intake" ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-bold text-gray-900">
                    Load {loadNumber || load!.load_number}
                  </h1>
                  <StatusBadge status={status} />
                  <span className="inline-flex items-center rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-amber-900 ring-1 ring-inset ring-amber-200/80">
                    Intake verify
                  </span>
                  {load!.review_required ? (
                    <span
                      className="rounded border px-2 py-0.5 text-[11px] font-semibold text-amber-900"
                      style={{ background: "rgba(245,166,35,0.12)", borderColor: "rgba(245,166,35,0.35)" }}
                    >
                      Review required
                    </span>
                  ) : null}
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  Cross-check email on the left; save updates this load.
                </p>
              </>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-lg font-bold text-gray-900">Load {loadNumber || load!.load_number}</h1>
                  <StatusBadge status={status} />
                  {load!.review_required ? (
                    <span
                      className="rounded border px-2 py-0.5 text-[11px] font-semibold text-amber-900"
                      style={{ background: "rgba(245,166,35,0.12)", borderColor: "rgba(245,166,35,0.35)" }}
                    >
                      Review required
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-gray-600">
                  {load!.trip_number?.trim() ? (
                    <span className="text-gray-700">
                      Trip <span className="font-mono">{load!.trip_number.trim()}</span>
                    </span>
                  ) : (
                    <span className="italic text-gray-500">No trip number yet</span>
                  )}
                  <span className="text-gray-500">·</span>
                  <span>{hasActiveDispatchTrip ? "Dispatch trip linked" : "No dispatch trip linked"}</span>
                  {routeSubtitle !== "—" ? (
                    <>
                      <span className="text-gray-500">·</span>
                      <span>{routeSubtitle}</span>
                    </>
                  ) : null}
                </div>
                {(load!.created_at || load!.updated_at) && (
                  <p className="mt-1 text-[11px] text-gray-500">
                    {load!.created_at ? <>Created {new Date(load!.created_at).toLocaleString()}</> : null}
                    {load!.created_at && load!.updated_at ? " · " : null}
                    {load!.updated_at ? <>Updated {new Date(load!.updated_at).toLocaleString()}</> : null}
                  </p>
                )}
              </>
            )}
          </div>
          <div className="flex w-full flex-col gap-2 sm:w-auto sm:items-end">
            {workspaceMode === "manual" && saveMessage ? (
              <div className="w-full max-w-md rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800 sm:text-right">
                {saveMessage}
              </div>
            ) : workspaceMode !== "manual" && saveMessage ? (
              <span className="text-xs text-gray-600">{saveMessage}</span>
            ) : null}
            <div className="flex flex-wrap items-center justify-end gap-2">
              <Button variant="secondary" type="button" onClick={() => navigate(OPS.LOADS)}>
                Back to list
              </Button>
              {workspaceMode === "intake" ? (
                <Button variant="secondary" type="button" onClick={() => navigate(OPS.INTAKE)}>
                  Back to intake
                </Button>
              ) : null}
              <Button variant="secondary" type="button" onClick={() => navigate(OPS.DISPATCH)}>
                Dispatch
              </Button>
              {workspaceMode === "manual" ? (
                <Button variant="primary" type="button" disabled={saving} onClick={() => void onCreate()}>
                  {saving ? "Creating…" : "Create load"}
                </Button>
              ) : (
                <Button variant="primary" type="button" disabled={saving} onClick={() => void onSave()}>
                  {saving ? "Saving…" : "Save load"}
                </Button>
              )}
            </div>
          </div>
        </div>
      </header>

      {workspaceMode !== "manual" && load && (load.review_required || contextSummary) ? (
        <div
          className="border-b border-amber-200/60 bg-amber-50/90 px-4 py-2 text-xs text-amber-950"
          style={!load.review_required ? { background: "rgba(245,166,35,0.06)" } : undefined}
        >
          <div className="mx-auto max-w-7xl">
            {load.review_required ? (
              <span className="font-semibold">
                Review required — verify intake / broker match before relying on this load.
              </span>
            ) : null}
            {load.review_required && contextSummary ? <span className="mx-2 text-amber-800">·</span> : null}
            {contextSummary ? <span className="text-amber-900">{contextSummary}</span> : null}
          </div>
        </div>
      ) : null}

      <div className="mx-auto grid max-w-7xl grid-cols-1 gap-6 px-4 py-6 lg:grid-cols-12">
        <aside className="lg:col-span-4">
          {workspaceMode === "intake" && hasIntakeThread ? (
            <IntakeEmailSidePanel
              threadId={intakeThreadId}
              loading={intakeLoading}
              error={intakeError}
              messages={intakeMessages}
            />
          ) : workspaceMode === "manual" ? (
            <div className="sticky top-24 rounded-xl border border-gray-200/90 bg-white p-5 shadow-sm ring-1 ring-black/[0.02]">
              <div className={sectionTitleClass}>Rate confirmation</div>
              <p className="mb-3 text-xs leading-relaxed text-gray-500">
                Paste rate confirmation text here. Lines highlight as you tab through the form. Saved as{" "}
                <code className="rounded bg-slate-100 px-1 py-0.5 text-[10px] text-slate-700">internal_notes</code> on
                create.
              </p>
              {docLines.length ? (
                <div
                  ref={docScrollRef}
                  className="max-h-[min(70vh,36rem)] overflow-auto rounded-lg border border-gray-200 bg-slate-50/80 p-2 text-xs leading-snug text-gray-900 font-mono shadow-inner"
                >
                  {docLines.map((line, i) => (
                    <div
                      key={i}
                      ref={(el) => {
                        docLineRefs.current.set(i, el);
                      }}
                      className="whitespace-pre-wrap break-words px-2 py-0.5 rounded"
                      style={activeDocLine === i ? { background: "rgba(245,166,35,0.18)" } : undefined}
                    >
                      {line || " "}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="rounded-lg border border-dashed border-gray-200 bg-slate-50/50 px-3 py-4 text-sm text-gray-500">
                  Paste rate confirmation text in{" "}
                  <span className="font-medium text-gray-700">Documents &amp; notes → Internal notes</span> to see it
                  here.
                </p>
              )}
            </div>
          ) : (
            <div className="sticky top-20 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
              <div className={sectionTitleClass}>Source document (PDF excerpt)</div>
              <p className="mb-2 text-xs text-gray-500">
                Text stored on the load (<code className="text-[10px]">internal_notes</code>). Edit the full field under{" "}
                <strong>Notes</strong> — this panel updates as you type.
              </p>
              {docLines.length ? (
                <div
                  ref={docScrollRef}
                  className="max-h-[min(70vh,36rem)] overflow-auto rounded-md border border-gray-200 bg-gray-50 p-2 text-xs leading-snug text-gray-900 font-mono"
                >
                  {docLines.map((line, i) => (
                    <div
                      key={i}
                      ref={(el) => {
                        docLineRefs.current.set(i, el);
                      }}
                      className="whitespace-pre-wrap break-words px-2 py-0.5 rounded"
                      style={activeDocLine === i ? { background: "rgba(245,166,35,0.18)" } : undefined}
                    >
                      {line || " "}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-sm italic text-gray-500">No excerpt yet — paste or save from intake under Notes.</p>
              )}
            </div>
          )}
        </aside>

        <main className="space-y-6 lg:col-span-8">
          {workspaceMode !== "manual" && load ? (
            <div className="rounded-xl border border-gray-200 bg-white shadow-sm">
              <div className="border-b border-gray-100 px-4 py-3 text-xs font-semibold uppercase tracking-wide text-gray-500">
                Load context
              </div>
              <div className="px-4 py-4 text-sm">
                <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <ContextRow label="Trip number" value={load.trip_number?.trim() || "—"} mono />
                  <ContextRow label="Dispatch trip" value={hasActiveDispatchTrip ? "Linked" : "—"} />
                  <ContextRow label="Match method" value={load.broker_match_method?.replace(/_/g, " ") || "—"} />
                  <ContextRow label="Confidence tier" value={load.broker_match_confidence_tier || "—"} />
                </dl>
                {load.broker_match_explanation?.trim() ? (
                  <p className="mt-3 whitespace-pre-wrap text-xs text-gray-700">{load.broker_match_explanation.trim()}</p>
                ) : null}
                {load.is_duplicate_of_load_id != null ? (
                  <p className="mt-3 text-xs">
                    <span className="text-gray-500">Possible duplicate — </span>
                    <Link
                      to={OPS.LOAD_DETAIL(load.is_duplicate_of_load_id)}
                      className="font-medium text-indigo-600 hover:underline"
                    >
                      Open linked load
                    </Link>
                  </p>
                ) : null}
                <div className="mt-4 border-t border-gray-100 pt-3">
                  <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Resolved labels</p>
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
                  <div className="mt-4 border-t border-gray-100 pt-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">
                      Stop schedules (read-only)
                    </p>
                    <ul className="space-y-1 text-xs text-gray-700">
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
                  <div className="mt-4 border-t border-gray-100 pt-3">
                    <p className="mb-2 text-[10px] font-semibold uppercase tracking-wide text-gray-500">Customs snapshot</p>
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
                      <ul className="mt-2 space-y-0.5 text-xs text-gray-600">
                        <li>{load.customs_snapshot.legal_name_snapshot || "—"}</li>
                        <li>{load.customs_snapshot.phone_primary_snapshot || ""}</li>
                        <li>{load.customs_snapshot.generic_email_snapshot || ""}</li>
                      </ul>
                    )}
                  </div>
                )}
              </div>
            </div>
          ) : null}

          <LoadWorkspaceForm
            mode={workspaceMode}
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
        </main>
      </div>
    </div>
  );
}
