import { useCallback, useEffect, useRef, useState } from "react";
import {
  downloadLoadPodEvidenceFile,
  listLoadPodEvidence,
  uploadLoadPodEvidence,
  type LoadPodEvidence,
} from "@/api";

export type LoadPodEvidencePanelApi = {
  listLoadPodEvidence: typeof listLoadPodEvidence;
  uploadLoadPodEvidence: typeof uploadLoadPodEvidence;
  downloadLoadPodEvidenceFile: typeof downloadLoadPodEvidenceFile;
};

const defaultApi: LoadPodEvidencePanelApi = {
  listLoadPodEvidence,
  uploadLoadPodEvidence,
  downloadLoadPodEvidenceFile,
};

const btn =
  "rounded border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-0.5 text-[10px] font-semibold text-[var(--trk-text-muted)] hover:bg-[var(--trk-border)] disabled:opacity-45";

const ACCEPT = "application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png";

function formatPodApiError(err: unknown): string {
  if (err && typeof err === "object" && "message" in err && typeof (err as { message: string }).message === "string") {
    return (err as { message: string }).message;
  }
  return "Upload failed";
}

export default function LoadPodEvidencePanel({
  loadId,
  api = defaultApi,
}: {
  loadId: number;
  api?: LoadPodEvidencePanelApi;
}) {
  const [items, setItems] = useState<LoadPodEvidence[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const pendingRef = useRef(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const listed = await api.listLoadPodEvidence(loadId);
      setItems(listed);
    } catch (e) {
      setError(formatPodApiError(e));
    } finally {
      setLoading(false);
    }
  }, [api, loadId]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const onFileChosen = async (file: File | undefined) => {
    if (!file || pendingRef.current) return;
    pendingRef.current = true;
    setPending(true);
    setUploadError(null);
    try {
      await api.uploadLoadPodEvidence(loadId, file);
      await refresh();
    } catch (e) {
      setUploadError(formatPodApiError(e));
    } finally {
      pendingRef.current = false;
      setPending(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  return (
    <div className="rounded border border-[var(--trk-border)]/80 bg-[var(--trk-surface)] px-2 py-1.5">
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <span className="text-[9px] font-semibold uppercase text-[var(--trk-text-muted)]">Proof of delivery</span>
        <button
          type="button"
          className={btn}
          disabled={pending}
          data-testid={`pod-upload-${loadId}`}
          onClick={() => inputRef.current?.click()}
        >
          {pending ? "Uploading…" : "Upload POD"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          className="hidden"
          data-testid={`pod-file-input-${loadId}`}
          onChange={(e) => void onFileChosen(e.target.files?.[0])}
        />
      </div>
      <p className="text-[9px] text-[var(--trk-text-muted)]">
        Attach a receiver-signed PDF or image. This does not deliver the load or complete the trip.
      </p>
      {uploadError ? (
        <div className="mt-1 text-[9px] text-[var(--trk-danger)]" data-testid={`pod-upload-error-${loadId}`}>
          {uploadError}
        </div>
      ) : null}
      {error ? <div className="mt-1 text-[9px] text-[var(--trk-danger)]">{error}</div> : null}
      {loading ? (
        <div className="mt-1 text-[9px] text-[var(--trk-text-muted)]">Loading POD…</div>
      ) : items.length === 0 ? (
        <div className="mt-1 text-[9px] text-[var(--trk-text-muted)]">No POD attached yet.</div>
      ) : (
        <ul className="mt-1 space-y-0.5">
          {items.map((row) => (
            <li key={row.id} className="flex flex-wrap items-center gap-2 text-[9px]">
              <span className="font-medium text-[var(--trk-text)]">{row.original_filename ?? `POD #${row.id}`}</span>
              <span className="text-[var(--trk-text-muted)]">{new Date(row.uploaded_at).toLocaleString()}</span>
              <button
                type="button"
                className={btn}
                data-testid={`pod-download-${loadId}-${row.id}`}
                onClick={() =>
                  void api.downloadLoadPodEvidenceFile(loadId, row.id, row.original_filename).catch((e) =>
                    setUploadError(formatPodApiError(e))
                  )
                }
              >
                Download
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
