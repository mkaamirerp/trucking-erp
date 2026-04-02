import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { getDlGallery, type DlGalleryResponse } from "../api";

const API_BASE = import.meta.env.VITE_API_BASE || "/api/v1";

// Row 1: FRONT, FRONT_ENH; Row 2: BACK, BACK_ENH
const GRID_ORDER: Array<"CDL_FRONT" | "CDL_FRONT_ENH" | "CDL_BACK" | "CDL_BACK_ENH"> = [
  "CDL_FRONT",
  "CDL_FRONT_ENH",
  "CDL_BACK",
  "CDL_BACK_ENH",
];

function copyToClipboard(text: string): Promise<void> {
  return navigator.clipboard.writeText(text);
}

export default function DebugDlImagesPage() {
  const [searchParams] = useSearchParams();
  const tenantParam = searchParams.get("tenant");
  const appParam = searchParams.get("app");
  const tenantId = tenantParam ? parseInt(tenantParam, 10) : 52;
  const appId = appParam ? parseInt(appParam, 10) : 13;

  const [data, setData] = useState<DlGalleryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [imageErrors, setImageErrors] = useState<Set<string>>(new Set());
  const [copyFeedback, setCopyFeedback] = useState<string | null>(null);

  const fetchGallery = useCallback(() => {
    setLoading(true);
    setError(null);
    setImageErrors(new Set());
    getDlGallery(appId, tenantId)
      .then((res) => {
        setData(res);
        setLastRefreshed(new Date());
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [appId, tenantId]);

  useEffect(() => {
    fetchGallery();
  }, [fetchGallery]);

  const handleRefresh = () => {
    fetchGallery();
  };

  const handleImageError = (docType: string) => {
    setImageErrors((prev) => new Set(prev).add(docType));
  };

  const rawUrl = (fileId: number) =>
    `${API_BASE}/dev/person-application-files/${fileId}/raw?tenant=${tenantId}`;

  const showCopyFeedback = (msg: string) => {
    setCopyFeedback(msg);
    setTimeout(() => setCopyFeedback(null), 2000);
  };

  const handleCopyUrl = (fileId: number) => {
    copyToClipboard(rawUrl(fileId))
      .then(() => showCopyFeedback("URL copied"))
      .catch(() => showCopyFeedback("Copy failed"));
  };

  const handleCopyGalleryJson = () => {
    if (!data) return;
    copyToClipboard(JSON.stringify(data, null, 2))
      .then(() => showCopyFeedback("Gallery JSON copied"))
      .catch(() => showCopyFeedback("Copy failed"));
  };

  const files = data?.files ?? {};

  return (
    <div className="min-h-screen bg-slate-900 text-slate-200 p-6">
      <div className="max-w-4xl mx-auto">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
          <div>
            <h1 className="text-xl font-semibold mb-1">Debug: DL images (persisted storage)</h1>
            <p className="text-sm text-slate-400">
              Tenant ID: {tenantId} · Application ID: {appId}
              {lastRefreshed && (
                <span className="ml-3 text-slate-500">
                  Last refreshed: {lastRefreshed.toLocaleString()}
                </span>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleRefresh}
              className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm font-medium"
            >
              Refresh
            </button>
            {data && (
              <button
                type="button"
                onClick={handleCopyGalleryJson}
                className="rounded-lg bg-slate-700 hover:bg-slate-600 px-4 py-2 text-sm font-medium"
              >
                Copy gallery JSON
              </button>
            )}
            {copyFeedback && (
              <span className="text-sm text-emerald-400">{copyFeedback}</span>
            )}
          </div>
        </div>
        {loading && <p className="text-slate-400">Loading gallery…</p>}
        {error && (
          <p className="text-red-400" role="alert">
            {error}
          </p>
        )}
        {!loading && !error && data && (
          <div className="grid grid-cols-2 gap-4" style={{ gridTemplateColumns: "1fr 1fr" }}>
            {GRID_ORDER.map((docType) => {
              const fileId = files[docType];
              const label = docType.replace("CDL_", "");
              const failed = imageErrors.has(docType);
              const url = fileId != null ? rawUrl(fileId) : null;

              return (
                <div
                  key={docType}
                  className="rounded-lg border border-slate-600 bg-slate-800/50 p-3"
                >
                  <div className="text-sm font-medium text-slate-300 mb-2">
                    {label}
                    {fileId != null && (
                      <span className="ml-2 text-slate-500 font-normal">
                        {docType} · file_id: {fileId}
                      </span>
                    )}
                  </div>
                  {fileId == null ? (
                    <div className="text-slate-500 text-sm py-8 text-center rounded border border-slate-600">
                      missing
                    </div>
                  ) : failed ? (
                    <div className="rounded border border-amber-600/50 bg-amber-900/20 p-4 text-center">
                      <p className="text-amber-200 text-sm mb-2">
                        Image failed to load (404)
                      </p>
                      <p className="text-slate-400 text-xs mb-3">
                        {docType} · file_id: {fileId}
                      </p>
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block rounded bg-slate-600 hover:bg-slate-500 px-3 py-1.5 text-xs"
                      >
                        Open raw
                      </a>
                    </div>
                  ) : (
                    <img
                      src={url!}
                      alt={docType}
                      style={{ maxWidth: "100%", height: "auto" }}
                      className="rounded border border-slate-600"
                      onError={() => handleImageError(docType)}
                    />
                  )}
                  {fileId != null && (
                    <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
                      <a
                        href={url!}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-blue-300 hover:text-blue-200"
                      >
                        Open raw
                      </a>
                      <button
                        type="button"
                        onClick={() => handleCopyUrl(fileId)}
                        className="text-slate-400 hover:text-slate-300"
                      >
                        Copy URL
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
