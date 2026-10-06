import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getFuelBvdUploadErrorDisplay,
  listFuelProcessed,
  listFuelProviders,
  getFuelDashboardStats,
  discardFuelBvdStage,
  discardFuelNationwideStage,
  uploadFuelBvdPdf,
  uploadFuelNationwidePdf,
  getFuelNationwideUploadErrorDisplay,
  type FuelProcessedSummary,
  type FuelProviderCatalog,
} from "../api";
import FuelConfigureApiModal from "./fuel/FuelConfigureApiModal";
import FuelProviderCombobox from "./fuel/FuelProviderCombobox";
import {
  FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT,
  FUEL_RECENT_ACTIVITY_VIEW_ALL_LIMIT,
  mapFuelDashboardStatsFromApi,
  type FuelDashboardStats,
} from "./fuel/fuelDashboardData";
import { buildFuelRecentActivityDisplay } from "./fuel/fuelRecentActivityDisplay";
import { readLastFuelProviderCode, writeLastFuelProviderCode } from "./fuel/fuelLastProvider";
import { parseFuelBvdDuplicateDetail } from "./fuelBvdReview/bvdUploadDuplicate";
import { readFuelProcessedReturn } from "./fuelBvdReview/bvdUploadCompletion";
import FuelRecentActivitySection from "./fuel/FuelRecentActivitySection";
import FuelBvdProcessingWorkspace from "./fuelBvdReview/FuelBvdProcessingWorkspace";
import FuelNationwideProcessingWorkspace from "./fuelNationwideReview/FuelNationwideProcessingWorkspace";
import FuelManualEntryModal from "./fuel/FuelManualEntryModal";
import { getProcessedFuelRecordOverlay } from "./fuel/processedFuelProviderRenderers";
import "./fuel/fuel-home.css";

