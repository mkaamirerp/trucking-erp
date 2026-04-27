import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  clearLoadLabRuns,
  getLoadLabRun,
  listBrokers,
  listCustomsBrokers,
  listDrivers,
  listLoadLabRuns,
  listTrailers,
  listTrucks,
  LoadDocumentParseResponse,
  LoadLabRun,
  postLoadLabOpenaiSmoke,
  postLoadLabRecomputeReview,
  postLoadLabSemanticExtract,
  uploadLoadLabRun,
  type Broker,
  type BrokerContact,
  type CustomsBroker,
  type Driver,
  type Trailer,
  type Truck,
} from "@/api";
import { useMe, isTenantAdmin } from "@/hooks/useMe";
import { LoadWorkspaceForm } from "@/loadWorkspace/LoadWorkspaceForm";
import { applyLoadDocumentParseResponse } from "@/loadWorkspace/applyLoadDocumentParseResponse";
import {
  buildVerificationTabIndexMap,
  emptyIntakeProposed,
  initialManualCreateStops,
  newDraftStop,
  SECTION_CONFIG,
  type DraftStop,
} from "@/loadWorkspace/loadWorkspaceShared";

function JsonBlock({ value, title }: { value: unknown; title: string }) {
  const text =
    value === null || value === undefined
      ? "—"
      : typeof value === "string"
        ? value
        : JSON.stringify(value, null, 2);
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">{title}</div>
      <pre className="max-h-64 overflow-auto rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-3 text-[11px] leading-snug text-[var(--trk-text)]">
        {text}
      </pre>
    </div>
  );
}

const LAB_GROUP_LABELS: Record<string, string> = {
  broker_identity: "Broker identity",
  broker_contact: "Broker contact",
  references: "References",
  equipment: "Equipment",
  money: "Money / miles",
  stops: "Stops",
  customs: "Customs",
};

function ReviewStateBanner({ status, summary }: { status: string | null | undefined; summary: string | null | undefined }) {
  const s = status ?? "not_applicable";
  const border =
    s === "blocked"
      ? "border-red-500/50 bg-red-500/10"
      : s === "review_required"
        ? "border-amber-500/50 bg-amber-500/10"
        : s === "candidate_ok"
          ? "border-emerald-500/45 bg-emerald-500/10"
          : "border-[var(--trk-border)] bg-[var(--trk-surface)]/80";
  return (
    <div className={`rounded-md border px-3 py-2 text-sm ${border}`}>
      <div className="font-semibold text-[var(--trk-heading)]">Lab review state: {s}</div>
      {summary ? <p className="mt-1 text-xs text-[var(--trk-text-muted)]">{summary}</p> : null}
      <p className="mt-1 text-[10px] leading-snug text-[var(--trk-text-muted)]">
        Heuristic only — prefer review when unsure. Does not promote or write loads.
      </p>
    </div>
  );
}

