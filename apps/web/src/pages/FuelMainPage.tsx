import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getFuelBvdUploadErrorDisplay,
  listFuelBvdCompletedHistory,
  listFuelProviders,
  getFuelDashboardStats,
  discardFuelBvdStage,
  uploadFuelBvdPdf,
  type FuelBvdCompletedBasic,
  type FuelProviderCatalog,
} from "../api";
import FuelConfigureApiModal from "./fuel/FuelConfigureApiModal";
import FuelProviderCombobox from "./fuel/FuelProviderCombobox";
import { mapFuelDashboardStatsFromApi, recentFuelActivity, type FuelDashboardStats } from "./fuel/fuelDashboardData";
import { readLastFuelProviderCode, writeLastFuelProviderCode } from "./fuel/fuelLastProvider";
import { parseFuelBvdDuplicateDetail } from "./fuelBvdReview/bvdUploadDuplicate";
import { readFuelProcessedReturn } from "./fuelBvdReview/bvdUploadCompletion";
import FuelRecentActivitySection from "./fuel/FuelRecentActivitySection";
import FuelBvdProcessingWorkspace from "./fuelBvdReview/FuelBvdProcessingWorkspace";
import FuelBvdProcessedRecordView from "./fuelBvdReview/FuelBvdProcessedRecordView";

export default function FuelMainPage() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [catalog, setCatalog] = useState<FuelProviderCatalog[]>([]);
  const [providerCode, setProviderCode] = useState("BVD");
  const [completed, setCompleted] = useState<FuelBvdCompletedBasic[]>([]);
  const [stats, setStats] = useState<FuelDashboardStats>({
    needsReviewCount: 0,
    processedLast7DaysCount: 0,
  });
  const [loading, setLoading] = useState(true);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [apiModalOpen, setApiModalOpen] = useState(false);
  const [showAllActivity, setShowAllActivity] = useState(false);
  const [processNotice, setProcessNotice] = useState<string | null>(null);
  const [processingImportId, setProcessingImportId] = useState<string | null>(null);
  const [processedImportId, setProcessedImportId] = useState<string | null>(null);
  const [highlightImportId, setHighlightImportId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();

  const refresh = useCallback(async () => {
    const [providers, history, dashboardStats] = await Promise.all([
      listFuelProviders(),
      listFuelBvdCompletedHistory(),
      getFuelDashboardStats(),
    ]);
    setCatalog(providers);
    setCompleted(history);
    setStats(mapFuelDashboardStatsFromApi(dashboardStats));

    const last = readLastFuelProviderCode();
    const codes = providers.map((p) => p.provider_code);
    if (last && codes.includes(last)) setProviderCode(last);
    else if (codes.includes("BVD")) setProviderCode("BVD");
    else if (providers[0]) setProviderCode(providers[0].provider_code);
  }, []);

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

  const activity = useMemo(
    () => recentFuelActivity(completed, showAllActivity ? 40 : 5),
    [completed, showAllActivity],
  );

  async function onFileChosen(file: File) {
    setUploadError(null);
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext !== "pdf" && ext !== "csv") {
      setUploadError("Choose a PDF or CSV file.");
      return;
    }
    if (providerCode === "BVD" && ext === "pdf") {
      setUploadBusy(true);
      try {
        const out = await uploadFuelBvdPdf(file);
        writeLastFuelProviderCode(providerCode);
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
    setUploadError(
      ext === "csv"
        ? "CSV format is not configured for this provider yet."
        : `PDF upload for provider ${providerCode} is not available from this screen yet. Use BVD for PDF imports today.`,
    );
  }

  const handleProcessed = useCallback(
    async (payload: { importId: string; invoiceNumber?: string }) => {
      setProcessingImportId(null);
      setHighlightImportId(payload.importId);
      setShowAllActivity(true);
      setProcessNotice(
        payload.invoiceNumber
          ? `Invoice ${payload.invoiceNumber} processed. It appears in Recent activity below.`
          : "Import processed. Recent activity updated.",
      );
      await refresh();
    },
    [refresh],
  );

  const overlayOpen = Boolean(processingImportId || processedImportId);

  useEffect(() => {
    if (overlayOpen) {
      document.body.classList.add("fuel-overlay-open");
    } else {
      document.body.classList.remove("fuel-overlay-open");
    }
    return () => document.body.classList.remove("fuel-overlay-open");
  }, [overlayOpen]);

  return (
    <div className="w-full max-w-full overflow-x-hidden px-5 py-4" data-testid="fuel-home">
      <header className="mb-3 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <div>
          <h1 className="text-xl font-semibold text-[var(--trk-text)]">Fuel</h1>
          <p className="text-xs text-[var(--trk-text-muted)]">
            Upload, import, review and manage fuel card activity.
          </p>
        </div>
      </header>
      {processNotice ? (
        <p className="mb-2 text-xs font-medium text-[var(--trk-success)]" role="status">{processNotice}</p>
      ) : null}

      <section className="mb-3 rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
        <div className="flex flex-wrap items-end gap-3">
          <FuelProviderCombobox
            catalog={catalog}
            value={providerCode}
            onChange={onSelectProvider}
            disabled={loading}
          />
        </div>
      </section>

      <div className="mb-3 grid gap-3 lg:grid-cols-[1fr_auto]">
        <section className="rounded-lg border border-[var(--trk-border)] bg-[var(--trk-surface)] px-3 py-2">
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
        activity={activity}
        loading={loading}
        heading={showAllActivity ? "Completed invoices" : "Recent activity"}
        showViewAllLink={!showAllActivity && completed.length > 5}
        onViewAllClick={() => setShowAllActivity(true)}
        emptyMessage="No completed imports yet."
        highlightImportId={highlightImportId}
        onOpenProcessed={(importId) => setProcessedImportId(importId)}
      />

      <FuelConfigureApiModal
        open={apiModalOpen}
        onClose={() => setApiModalOpen(false)}
        initialProviderCode={providerCode}
      />

      {processingImportId ? (
        <FuelBvdProcessingWorkspace
          importId={processingImportId}
          variant="overlay"
          onClose={() => {
            const id = processingImportId;
            setProcessingImportId(null);
            if (id) {
              void discardFuelBvdStage(id).catch(() => {
                /* overlay already closed; best-effort discard */
              });
            }
          }}
          onProcessed={(p) => void handleProcessed(p)}
        />
      ) : null}

      {processedImportId ? (
        <FuelBvdProcessedRecordView
          importId={processedImportId}
          variant="overlay"
          onClose={() => setProcessedImportId(null)}
        />
      ) : null}
    </div>
  );
}
