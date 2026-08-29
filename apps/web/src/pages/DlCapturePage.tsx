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
  message?: string | null;
};

type UiPhase = "LOADING" | "INVALID" | "READY" | "UPLOADING" | "SCANNING";

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

export default function DlCapturePage() {
  const { token = "" } = useParams<{ token: string }>();
  const [phase, setPhase] = useState<UiPhase>("LOADING");
  const [session, setSession] = useState<CaptureSession | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const takeInputRef = useRef<HTMLInputElement>(null);
  const uploadInputRef = useRef<HTMLInputElement>(null);

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

  const previewSrc = (() => {
    if (localPreview) return localPreview;
    if (!session || !token) return null;
    const fileId =
      session.step === "BACK"
        ? session.back_preview_file_id || session.front_preview_file_id
        : session.front_preview_file_id;
    if (!fileId) return null;
    return `${captureUrl(token, "/file")}?file_id=${encodeURIComponent(fileId)}`;
  })();

  const handleFile = async (file: File) => {
    if (!token || !session || session.step === "COMPLETE") return;
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

    const url = URL.createObjectURL(normalized);
    setLocalPreview((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return url;
    });

    const docType = session.step === "FRONT" ? "CDL_FRONT" : "CDL_BACK";
    setPhase("UPLOADING");
    const timer = window.setTimeout(() => setPhase("SCANNING"), 600);
    try {
      const form = new FormData();
      form.append("doc_type", docType);
      form.append("file", normalized);
      const res = await fetchWithTenant(captureUrl(token, "/upload"), {
        method: "POST",
        body: form,
      });
      window.clearTimeout(timer);
      if (isInvalidCaptureLinkStatus(res.status)) {
        setPhase("INVALID");
        return;
      }
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(
          typeof detail?.detail === "string"
            ? detail.detail
            : "Upload failed. Please try again.",
        );
        setPhase("READY");
        return;
      }
      const next = (await res.json()) as CaptureSession;
      setSession(next);
      if (next.message) setError(next.message);
      else setError(null);
      if (next.step !== session.step || next.step === "COMPLETE") {
        if (localPreview) URL.revokeObjectURL(localPreview);
        setLocalPreview(null);
      }
      setPhase("READY");
    } catch {
      window.clearTimeout(timer);
      setError("We could not upload your license right now. Please try again.");
      setPhase("READY");
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
        </div>
      </div>
    );
  }

  const busy = phase === "UPLOADING" || phase === "SCANNING";
  const stepLabel = session.step === "FRONT" ? "Front Driver Licence" : "Back Driver Licence";
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
          {busy ? (
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

        <button type="button" style={primary} disabled={busy} onClick={() => takeInputRef.current?.click()}>
          Take Photo
        </button>
        <button type="button" style={btn} disabled={busy} onClick={() => uploadInputRef.current?.click()}>
          Choose Existing Photo
        </button>
      </div>
    </div>
  );
}