export default function FuelMainPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [catalog, setCatalog] = useState<FuelProviderCatalog[]>([]);
  const [providerCode, setProviderCode] = useState("BVD");
  const [completed, setCompleted] = useState<FuelProcessedSummary[]>([]);
  const [stats, setStats] = useState<FuelDashboardStats>({
    needsReviewCount: 0,
    processedLast7DaysCount: 0,
  });
  const [loading, setLoading] = useState(true);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [apiModalOpen, setApiModalOpen] = useState(false);
  const [manualEntryOpen, setManualEntryOpen] = useState(false);
  const [showAllActivity, setShowAllActivity] = useState(false);
  const [hasMoreCompleted, setHasMoreCompleted] = useState(false);
  const [processNotice, setProcessNotice] = useState<string | null>(null);
  const [processingImportId, setProcessingImportId] = useState<string | null>(null);
  const [processingProvider, setProcessingProvider] = useState<"BVD" | "NATIONWIDE">("BVD");
  const [processedBatchId, setProcessedBatchId] = useState<number | null>(null);
  const [processedProvider, setProcessedProvider] = useState<string>("BVD");
  const [processedSourceImportRef, setProcessedSourceImportRef] = useState<string | null>(null);
  const [highlightBatchId, setHighlightBatchId] = useState<number | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const refresh = useCallback(async () => {
    const processedLimit = showAllActivity
      ? FUEL_RECENT_ACTIVITY_VIEW_ALL_LIMIT
      : FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT + 1;
    const [providers, processedHistory, dashboardStats] = await Promise.all([
      listFuelProviders(),
      listFuelProcessed({ limit: processedLimit }),
      getFuelDashboardStats(),
    ]);
    setCatalog(providers);
    setCompleted(processedHistory);
    setHasMoreCompleted(
      !showAllActivity && processedHistory.length > FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT,
    );
    setStats(mapFuelDashboardStatsFromApi(dashboardStats));

    const last = readLastFuelProviderCode();
    const codes = providers.map((p) => p.provider_code);
    if (last && codes.includes(last)) setProviderCode(last);
    else if (codes.includes("BVD")) setProviderCode("BVD");
    else if (providers[0]) setProviderCode(providers[0].provider_code);
    return processedHistory;
  }, [showAllActivity]);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch(() => undefined)
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    const processed = readFuelProcessedReturn(searchParams.toString());
    if (!processed) return;
    setProcessNotice(
      processed.invoiceNumber
        ? `Invoice ${processed.invoiceNumber} processed. It appears in Recent activity below.`
        : "Import processed. Recent activity updated.",
    );
    setShowAllActivity(true);
    void refresh();
    setSearchParams({}, { replace: true });
  }, [searchParams, setSearchParams, refresh]);

  const onSelectProvider = (code: string) => {
    setProviderCode(code);
    writeLastFuelProviderCode(code);
  };

  const activityItems = useMemo(
    () =>
      buildFuelRecentActivityDisplay(
        completed,
        showAllActivity ? FUEL_RECENT_ACTIVITY_VIEW_ALL_LIMIT : FUEL_RECENT_ACTIVITY_PREVIEW_LIMIT,
      ),
    [completed, showAllActivity],
  );

  async function onFileChosen(file: File) {
    setUploadError(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "csv") {
      setUploadError("Choose a PDF or CSV file.");
      return;
    }
    if (ext === "pdf" && providerCode === "BVD") {
      setUploadBusy(true);
      try {
        const out = await uploadFuelBvdPdf(file);
        writeLastFuelProviderCode(providerCode);
        setProcessingProvider("BVD");
        setProcessingImportId(out.import_id);
      } catch (err: unknown) {
        const display = getFuelBvdUploadErrorDisplay(err);
        const dup = parseFuelBvdDuplicateDetail(err);
        if (dup?.existing_import_id) {
          setUploadError(`${display.title}: ${display.message} Open the existing import from Recent activity.`);
        } else {
          setUploadError(`${display.title}: ${display.message}`);
        }
      } finally {
        setUploadBusy(false);
      }
      return;
    }
    if (ext === "pdf" && providerCode === "NATIONWIDE") {
      setUploadBusy(true);
      try {
        const out = await uploadFuelNationwidePdf(file);
        writeLastFuelProviderCode(providerCode);
        setProcessingProvider("NATIONWIDE");
        setProcessingImportId(out.import_id);
      } catch (err: unknown) {
        const display = getFuelNationwideUploadErrorDisplay(err);
        const dup = parseFuelBvdDuplicateDetail(err);
        if (dup?.existing_import_id && dup.existing_status === "SOURCE_REVIEWED") {
          setUploadError(
            `${display.title}: ${display.message} Open the processed invoice from Recent activity below.`,
          );
        } else if (dup?.existing_import_id) {
          setUploadError(`${display.title}: ${display.message} Existing import: ${dup.existing_import_id}.`);
        } else {
          setUploadError(`${display.title}: ${display.message}`);
        }
      } finally {
        setUploadBusy(false);
      }
      return;
    }
    setUploadError(
      ext === "csv"
        ? "CSV format is not configured for this provider yet."
        : `PDF upload for provider ${providerCode} is not available from this screen yet.`,
    );
  }

  const handleProcessed = useCallback(
    async (payload: { importId: string; invoiceNumber?: string }) => {
      setProcessingImportId(null);
      setShowAllActivity(true);
      setProcessNotice(
        payload.invoiceNumber
          ? `Invoice ${payload.invoiceNumber} processed. It appears in Recent activity below.`
          : "Import processed. Recent activity updated.",
      );
      const processedHistory = await refresh();
      setHighlightBatchId(
        processedHistory.find((row) => row.source_import_ref === payload.importId)?.batch_id ?? null,
      );
    },
    [refresh],
  );

  const overlayOpen = Boolean(processingImportId || processedBatchId);
  const ProcessedRecordOverlay = processedBatchId
    ? getProcessedFuelRecordOverlay(processedProvider)
    : null;

  useEffect(() => {
    if (overlayOpen) {
      document.body.classList.add("fuel-overlay-open");
    } else {
      document.body.classList.remove("fuel-overlay-open");
    }
    return () => document.body.classList.remove("fuel-overlay-open");
  }, [overlayOpen]);

  return (
    <div className="trk-page trk-page--dense" data-testid="fuel-home">
      {processNotice ? (
        <p className="mb-2 text-xs font-medium text-[var(--trk-success)]" role="status">{processNotice}</p>
      ) : null}

      <section className="mb-2 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5">
        <div className="flex flex-wrap items-end gap-3">
          <FuelProviderCombobox
            catalog={catalog}
            value={providerCode}
            onChange={onSelectProvider}
            disabled={loading}
          />
        </div>
      </section>

      <div className="mb-2 grid gap-2 lg:grid-cols-[1fr_auto]">
        <section className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-1.5">
          <div className="flex flex-wrap items-center gap-3">
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.csv,application/pdf,text/csv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void onFileChosen(f);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              disabled={uploadBusy}
              onClick={() => fileInputRef.current?.click()}
              className="rounded-md bg-[var(--trk-btn-primary)] px-3 py-1.5 text-xs font-semibold text-[var(--trk-btn-text)] disabled:opacity-50"
            >
              {uploadBusy ? "Uploading…" : "Upload file"}
            </button>
            <span className="text-xs text-[var(--trk-text-muted)]">.pdf or .csv · {providerCode}</span>
            <span className="hidden text-[var(--trk-border)] sm:inline">|</span>
            <button
              type="button"
              onClick={() => setManualEntryOpen(true)}
              className="rounded-md border border-[var(--trk-border-strong)] px-3 py-1.5 text-xs font-medium text-[var(--trk-text)]"
            >
              Manual Entry
            </button>
            <button
              type="button"
              onClick={() => setApiModalOpen(true)}
              className="rounded-md border border-[var(--trk-border-strong)] px-3 py-1.5 text-xs font-medium text-[var(--trk-text)]"
            >
              Configure API
            </button>
          </div>
          {uploadError ? (
            <p className="mt-2 text-xs text-[var(--trk-danger)]" role="alert">{uploadError}</p>
          ) : null}
        </section>

        <div className="grid grid-cols-2 gap-2 lg:w-[min(100%,20rem)]">
          {[
            { label: "Needs review", value: stats.needsReviewCount },
            { label: "Processed last 7 days", value: stats.processedLast7DaysCount },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1.5"
            >
              <div className="text-[10px] leading-tight text-[var(--trk-text-muted)]">{card.label}</div>
              <div className="text-base font-semibold tabular-nums text-[var(--trk-text)]">{card.value}</div>
            </div>
          ))}
        </div>
      </div>

      <FuelRecentActivitySection
        activityItems={activityItems}
        loading={loading}
        heading={showAllActivity ? "Completed invoices" : "Recent activity"}
        showViewAllLink={!showAllActivity && hasMoreCompleted}
        onViewAllClick={() => setShowAllActivity(true)}
        emptyMessage="No completed imports yet."
        highlightBatchId={highlightBatchId}
        onOpenProcessed={(batchId, provider, sourceImportRef) => {
          setProcessedProvider(provider);
          setProcessedBatchId(batchId);
          setProcessedSourceImportRef(sourceImportRef);
        }}
      />

      <FuelConfigureApiModal
        open={apiModalOpen}
        onClose={() => setApiModalOpen(false)}
        initialProviderCode={providerCode}
      />

      <FuelManualEntryModal
        open={manualEntryOpen}
        onClose={() => setManualEntryOpen(false)}
        onProcessed={(p) => void handleProcessed(p)}
      />

      {processingImportId && processingProvider === "BVD" ? (
        <FuelBvdProcessingWorkspace
          importId={processingImportId}
          variant="overlay"
          onClose={() => {
            const id = processingImportId;
            setProcessingImportId(null);
            if (id) {
              void discardFuelBvdStage(id).catch(() => {});
            }
          }}
          onProcessed={(p) => void handleProcessed(p)}
        />
      ) : null}

      {processingImportId && processingProvider === "NATIONWIDE" ? (
        <FuelNationwideProcessingWorkspace
          importId={processingImportId}
          variant="overlay"
          onClose={() => {
            const id = processingImportId;
            setProcessingImportId(null);
            if (id) {
              void discardFuelNationwideStage(id).catch(() => {});
            }
          }}
          onProcessed={(p) => void handleProcessed(p)}
        />
      ) : null}

      {processedBatchId &&
      ProcessedRecordOverlay &&
      processedSourceImportRef ? (
        <ProcessedRecordOverlay
          sourceImportRef={processedSourceImportRef}
          variant="overlay"
          onClose={() => {
            setProcessedBatchId(null);
            setProcessedSourceImportRef(null);
          }}
        />
      ) : null}
    </div>
  );
}
