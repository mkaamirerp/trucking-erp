/**
 * Mobile-first public Driver Licence capture page.
 * Uses normalizeDlUpload (f00cf96e) then capture API; no OpenCV in browser.
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useParams } from "react-router-dom";
import { normalizeDlUpload } from "../lib/normalizeDlUpload";
import { API_BASE, fetchWithTenant } from "../api";

type CaptureStep = "FRONT" | "BACK" | "COMPLETE";
type SideStatus = "MISSING" | "FAILED" | "PROCESSED";

type CaptureSession = {
  step: CaptureStep;
  front_status: SideStatus;
  back_status: SideStatus;
  front_preview_file_id?: string | null;
  back_preview_file_id?: string | null;
  front_confirmed?: boolean;
  back_confirmed?: boolean;
  message?: string | null;
};

type UiPhase = "LOADING" | "INVALID" | "READY" | "UPLOADING" | "SCANNING";

export const DL_CAPTURE_UPLOAD_TIMEOUT_MS = 30_000;
export const DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE = "The upload took too long. Please try again.";
export const DL_CAPTURE_UPLOAD_NETWORK_MESSAGE =
  "We could not upload your license right now. Please try again.";

const INVALID_CAPTURE_TITLE = "Invalid or expired capture link";
const INVALID_CAPTURE_BODY =
  "This driver licence capture link is invalid or has expired. Ask your company for a new link.";

/** Capture-only: map tenant/auth failures to the same generic invalid-link UX. */
function isInvalidCaptureLinkStatus(status: number): boolean {
  return status === 400 || status === 403 || status === 404;
}

function captureUrl(token: string, suffix = ""): string {
  return `${API_BASE}/driver-onboarding/applicant/dl-capture/${encodeURIComponent(token)}${suffix}`;
}

async function loadSession(token: string): Promise<CaptureSession> {
  const res = await fetchWithTenant(captureUrl(token));
  if (isInvalidCaptureLinkStatus(res.status)) {
    throw new Error("invalid");
  }
  if (!res.ok) {
    throw new Error("invalid");
  }
  return (await res.json()) as CaptureSession;
}

function tryCloseCaptureTab(): void {
  try {
    window.close();
  } catch {
    /* Safari blocks close for tabs not opened by script. */
  }
}

function isConfirmingProcessed(session: CaptureSession): boolean {
  if (session.step === "COMPLETE") return false;
  if (session.step === "FRONT") return session.front_status === "PROCESSED";
  return session.back_status === "PROCESSED";
}