function ConfidenceGroups({ lab }: { lab: Record<string, unknown> | null | undefined }) {
  if (!lab || typeof lab !== "object") {
    return <p className="text-xs text-[var(--trk-text-muted)]">No confidence block yet (run semantic extract or recompute review).</p>;
  }
  const doc = lab.document as { level?: string; reasons?: string[] } | undefined;
  const groups = lab.groups as Record<string, { level?: string; reasons?: string[] }> | undefined;
  const engine = typeof lab.engine_version === "string" ? lab.engine_version : null;
  return (
    <div className="space-y-2">
      {engine ? (
        <div className="text-[10px] text-[var(--trk-text-muted)]">
          Engine: <span className="font-mono">{engine}</span>
        </div>
      ) : null}
      {doc ? (
        <div className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)]/50 px-2 py-1.5 text-xs">
          <span className="font-semibold text-[var(--trk-text)]">Document</span>{" "}
          <span className="text-[var(--trk-text-muted)]">· {doc.level ?? "—"}</span>
          {doc.reasons?.length ? (
            <ul className="mt-1 list-inside list-disc text-[10px] text-[var(--trk-text-muted)]">
              {doc.reasons.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {groups && Object.keys(groups).length > 0 ? (
        <ul className="space-y-1.5">
          {Object.entries(groups).map(([key, g]) => (
            <li
              key={key}
              className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)]/50 px-2 py-1.5 text-xs"
            >
              <span className="font-semibold text-[var(--trk-text)]">{LAB_GROUP_LABELS[key] ?? key}</span>{" "}
              <span className="text-[var(--trk-text-muted)]">· {g.level ?? "—"}</span>
              {g.reasons?.length ? (
                <ul className="mt-1 list-inside list-disc text-[10px] text-[var(--trk-text-muted)]">
                  {g.reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function ContradictionsList({ items }: { items: unknown[] | null | undefined }) {
  if (!items?.length) {
    return <p className="text-xs text-[var(--trk-text-muted)]">No contradiction flags recorded.</p>;
  }
  return (
    <ul className="space-y-2">
      {items.map((raw, i) => {
        const row = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
        const id = typeof row.id === "string" ? row.id : `flag_${i}`;
        const sev = typeof row.severity === "string" ? row.severity : "—";
        const detail = typeof row.detail === "string" ? row.detail : JSON.stringify(raw);
        return (
          <li key={id + i} className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)]/50 px-2 py-1.5 text-xs">
            <span className="font-mono text-[10px] text-[var(--trk-text-muted)]">{id}</span>{" "}
            <span className="text-amber-200/90">({sev})</span>
            <p className="mt-0.5 text-[11px] text-[var(--trk-text)]">{detail}</p>
          </li>
        );
      })}
    </ul>
  );
}

function TextPreview({ text, title }: { text: string | null; title: string }) {
  const body = (text ?? "").trim();
  const preview = body ? (body.length > 6000 ? `${body.slice(0, 6000)}\n\n…(truncated preview)…` : body) : "—";
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">{title}</div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-3 text-[11px] leading-snug text-[var(--trk-text)]">
        {preview}
      </pre>
    </div>
  );
}

function labParseResponseShape(raw: unknown): LoadDocumentParseResponse | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (!o.extracted || typeof o.extracted !== "object") return null;
  if (typeof o.raw_text !== "string") return null;
  return raw as LoadDocumentParseResponse;
}

function resetWorkspaceFormState(args: {
  setStatus: (v: string) => void;
  setLoadNumber: (v: string) => void;
  setBrokerId: (v: number | null) => void;
  setBrokerContactId: (v: number | null) => void;
  setBrokerContacts: (v: BrokerContact[]) => void;
  setBrokerNameSnapshot: (v: string) => void;
  setBrokerContactNameSnapshot: (v: string) => void;
  setBrokerContactPhoneSnapshot: (v: string) => void;
  setBrokerContactExtensionSnapshot: (v: string) => void;
  setBrokerContactEmailSnapshot: (v: string) => void;
  setBrokerLoadReference: (v: string) => void;
  setFreightMode: (v: string) => void;
  setEquipmentType: (v: string) => void;
  setTrailerType: (v: string) => void;
  setTrailerSize: (v: string) => void;
  setCommodity: (v: string) => void;
  setEstimatedWeight: (v: string) => void;
  setHazmat: (v: "unset" | "yes" | "no") => void;
  setTemperatureRequirement: (v: string) => void;
  setPalletCaseCount: (v: string) => void;
  setRate: (v: string) => void;
  setCustomerRate: (v: string) => void;
  setMiles: (v: string) => void;
  setDriverId: (v: number | null) => void;
  setTruckId: (v: number | null) => void;
  setTrailerAssetId: (v: number | null) => void;
  setCustomsBrokerId: (v: number | null) => void;
  setInternalNotes: (v: string) => void;
  setDraftStops: (v: DraftStop[]) => void;
}) {
  args.setStatus("unassigned");
  args.setLoadNumber("");
  args.setBrokerId(null);
  args.setBrokerContactId(null);
  args.setBrokerContacts([]);
  args.setBrokerNameSnapshot("");
  args.setBrokerContactNameSnapshot("");
  args.setBrokerContactPhoneSnapshot("");
  args.setBrokerContactExtensionSnapshot("");
  args.setBrokerContactEmailSnapshot("");
  args.setBrokerLoadReference("");
  args.setFreightMode("");
  args.setEquipmentType("");
  args.setTrailerType("");
  args.setTrailerSize("");
  args.setCommodity("");
  args.setEstimatedWeight("");
  args.setHazmat("unset");
  args.setTemperatureRequirement("");
  args.setPalletCaseCount("");
  args.setRate("");
  args.setCustomerRate("");
  args.setMiles("");
  args.setDriverId(null);
  args.setTruckId(null);
  args.setTrailerAssetId(null);
  args.setCustomsBrokerId(null);
  args.setInternalNotes("");
  args.setDraftStops(initialManualCreateStops());
}

export default function LoadLabPage() {
  const { me } = useMe();
  const canOpenaiSmoke = isTenantAdmin(me?.roles);
  const fileRef = useRef<HTMLInputElement>(null);
  const [runs, setRuns] = useState<LoadLabRun[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<LoadLabRun | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forceRerun, setForceRerun] = useState(false);
  const [smokeBusy, setSmokeBusy] = useState(false);
  const [smokeMsg, setSmokeMsg] = useState<string | null>(null);
  const [semanticBusy, setSemanticBusy] = useState(false);
  const [semanticNote, setSemanticNote] = useState<string | null>(null);
  const [forceSemantic, setForceSemantic] = useState(false);
  const [semanticMode, setSemanticMode] = useState<"guarded" | "ai_validate_only" | "pure_ai">("guarded");
  const [semanticResponseContract, setSemanticResponseContract] = useState<"truckerjson" | "critical_v1_1">(
    "truckerjson"
  );
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewNote, setReviewNote] = useState<string | null>(null);
  const [hydrateError, setHydrateError] = useState<string | null>(null);
  const [listsLoaded, setListsLoaded] = useState(false);
  const [customsBrokers, setCustomsBrokers] = useState<CustomsBroker[]>([]);
  const [freightBrokers, setFreightBrokers] = useState<Broker[]>([]);
  const [brokerContacts, setBrokerContacts] = useState<BrokerContact[]>([]);
  const [drivers, setDrivers] = useState<Driver[]>([]);
  const [trucks, setTrucks] = useState<Truck[]>([]);
  const [trailers, setTrailers] = useState<Trailer[]>([]);

  const [status, setStatus] = useState("unassigned");
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
  const [trailerAssetId, setTrailerAssetId] = useState<number | null>(null);
  const [customsBrokerId, setCustomsBrokerId] = useState<number | null>(null);
  const [internalNotes, setInternalNotes] = useState("");
  const [draftStops, setDraftStops] = useState<DraftStop[]>(() => initialManualCreateStops());

  const refreshList = useCallback(async () => {
    const list = await listLoadLabRuns(40);
    setRuns(list);
  }, []);

  useEffect(() => {
    void refreshList().catch((e) => setError(e instanceof Error ? e.message : "Failed to list runs"));
  }, [refreshList]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [customsPaged, brPaged, dr, trk, trl] = await Promise.all([
          listCustomsBrokers({ page: 1, size: 200, include_inactive: false }),
          listBrokers({ page: 1, size: 200, sort: "name_asc" }),
          listDrivers({ limit: 500, include_inactive: false }),
          listTrucks({ page: 1, size: 200, status: ["active"] }),
          listTrailers({ page: 1, size: 200, status: ["active"] }),
        ]);
        if (cancelled) return;
        setCustomsBrokers(customsPaged.items || []);
        setFreightBrokers(brPaged.items || []);
        setDrivers(dr);
        setTrucks(trk.items || []);
        setTrailers(trl.items || []);
        setListsLoaded(true);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load workspace lists");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    setError(null);
    const r = await getLoadLabRun(id);
    setDetail(r);
  }, []);

  useEffect(() => {
    setSemanticNote(null);
    setReviewNote(null);
    setHydrateError(null);
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedId).catch((e) => setError(e instanceof Error ? e.message : "Failed to load run"));
  }, [selectedId, loadDetail]);

  useEffect(() => {
    if (!detail || !listsLoaded) return;
    let cancelled = false;
    resetWorkspaceFormState({
      setStatus,
      setLoadNumber,
      setBrokerId,
      setBrokerContactId,
      setBrokerContacts,
      setBrokerNameSnapshot,
      setBrokerContactNameSnapshot,
      setBrokerContactPhoneSnapshot,
      setBrokerContactExtensionSnapshot,
      setBrokerContactEmailSnapshot,
      setBrokerLoadReference,
      setFreightMode,
      setEquipmentType,
      setTrailerType,
      setTrailerSize,
      setCommodity,
      setEstimatedWeight,
      setHazmat,
      setTemperatureRequirement,
      setPalletCaseCount,
      setRate,
      setCustomerRate,
      setMiles,
      setDriverId,
      setTruckId,
      setTrailerAssetId,
      setCustomsBrokerId,
      setInternalNotes,
      setDraftStops,
    });
    const parsed = labParseResponseShape(detail.parse_response);
    if (!parsed) {
      if (detail.parse_response != null) {
        setHydrateError("Candidate JSON is missing extracted/raw_text — cannot hydrate workspace form.");
      }
      return;
    }
    void (async () => {
      try {
        await applyLoadDocumentParseResponse(parsed, {
          setBrokerNameSnapshot,
          setBrokerId,
          setBrokerContactId,
          setBrokerContacts,
          setBrokerContactNameSnapshot,
          setBrokerContactPhoneSnapshot,
          setBrokerContactEmailSnapshot,
          setBrokerLoadReference,
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
          setDraftStops,
        });
        if (!cancelled) setHydrateError(null);
      } catch (e) {
        if (!cancelled) setHydrateError(e instanceof Error ? e.message : "Hydrate failed");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [detail, listsLoaded]);

  const sortedDraftStops = useMemo(
    () => [...draftStops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0)),
    [draftStops],
  );

  const verificationTabIndex = useMemo(() => buildVerificationTabIndexMap(sortedDraftStops), [sortedDraftStops]);

  const focusDocNoop = useCallback(() => {}, []);

  function updateStop(key: string, patch: Partial<DraftStop>) {
    setDraftStops((rows) => rows.map((r) => (r._key === key ? { ...r, ...patch } : r)));
  }
  function removeStop(key: string) {
    setDraftStops((rows) => rows.filter((r) => r._key !== key));
  }
  function addStop() {
    const maxSeq = draftStops.length === 0 ? 0 : Math.max(...draftStops.map((s) => s.sequence ?? 0)) + 1;
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

  const onUpload = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await uploadLoadLabRun(file, { forceRerun });
      setSelectedId(res.run.id);
      await refreshList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const onClearAllRuns = async () => {
    if (!canOpenaiSmoke) {
      setError("Tenant admin required");
      return;
    }
    if (!window.confirm("Delete ALL Load Lab runs for this tenant? This cannot be undone.")) return;
    setBusy(true);
    setError(null);
    try {
      const r = await clearLoadLabRuns();
      setSelectedId(null);
      setDetail(null);
      await refreshList();
      setSmokeMsg(`Cleared runs: ${r.deleted}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to clear runs");
    } finally {
      setBusy(false);
    }
  };

  const onRecomputeReview = async () => {
    if (selectedId == null) return;
    setReviewBusy(true);
    setReviewNote(null);
    setError(null);
    try {
      const r = await postLoadLabRecomputeReview(selectedId);
      setDetail(r);
      await refreshList();
      setReviewNote(`Review recomputed: ${r.lab_review_status ?? "—"}`);
    } catch (e) {
      setReviewNote(e instanceof Error ? e.message : "Review recompute failed");
    } finally {
      setReviewBusy(false);
    }
  };

  const onSemanticExtract = async () => {
    if (selectedId == null) return;
    setSemanticBusy(true);
    setSemanticNote(null);
    setError(null);
    try {
      const r = await postLoadLabSemanticExtract(selectedId, {
        force: forceSemantic,
        mode: semanticMode,
        responseContract: semanticResponseContract,
      });
      setDetail(r);
      await refreshList();
      const st = r.semantic_extract_status ?? "—";
      setSemanticNote(`Semantic extract finished: ${st}`);
    } catch (e) {
      setSemanticNote(e instanceof Error ? e.message : "Semantic extract request failed");
    } finally {
      setSemanticBusy(false);
    }
  };

  const onOpenaiSmoke = async () => {
    setSmokeBusy(true);
    setSmokeMsg(null);
    setError(null);
    try {
      const r = await postLoadLabOpenaiSmoke();
      setSmokeMsg(
        r.ok
          ? `OpenAI OK (HTTP ${r.http_status ?? "?"}) — sample model: ${r.sample_model_id ?? "—"}`
          : `OpenAI check failed: ${r.detail ?? "unknown"}`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "OpenAI smoke failed");
    } finally {
      setSmokeBusy(false);
    }
  };

  const btn =
    "rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5 text-xs font-semibold text-[var(--trk-text)] hover:border-[var(--trk-border-strong)] disabled:opacity-50";

  const readability =
    detail?.status === "ocr_required"
      ? "ocr_required"
      : detail?.status === "text_extracted"
        ? "text_usable"
        : detail?.status === "failed"
          ? "failed"
          : null;

  const rawText =
    detail?.normalized_package && typeof detail.normalized_package === "object"
      ? (detail.normalized_package as Record<string, unknown>)["raw_full_text"]
      : null;
  const rawTextStr = typeof rawText === "string" ? rawText : null;

  const sectionConfig = SECTION_CONFIG.manual;
  const parseReferences =
    detail?.parse_response &&
    typeof detail.parse_response === "object" &&
    (detail.parse_response as Record<string, unknown>).extracted &&
    typeof (detail.parse_response as Record<string, unknown>).extracted === "object"
      ? ((detail.parse_response as Record<string, unknown>).extracted as Record<string, unknown>).references
      : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold text-[var(--trk-heading)]">Load Lab</h1>
        <p className="mt-1 max-w-3xl text-sm text-[var(--trk-text-muted)]">
          Same load workspace form as production (read-only) plus isolated run metadata, semantic extract, and lab
          review. Nothing here writes operational loads.
        </p>
      </div>

      {error ? (
        <div className="rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">{error}</div>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <input ref={fileRef} type="file" accept=".pdf,application/pdf" className="hidden" onChange={(e) => void onUpload(e.target.files?.[0] ?? null)} />
        <button type="button" className={btn} disabled={busy} onClick={() => fileRef.current?.click()}>
          {busy ? "Working…" : "Upload PDF"}
        </button>
        <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--trk-text-muted)]">
          <input type="checkbox" checked={forceRerun} onChange={(e) => setForceRerun(e.target.checked)} />
          Force new run (skip hash/version reuse)
        </label>
        {canOpenaiSmoke ? (
          <div className="flex flex-wrap items-center gap-2 border-l border-[var(--trk-border)] pl-3">
            <button type="button" className={btn} disabled={busy || smokeBusy} onClick={() => void onOpenaiSmoke()}>
              {smokeBusy ? "OpenAI…" : "Test OpenAI connectivity"}
            </button>
            <button type="button" className={btn} disabled={busy} onClick={() => void onClearAllRuns()}>
              Clear all runs
            </button>
            {smokeMsg ? <span className="max-w-md text-xs text-[var(--trk-text-muted)]">{smokeMsg}</span> : null}
          </div>
        ) : null}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,260px)_1fr]">
        <div className="space-y-2">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">Recent runs</div>
          <ul className="max-h-[70vh] space-y-1 overflow-auto rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] p-2">
            {runs.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => setSelectedId(r.id)}
                  className={`w-full rounded px-2 py-1.5 text-left text-xs ${
                    selectedId === r.id ? "bg-[var(--trk-border)] text-[var(--trk-text)]" : "hover:bg-[var(--trk-border)]/50"
                  }`}
                >
                  <div className="font-mono text-[10px] text-[var(--trk-text-muted)]">#{r.id}</div>
                  <div className="truncate">{r.filename}</div>
                  <div className="text-[10px] text-[var(--trk-text-muted)]">
                    {r.status}
                    {r.extraction_path ? ` · ${r.extraction_path}` : ""}
                    {r.lab_review_status ? ` · review:${r.lab_review_status}` : ""}
                  </div>
                </button>
              </li>
            ))}
            {runs.length === 0 ? <li className="px-2 py-4 text-xs text-[var(--trk-text-muted)]">No runs yet.</li> : null}
          </ul>
        </div>

        <div className="min-w-0 space-y-4">
          {!detail ? (
            <p className="text-sm text-[var(--trk-text-muted)]">Select a run or upload a PDF.</p>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold text-[var(--trk-heading)]">Run #{detail.id}</span>
                <span className="text-[var(--trk-text-muted)]">{detail.status}</span>
                {detail.semantic_extract_status ? (
                  <span className="rounded border border-[var(--trk-border)] px-2 py-0.5 text-[10px] text-[var(--trk-text-muted)]">
                    semantic: {detail.semantic_extract_status}
                  </span>
                ) : null}
                <span className="ml-auto flex flex-wrap items-center gap-2 text-xs text-[var(--trk-text-muted)]">
                  Mode
                  <select
                    className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-xs text-[var(--trk-text)]"
                    value={semanticMode}
                    onChange={(e) => setSemanticMode(e.target.value as typeof semanticMode)}
                    disabled={semanticBusy}
                  >
                    <option value="guarded">Guarded (repairs on)</option>
                    <option value="ai_validate_only">AI + validate only (no repairs)</option>
                    <option value="pure_ai">Pure AI (schema only, no diagnostics, no repairs)</option>
                  </select>
                  Contract
                  <select
                    className="rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1 text-xs text-[var(--trk-text)]"
                    value={semanticResponseContract}
                    onChange={(e) => setSemanticResponseContract(e.target.value as typeof semanticResponseContract)}
                    disabled={semanticBusy}
                    title="Response JSON schema: legacy full parse vs dispatch-critical v1.1"
                  >
                    <option value="truckerjson">Full parse (legacy)</option>
                    <option value="critical_v1_1">Dispatch-critical v1.1</option>
                  </select>
                </span>
              </div>

              {readability === "text_usable" ? (
                <div className="flex flex-wrap items-center gap-3 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)]/60 p-3">
                  <button type="button" className={btn} disabled={semanticBusy} onClick={() => void onSemanticExtract()}>
                    {semanticBusy ? "OpenAI extraction…" : "Run OpenAI extraction"}
                  </button>
                  <label className="flex cursor-pointer items-center gap-2 text-xs text-[var(--trk-text-muted)]">
                    <input type="checkbox" checked={forceSemantic} onChange={(e) => setForceSemantic(e.target.checked)} />
                    Force re-run (ignore cached success)
                  </label>
                  {semanticNote ? <span className="text-xs text-[var(--trk-text-muted)]">{semanticNote}</span> : null}
                </div>
              ) : null}

              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(280px,340px)]">
                <div className="min-w-0 space-y-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
                    Candidate load (read-only — same sections as workspace)
                  </div>
                  {hydrateError ? (
                    <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                      {hydrateError}
                    </div>
                  ) : null}
                  {!listsLoaded ? (
                    <p className="text-xs text-[var(--trk-text-muted)]">Loading broker/driver lists for form…</p>
                  ) : (
                    <LoadWorkspaceForm
                      mode="manual"
                      readOnly
                      visibleSections={sectionConfig.visible}
                      editableSections={[]}
                      intakeProposed={emptyIntakeProposed()}
                      saving={false}
                      freightBrokers={freightBrokers}
                      brokerContacts={brokerContacts}
                      drivers={drivers}
                      trucks={trucks}
                      trailers={trailers}
                      customsBrokers={customsBrokers}
                      customsMessage={null}
                      customsBrokerLocked
                      onCustomsBrokerChange={onCustomsBrokerChangeManual}
                      onConfirmSnapshot={undefined}
                      showOperationalNotesTimeline={false}
                      loadNotes={[]}
                      newNoteBody=""
                      setNewNoteBody={() => {}}
                      onAddNote={() => {}}
                      focusDoc={focusDocNoop}
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
                      trailerAssetId={trailerAssetId}
                      setTrailerAssetId={setTrailerAssetId}
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
                  )}
                </div>

                <aside className="min-w-0 space-y-4 border-t border-[var(--trk-border)] pt-4 xl:border-l xl:border-t-0 xl:pl-4 xl:pt-0">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
                    Lab context
                  </div>
                  <div className="grid gap-2 text-xs text-[var(--trk-text-muted)]">
                    <div>
                      <span className="font-semibold text-[var(--trk-text)]">Readability:</span> {readability ?? "—"}
                    </div>
                    <div>
                      <span className="font-semibold text-[var(--trk-text)]">Parser:</span> {detail.parser_version}
                    </div>
                    <div>
                      <span className="font-semibold text-[var(--trk-text)]">Schema:</span> {detail.schema_version}
                    </div>
                    {detail.semantic_model_name ? (
                      <div>
                        <span className="font-semibold text-[var(--trk-text)]">Semantic model:</span> {detail.semantic_model_name}
                      </div>
                    ) : null}
                    <div>
                      <span className="font-semibold text-[var(--trk-text)]">SHA-256:</span>{" "}
                      <span className="break-all font-mono text-[10px]">{detail.file_sha256}</span>
                    </div>
                    {detail.pipeline_error ? (
                      <div className="text-amber-200">
                        <span className="font-semibold">Pipeline:</span> {detail.pipeline_error}
                      </div>
                    ) : null}
                  </div>

                  <ReviewStateBanner status={detail.lab_review_status} summary={detail.lab_review_summary} />

                  {detail.parse_response ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <button type="button" className={btn} disabled={reviewBusy} onClick={() => void onRecomputeReview()}>
                        {reviewBusy ? "Review…" : "Recompute lab review"}
                      </button>
                      {reviewNote ? <span className="text-xs text-[var(--trk-text-muted)]">{reviewNote}</span> : null}
                    </div>
                  ) : null}

                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
                      Confidence by group
                    </div>
                    <ConfidenceGroups lab={detail.lab_confidence ?? null} />
                  </div>

                  <div className="space-y-1">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-[var(--trk-text-muted)]">
                      Contradiction flags
                    </div>
                    <ContradictionsList items={detail.contradictions ?? null} />
                  </div>

                  <JsonBlock value={parseReferences ?? null} title="Structured references (parse DTO)" />
                  <JsonBlock value={detail.warnings} title="Warnings" />
                  <JsonBlock value={(detail.parse_response as any)?.field_confidence ?? null} title="Field confidence (workspace-facing)" />
                  <JsonBlock
                    value={((detail.parse_response as any)?.parse_diagnostics as any)?.review_flags ?? null}
                    title="Review flags (parse_diagnostics)"
                  />
                  <TextPreview text={rawTextStr} title="Raw text preview" />
                  <JsonBlock value={detail.normalized_package} title="Normalized package" />
                  <JsonBlock value={detail.parse_response ?? null} title="Candidate JSON (parse_response)" />
                  <JsonBlock value={detail.semantic_validation_result ?? null} title="Deterministic validation" />
                  <JsonBlock value={detail.ai_model_output ?? null} title="OpenAI request metadata / excerpt" />
                </aside>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