export default function DlCapturePage() {
  const { token = "" } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<UiPhase>("LOADING");
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
  const takeInputRef = useRef<HTMLInputElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const sessionRef = useRef<CaptureSession | null>(null);
  const localPreviewRef = useRef<string | null>(null);
  const uploadGenerationRef = useRef(0);
  const uploadAbortRef = useRef<AbortController | null>(null);

  sessionRef.current = session;
  localPreviewRef.current = localPreview;

  const refresh = useCallback(async () => {
    if (!token) {
      setPhase("INVALID");
      return;
    }
    try {
      const data = await loadSession(token);
      setSession(data);
      setPhase("READY");
      setError(null);
    } catch {
      setSession(null);
      setPhase("INVALID");
    }
  }, [token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    return () => {
      if (localPreview) URL.revokeObjectURL(localPreview);
    };
  }, [localPreview]);

  useEffect(() => {
    return () => {
      uploadGenerationRef.current += 1;
      uploadAbortRef.current?.abort();
    };
  }, []);

  const clearLocalPreview = () => {
    const blob = localPreviewRef.current;
    if (blob) URL.revokeObjectURL(blob);
    setLocalPreview(null);
  };

  const previewSrc = (() => {
    if (localPreview) return localPreview;
    if (!session || !token) return null;
    const fileId =
      session.step === "BACK" ? session.back_preview_file_id : session.front_preview_file_id;
    if (!fileId) return null;
    return `${captureUrl(token, "/file")}?file_id=${encodeURIComponent(fileId)}`;
  })();

  const handleFile = async (file: File) => {
    const current = sessionRef.current;
    if (!token || !current || current.step === "COMPLETE") return;
    setError(null);
    let normalized: File;
    try {
      normalized = await normalizeDlUpload(file);
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? `Could not prepare this image for upload (${err.message}). Please try again.`
          : "Could not prepare this image for upload. Please try again.",
      );
      return;
    }

    uploadGenerationRef.current += 1;
    const generation = uploadGenerationRef.current;
    uploadAbortRef.current?.abort();
    const controller = new AbortController();
    uploadAbortRef.current = controller;

    const url = URL.createObjectURL(normalized);
    setLocalPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });

    const startedStep = current.step;
    const docType = startedStep === "FRONT" ? "CDL_FRONT" : "CDL_BACK";
    setPhase("UPLOADING");
    const scanningTimer = window.setTimeout(() => {
      if (generation !== uploadGenerationRef.current) return;
      setPhase("SCANNING");
    }, 600);
    const abortTimer = window.setTimeout(() => {
      controller.abort();
      if (generation !== uploadGenerationRef.current) return;
      setError(DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE);
      setPhase("READY");
    }, DL_CAPTURE_UPLOAD_TIMEOUT_MS);

    const isStale = () => generation !== uploadGenerationRef.current;

    try {
      const form = new FormData();
      form.append("doc_type", docType);
      form.append("file", normalized);
      const res = await fetchWithTenant(captureUrl(token, "/upload"), {
        method: "POST",
        body: form,
        signal: controller.signal,
      });
      if (isStale() || controller.signal.aborted) return;
      if (isInvalidCaptureLinkStatus(res.status)) {
        setPhase("INVALID");
        return;
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        if (isStale() || controller.signal.aborted) return;
        setError(
          typeof detail?.detail === "string"
            ? detail.detail
            : "Upload failed. Please try again.",
        );
        setPhase("READY");
        return;
      }
      const next = (await res.json()) as CaptureSession;
      if (isStale() || controller.signal.aborted) return;
      setSession(next);
      sessionRef.current = next;
      if (next.message) setError(next.message);
      else setError(null);
      const processed =
        (startedStep === "FRONT" && next.front_status === "PROCESSED") ||
        (startedStep === "BACK" && next.back_status === "PROCESSED");
      if (processed || next.step === "COMPLETE") {
        clearLocalPreview();
      }
      setPhase("READY");
    } catch {
      if (isStale()) return;
      if (controller.signal.aborted) {
        setError(DL_CAPTURE_UPLOAD_TIMEOUT_MESSAGE);
        setPhase("READY");
        return;
      }
      setError(DL_CAPTURE_UPLOAD_NETWORK_MESSAGE);
      setPhase("READY");
    } finally {
      window.clearTimeout(scanningTimer);
      window.clearTimeout(abortTimer);
    }
  };

  const handleConfirm = async () => {
    const current = sessionRef.current;
    if (!token || !current || current.step === "COMPLETE" || confirmBusy) return;
    if (!isConfirmingProcessed(current)) return;
    const docType = current.step === "FRONT" ? "CDL_FRONT" : "CDL_BACK";
    setConfirmBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("doc_type", docType);
      const res = await fetchWithTenant(captureUrl(token, "/confirm"), {
        method: "POST",
        body: form,
      });
      if (isInvalidCaptureLinkStatus(res.status)) {
        setPhase("INVALID");
        return;
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(
          typeof detail?.detail === "string"
            ? detail.detail
            : "Could not confirm this photo. Please try again.",
        );
        return;
      }
      const next = (await res.json()) as CaptureSession;
      setSession(next);
      sessionRef.current = next;
      clearLocalPreview();
      if (next.step === "COMPLETE") {
        tryCloseCaptureTab();
      }
    } catch {
      setError(DL_CAPTURE_UPLOAD_NETWORK_MESSAGE);
    } finally {
      setConfirmBusy(false);
    }
  };

  const onInputFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    e.currentTarget.value = "";
    if (f) void handleFile(f);
  };

  const shell: CSSProperties = {
    minHeight: "100vh",
    background: "var(--trk-bg, #0f172a)",
    color: "var(--trk-text, #e2e8f0)",
    padding: "24px 18px 48px",
    fontFamily: "system-ui, sans-serif",
  };
  const card: CSSProperties = {
    maxWidth: 440,
    margin: "0 auto",
    background: "var(--trk-surface, #1e293b)",
    border: "1px solid var(--trk-border, #334155)",
    borderRadius: 16,
    padding: 20,
  };
  const btn: CSSProperties = {
    width: "100%",
    padding: "14px 16px",
    borderRadius: 10,
    border: "1px solid var(--trk-border, #475569)",
    background: "transparent",
    color: "var(--trk-heading, #f8fafc)",
    fontWeight: 700,
    fontSize: "0.95rem",
    cursor: "pointer",
    marginTop: 10,
  };
  const primary: CSSProperties = {
    ...btn,
    background: "var(--trk-heading, #f97316)",
    borderColor: "transparent",
    color: "#0f172a",
  };

  if (phase === "LOADING") {
    return (
      <div style={shell}>
        <div style={card}>Loading…</div>
      </div>
    );
  }

  if (phase === "INVALID" || !session) {
    return (
      <div style={shell}>
        <div style={card}>
          <h1 style={{ fontSize: "1.35rem", margin: "0 0 10px" }}>{INVALID_CAPTURE_TITLE}</h1>
          <p style={{ margin: 0, lineHeight: 1.55, color: "var(--trk-text-muted, #94a3b8)" }}>
            {INVALID_CAPTURE_BODY}
          </p>
        </div>
      </div>
    );
  }

  if (session.step === "COMPLETE") {
    return (
      <div style={shell}>
        <div style={card}>
          <div style={{ color: "var(--trk-success, #22c55e)", fontWeight: 800, marginBottom: 8 }}>
            ✓ Driver licence received
          </div>
          <p style={{ margin: 0, lineHeight: 1.55, color: "var(--trk-text-muted, #94a3b8)" }}>
            You can return to the other device.
          </p>
          <button type="button" style={primary} onClick={() => tryCloseCaptureTab()}>
            Close
          </button>
        </div>
      </div>
    );
  }

  const busy = phase === "UPLOADING" || phase === "SCANNING" || confirmBusy;
  const confirming = isConfirmingProcessed(session);
  const stepLabel = session.step === "FRONT" ? "Front Driver Licence" : "Back Driver Licence";
  const takeLabel = session.step === "FRONT" ? "Take Front DL" : "Take Back DL";
  const failed =
    (session.step === "FRONT" && session.front_status === "FAILED") ||
    (session.step === "BACK" && session.back_status === "FAILED");

  return (
    <div style={shell}>
      <div style={card}>
        <div
          style={{
            fontSize: "0.72rem",
            fontWeight: 800,
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            color: "var(--trk-heading, #f97316)",
            marginBottom: 8,
          }}
        >
          Driver Licence
        </div>
        <h1 style={{ fontSize: "1.45rem", margin: "0 0 6px" }}>{stepLabel}</h1>
        {session.step === "BACK" && session.front_status === "PROCESSED" && (
          <div style={{ color: "var(--trk-success, #22c55e)", fontWeight: 700, marginBottom: 12 }}>
            ✓ Front accepted
          </div>
        )}

        <div
          style={{
            borderRadius: 12,
            border: "2px dashed var(--trk-border, #475569)",
            minHeight: 220,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            overflow: "hidden",
            background: "var(--trk-bg, #0f172a)",
            marginBottom: 8,
          }}
        >
          {busy && !confirmBusy ? (
            <div style={{ textAlign: "center", padding: 24 }}>
              <div style={{ fontWeight: 700 }}>
                {phase === "SCANNING" ? "Processing licence image…" : "Uploading…"}
              </div>
            </div>
          ) : previewSrc ? (
            <img
              src={previewSrc}
              alt="Licence preview"
              style={{ width: "100%", height: "100%", objectFit: "contain", maxHeight: 320 }}
            />
          ) : (
            <div style={{ padding: 24, textAlign: "center", color: "var(--trk-text-muted, #94a3b8)" }}>
              Take or choose a clear photo of the {session.step === "FRONT" ? "front" : "back"} of
              your licence.
            </div>
          )}
        </div>

        {(error || failed) && (
          <p style={{ color: "var(--trk-danger, #f87171)", fontSize: "0.9rem", lineHeight: 1.5 }}>
            {error || "We couldn't clearly detect all four edges."}
          </p>
        )}

        <input
          ref={takeInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          style={{ display: "none" }}
          disabled={busy}
          onChange={onInputFile}
        />
        <input
          ref={uploadInputRef}
          type="file"
          accept="image/*"
          style={{ display: "none" }}
          disabled={busy}
          onChange={onInputFile}
        />

        {confirming ? (
          <div style={{ display: "flex", gap: 10, marginTop: 10 }}>
            <button
              type="button"
              style={{ ...btn, flex: 1, marginTop: 0 }}
              disabled={busy}
              onClick={() => takeInputRef.current?.click()}
            >
              Retake
            </button>
            <button
              type="button"
              style={{ ...primary, flex: 1, marginTop: 0 }}
              disabled={busy}
              onClick={() => void handleConfirm()}
            >
              Use This Photo
            </button>
          </div>
        ) : (
          <>
            <button type="button" style={primary} disabled={busy} onClick={() => takeInputRef.current?.click()}>
              {takeLabel}
            </button>
            <button type="button" style={btn} disabled={busy} onClick={() => uploadInputRef.current?.click()}>
              Choose Existing Photo
            </button>
          </>
        )}
      </div>
    </div>
  );
}
