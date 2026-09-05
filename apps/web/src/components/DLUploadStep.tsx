import { useEffect, useMemo, useState } from "react";
import QRCode from "react-qr-code";
import { issueApplicantDlCaptureLink, emailApplicantDlCaptureLink } from "../api";
import { normalizeDlUpload } from "../lib/normalizeDlUpload";
import {
  copyTextToClipboard,
  NO_APPLICANT_EMAIL_MESSAGE,
  parseApiErrorDetail,
  QR_ISSUE_FAILED_MESSAGE,
  applyEmailCaptureLinkResponse,
  DL_CAPTURE_EMAIL_HANDOFF_ENABLED,
} from "../lib/dlCaptureHandoff";

type Side = "front" | "back";
type UploadState = "IDLE" | "UPLOADING" | "SCANNING" | "SUCCESS" | "FAILED";
type DocType = "CDL_FRONT" | "CDL_BACK";

type Props = {
  frontPreviewUrl: string | null;
  backPreviewUrl: string | null;
  frontState: UploadState;
  backState: UploadState;
  frontMessage?: string;
  backMessage?: string;
  onUploadSide: (side: Side, file: File) => Promise<boolean> | boolean;
  onNormalizeError?: (message: string) => void;
  onboardingToken?: string;
  intake?: Record<string, unknown>;
  disabled?: boolean;
  onRefreshApplication?: () => Promise<void>;
  onClearSavedData?: () => void;
  saving?: boolean;
};

type LocalPreviewState = { front: string | null; back: string | null };

function dlPreprocessStatus(intake: Record<string, unknown>, side: DocType): "MISSING" | "FAILED" | "PROCESSED" {
  const files = intake.files as Record<string, unknown> | undefined;
  const meta = files?.[side];
  if (!meta || typeof meta !== "object") return "MISSING";
  const status = (meta as { dl_preprocess_status?: string }).dl_preprocess_status;
  if (status === "PROCESSED") return "PROCESSED";
  if (status === "FAILED") return "FAILED";
  return "MISSING";
}

function sideBadge(state: UploadState, preprocess: "MISSING" | "FAILED" | "PROCESSED"): {
  label: string;
  tone: "waiting" | "busy" | "done" | "error";
} {
  if (state === "UPLOADING" || state === "SCANNING") return { label: "PROCESSING", tone: "busy" };
  if (state === "FAILED" || preprocess === "FAILED") return { label: "RETRY", tone: "error" };
  if (state === "SUCCESS" || preprocess === "PROCESSED") return { label: "RECEIVED", tone: "done" };
  return { label: "WAITING", tone: "waiting" };
}

function IdCardIcon({ variant }: { variant: "front" | "back" }) {
  return (
    <svg width="88" height="56" viewBox="0 0 120 76" fill="none" aria-hidden="true">
      <rect x="4" y="8" width="112" height="60" rx="6" fill="#1f2937" stroke="#4b5563" strokeWidth="1.5" />
      {variant === "front" ? (
        <>
          <rect x="14" y="18" width="28" height="34" rx="4" fill="#374151" />
          <rect x="50" y="20" width="52" height="6" rx="2" fill="#f97316" />
          <rect x="50" y="32" width="44" height="5" rx="2" fill="#4b5563" />
          <rect x="50" y="42" width="36" height="5" rx="2" fill="#4b5563" />
        </>
      ) : (
        <>
          <rect x="14" y="22" width="92" height="8" rx="2" fill="#4b5563" />
          <rect x="14" y="36" width="92" height="22" rx="3" fill="#374151" />
          <rect x="18" y="40" width="4" height="14" fill="#6b7280" />
          <rect x="24" y="40" width="2" height="14" fill="#6b7280" />
          <rect x="28" y="40" width="3" height="14" fill="#6b7280" />
          <rect x="34" y="40" width="2" height="14" fill="#6b7280" />
          <rect x="38" y="40" width="4" height="14" fill="#6b7280" />
          <rect x="44" y="40" width="2" height="14" fill="#6b7280" />
          <rect x="48" y="40" width="3" height="14" fill="#6b7280" />
        </>
      )}
    </svg>
  );
}

function Badge({ label, tone }: { label: string; tone: "waiting" | "busy" | "done" | "error" | "accent" }) {
  const styles: Record<string, string> = {
    waiting: "border-gray-600 bg-gray-700/50 text-gray-500",
    busy: "border-orange-500/40 bg-orange-500/10 text-orange-400",
    done: "border-green-500/40 bg-green-500/10 text-green-400",
    error: "border-rose-500/40 bg-rose-500/10 text-rose-400",
    accent: "border-orange-500/40 bg-orange-500/10 text-orange-400",
  };
  return (
    <span className={`rounded border px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest ${styles[tone]}`}>
      {label}
    </span>
  );
}

export default function DLUploadStep({
  frontPreviewUrl,
  backPreviewUrl,
  frontState,
  backState,
  frontMessage = "",
  backMessage = "",
  onUploadSide,
  onNormalizeError,
  onboardingToken,
  intake = {},
  disabled = false,
  onRefreshApplication,
  onClearSavedData,
  saving = false,
}: Props) {
  const [localPreview, setLocalPreview] = useState<LocalPreviewState>({ front: null, back: null });
  const [captureLink, setCaptureLink] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [checking, setChecking] = useState(false);
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [issueError, setIssueError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [emailing, setEmailing] = useState(false);
  const [emailNote, setEmailNote] = useState<string | null>(null);
  const [emailFailed, setEmailFailed] = useState(false);

  useEffect(() => {
    return () => {
      if (localPreview.front) URL.revokeObjectURL(localPreview.front);
      if (localPreview.back) URL.revokeObjectURL(localPreview.back);
    };
  }, [localPreview.back, localPreview.front]);

  useEffect(() => {
    if (!frontPreviewUrl || !localPreview.front) return;
    URL.revokeObjectURL(localPreview.front);
    setLocalPreview((prev) => ({ ...prev, front: null }));
  }, [frontPreviewUrl, localPreview.front]);

  useEffect(() => {
    if (!backPreviewUrl || !localPreview.back) return;
    URL.revokeObjectURL(localPreview.back);
    setLocalPreview((prev) => ({ ...prev, back: null }));
  }, [backPreviewUrl, localPreview.back]);

  useEffect(() => {
    if (!onboardingToken) {
      setCaptureLink(null);
      setIssueError(null);
      return;
    }
    let cancelled = false;
    setIssuing(true);
    setIssueError(null);
    void (async () => {
      try {
        const resp = await issueApplicantDlCaptureLink(onboardingToken);
        if (!cancelled) setCaptureLink(resp.link);
      } catch (e: unknown) {
        if (!cancelled) {
          setCaptureLink(null);
          setIssueError(parseApiErrorDetail(e, QR_ISSUE_FAILED_MESSAGE));
        }
      } finally {
        if (!cancelled) setIssuing(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [onboardingToken]);

  const frontPreview = useMemo(() => {
    if (frontState === "SUCCESS" || frontState === "FAILED") return frontPreviewUrl;
    if (frontState === "UPLOADING" || frontState === "SCANNING") return localPreview.front ?? frontPreviewUrl;
    return frontPreviewUrl ?? localPreview.front;
  }, [frontPreviewUrl, frontState, localPreview.front]);

  const backPreview = useMemo(() => {
    if (backState === "SUCCESS" || backState === "FAILED") return backPreviewUrl;
    if (backState === "UPLOADING" || backState === "SCANNING") return localPreview.back ?? backPreviewUrl;
    return backPreviewUrl ?? localPreview.back;
  }, [backPreviewUrl, backState, localPreview.back]);

  const frontPre = dlPreprocessStatus(intake, "CDL_FRONT");
  const backPre = dlPreprocessStatus(intake, "CDL_BACK");
  const bothProcessed = frontPre === "PROCESSED" && backPre === "PROCESSED";

  const handleFileSelect = async (side: Side, file: File) => {
    let normalizedFile: File;
    try {
      normalizedFile = await normalizeDlUpload(file);
    } catch (err) {
      const message =
        err instanceof Error && err.message
          ? `Could not prepare this image for upload (${err.message}). Please try again.`
          : "Could not prepare this image for upload. Please try again.";
      onNormalizeError?.(message);
      return;
    }

    const url = URL.createObjectURL(normalizedFile);
    setLocalPreview((prev) => {
      const old = side === "front" ? prev.front : prev.back;
      if (old) URL.revokeObjectURL(old);
      return side === "front" ? { ...prev, front: url } : { ...prev, back: url };
    });
    await onUploadSide(side, normalizedFile);
  };

  const openFilePicker = (side: Side) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "image/*";
    input.capture = "environment";
    input.onchange = () => {
      const file = input.files?.[0];
      if (file) void handleFileSelect(side, file);
    };
    input.click();
  };

  async function retryQr() {
    if (!onboardingToken || issuing) return;
    setIssuing(true);
    setIssueError(null);
    try {
      const resp = await issueApplicantDlCaptureLink(onboardingToken);
      setCaptureLink(resp.link);
    } catch (e: unknown) {
      setCaptureLink(null);
      setIssueError(parseApiErrorDetail(e, QR_ISSUE_FAILED_MESSAGE));
    } finally {
      setIssuing(false);
    }
  }

  async function handleOpenCapture() {
    if (!onboardingToken || issuing) return;
    setPhoneError(null);
    if (captureLink) {
      window.open(captureLink, "_blank", "noopener,noreferrer");
      return;
    }
    setIssuing(true);
    try {
      const resp = await issueApplicantDlCaptureLink(onboardingToken);
      setCaptureLink(resp.link);
      window.open(resp.link, "_blank", "noopener,noreferrer");
    } catch (e: unknown) {
      setIssueError(parseApiErrorDetail(e, QR_ISSUE_FAILED_MESSAGE));
    } finally {
      setIssuing(false);
    }
  }

  async function handleCopyLink() {
    if (!captureLink) return;
    const ok = await copyTextToClipboard(captureLink);
    if (ok) {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } else {
      setPhoneError("Could not copy the capture link.");
    }
  }

  async function handleEmailCaptureLink() {
    if (!DL_CAPTURE_EMAIL_HANDOFF_ENABLED) return;
    if (!onboardingToken || emailing) return;
    setEmailNote(null);
    setEmailFailed(false);
    setEmailing(true);
    try {
      const resp = await emailApplicantDlCaptureLink(onboardingToken);
      const next = applyEmailCaptureLinkResponse(resp);
      setCaptureLink(next.captureLink);
      setEmailNote(next.emailNote);
      setEmailFailed(next.emailFailed);
    } catch (e: unknown) {
      const detail = parseApiErrorDetail(e, "Could not email the capture link.");
      setEmailNote(detail.includes("No applicant email") ? NO_APPLICANT_EMAIL_MESSAGE : detail);
      setEmailFailed(true);
    } finally {
      setEmailing(false);
    }
  }

  async function handleCheckStatus() {
    if (!onRefreshApplication || checking || disabled) return;
    setPhoneError(null);
    setChecking(true);
    try {
      await onRefreshApplication();
    } catch (e: unknown) {
      setPhoneError(e instanceof Error && e.message ? e.message : "Could not refresh application status.");
    } finally {
      setChecking(false);
    }
  }

  function renderSideCard(
    side: Side,
    label: string,
    hint: string,
    preview: string | null,
    state: UploadState,
    message: string,
    preprocess: "MISSING" | "FAILED" | "PROCESSED",
  ) {
    const badge = sideBadge(state, preprocess);
    const stageBusy = state === "UPLOADING" || state === "SCANNING";
    const uploadLabel = side === "front" ? "Upload Front DL" : "Upload Back DL";
    const received = badge.tone === "done";
    const failed = badge.tone === "error";

    return (
      <div
        className={`flex flex-col rounded-xl border p-4 ${
          received
            ? "border-green-500/40 bg-green-500/5"
            : failed
              ? "border-rose-500/60 bg-rose-500/5"
              : "border-gray-700 bg-gray-800/60"
        }`}
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-widest text-orange-400">{label}</span>
          <Badge label={badge.label} tone={badge.tone} />
        </div>

        <div
          className={`relative mb-3 flex min-h-[7.5rem] flex-col items-center justify-center overflow-hidden rounded-lg p-3 ${
            received
              ? "border border-green-500/40 bg-gray-900/40"
              : "border-2 border-dashed border-gray-600 bg-gray-900/40"
          }`}
        >
          {stageBusy ? (
            <div className="flex flex-col items-center gap-2 text-center">
              <div className="h-7 w-7 animate-spin rounded-full border-2 border-gray-600 border-t-orange-500" />
              <p className="text-xs text-gray-400">{message || "Processing licence image…"}</p>
            </div>
          ) : preview ? (
            <img
              src={preview}
              alt={`${label} preview`}
              className="max-h-[140px] w-full rounded-md object-contain"
            />
          ) : (
            <>
              <IdCardIcon variant={side} />
              <p className="mt-2 text-center text-xs font-medium text-gray-400">{hint}</p>
              <p className="mt-1 text-center text-[10px] text-gray-500">JPG, PNG up to 10 MB</p>
            </>
          )}
        </div>

        {state === "FAILED" && (
          <p className="mb-2 text-xs text-rose-400">{message || "Upload failed. Please try again."}</p>
        )}

        <button
          type="button"
          disabled={disabled || stageBusy}
          onClick={() => openFilePicker(side)}
          className="flex w-full items-center justify-center gap-2 rounded-lg border border-gray-600 px-3 py-2 text-xs font-medium text-gray-400 transition-all hover:border-orange-500 hover:text-orange-400 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
            <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {preview ? `Replace ${side === "front" ? "Front" : "Back"} DL` : uploadLabel}
        </button>
      </div>
    );
  }

  const statusRow = (
    sideLabel: string,
    sub: string,
    preprocess: "MISSING" | "FAILED" | "PROCESSED",
    state: UploadState,
    icon: "card" | "shield",
  ) => {
    const badge = sideBadge(state, preprocess);
    const done = preprocess === "PROCESSED" || state === "SUCCESS";
    return (
      <div className="flex items-start gap-3 border-b border-gray-700 py-2.5 last:border-b-0">
        <div
          className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${
            done ? "bg-green-500/10 text-green-400" : "bg-gray-700/50 text-orange-400"
          }`}
        >
          {icon === "shield" ? (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <circle cx="8.5" cy="11" r="2" />
            </svg>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold text-white">{sideLabel}</div>
          <div className="text-xs text-gray-500">{sub}</div>
        </div>
        <Badge label={done && icon === "shield" ? "COMPLETE" : badge.label} tone={done ? "done" : badge.tone} />
      </div>
    );
  };

  return (
    <div className="rounded-2xl border border-gray-700 bg-gray-800/60 p-6 space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <div className="w-1 h-5 shrink-0 bg-orange-500 rounded" />
            <h2 className="text-xl font-black text-white uppercase tracking-wide">
              Driver&apos;s <span className="text-orange-400">License</span>
            </h2>
          </div>
          <p className="mt-1 text-sm text-gray-400 sm:ml-3">
            Upload clear photos of both sides of your current, valid commercial driver&apos;s license.
            You can upload from this computer or use your phone.
          </p>
        </div>
        {onClearSavedData && (
          <button
            type="button"
            onClick={() => onClearSavedData()}
            disabled={saving}
            className="shrink-0 rounded-xl border border-rose-500/40 bg-rose-500/10 px-4 py-2 text-xs font-bold uppercase tracking-widest text-rose-300 transition-all hover:bg-rose-500/20 disabled:opacity-50"
          >
            {saving ? "Clearing..." : "Clear Saved Data"}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 items-start gap-4 sm:grid-cols-2">
        {renderSideCard(
          "front",
          "Front",
          "Upload the front of your license",
          frontPreview,
          frontState,
          frontMessage,
          frontPre,
        )}
        {renderSideCard(
          "back",
          "Back",
          "Upload the back of your license",
          backPreview,
          backState,
          backMessage,
          backPre,
        )}
      </div>

      <div className="flex flex-col gap-4 rounded-xl border border-gray-700 bg-gray-900/40 p-4 sm:flex-row sm:items-center">
        <div className="flex shrink-0 items-center justify-center rounded-lg border border-gray-700 bg-gray-900/40 p-2">
          {captureLink ? (
            <div className="rounded-lg bg-white p-2">
              <QRCode value={captureLink} size={112} />
            </div>
          ) : (
            <div className="flex h-[128px] w-[128px] items-center justify-center px-2 text-center text-xs text-gray-500">
              {issuing ? "Preparing QR code…" : issueError ? "QR unavailable" : "QR code will appear here"}
            </div>
          )}
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-orange-400">Use your phone</span>
            <Badge label="FAST & EASY" tone="accent" />
          </div>
          <p className="mb-3 text-xs text-gray-500">
            {DL_CAPTURE_EMAIL_HANDOFF_ENABLED
              ? "Scan the QR code, copy the link, or email it to the applicant address on file."
              : "Scan the QR code, copy the link, or open capture on this device."}
          </p>

          {issueError && (
            <div className="mb-3">
              <p className="text-xs text-rose-400">{issueError}</p>
              <button
                type="button"
                disabled={disabled || issuing || !onboardingToken}
                onClick={() => void retryQr()}
                className="mt-2 rounded-lg border border-rose-500/40 px-3 py-2 text-xs font-medium text-rose-300 hover:border-rose-400 disabled:opacity-50"
              >
                {issuing ? "Retrying…" : "Retry QR"}
              </button>
            </div>
          )}

          {!onboardingToken && (
            <p className="mb-3 text-xs text-gray-500">Phone capture is unavailable without an application invite.</p>
          )}

          <div className="mb-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={disabled || issuing || !onboardingToken}
              onClick={() => void handleOpenCapture()}
              className="flex items-center justify-center gap-2 rounded-lg border border-gray-600 px-3 py-2 text-xs font-medium text-gray-400 transition-all hover:border-orange-500 hover:text-orange-400 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="7" y="2" width="10" height="20" rx="2" />
                <path d="M11 18h2" strokeLinecap="round" />
              </svg>
              {issuing ? "Opening…" : "Open capture"}
            </button>
            <button
              type="button"
              disabled={disabled || !captureLink}
              onClick={() => void handleCopyLink()}
              className="rounded-lg border border-gray-600 px-3 py-2 text-xs font-medium text-gray-400 hover:border-orange-500 hover:text-orange-400 disabled:opacity-50"
            >
              {copied ? "Copied" : "Copy link"}
            </button>
            {DL_CAPTURE_EMAIL_HANDOFF_ENABLED && (
            <button
              type="button"
              disabled={disabled || emailing || !onboardingToken}
              onClick={() => void handleEmailCaptureLink()}
              className="rounded-lg border border-gray-600 px-3 py-2 text-xs font-medium text-gray-400 hover:border-orange-500 hover:text-orange-400 disabled:opacity-50"
            >
              {emailing ? "Sending…" : "Email capture link"}
            </button>
            )}
            <button
              type="button"
              disabled={disabled || checking || !onRefreshApplication}
              onClick={() => void handleCheckStatus()}
              className="rounded-lg border border-gray-600 px-3 py-2 text-xs font-medium text-gray-400 hover:border-orange-500 hover:text-orange-400 disabled:opacity-50"
            >
              {checking ? "Checking…" : "Check status"}
            </button>
          </div>

          {emailNote && (
            <p className={`mb-2 text-xs ${emailFailed ? "text-rose-400" : "text-green-400"}`}>{emailNote}</p>
          )}
          {phoneError && <p className="mt-2 text-xs text-rose-400">{phoneError}</p>}
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-gray-700 p-4">
          <span className="mb-3 block text-xs font-bold uppercase tracking-widest text-orange-400">Upload status</span>
          <div>
            {statusRow("Front of license", "Upload the front side", frontPre, frontState, "card")}
            {statusRow("Back of license", "Upload the back side", backPre, backState, "card")}
            {statusRow(
              "License complete",
              "Both sides received",
              bothProcessed ? "PROCESSED" : "MISSING",
              bothProcessed ? "SUCCESS" : "IDLE",
              "shield",
            )}
          </div>
        </div>

        <div className="rounded-xl border border-gray-700 p-4">
          <span className="mb-3 block text-xs font-bold uppercase tracking-widest text-orange-400">How it works</span>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {[
                { n: "1", title: "Scan or copy link", sub: DL_CAPTURE_EMAIL_HANDOFF_ENABLED ? "QR, copy, email, or open capture" : "QR, copy, or open capture" },
              { n: "2", title: "Take or choose front photo", sub: "Follow the on-screen guidance" },
              { n: "3", title: "Take or choose back photo", sub: "Follow the on-screen guidance" },
              { n: "4", title: "Return here and continue", sub: "We'll upload your photos automatically" },
            ].map((step) => (
              <div key={step.n} className="text-center">
                <div className="mx-auto mb-2 flex h-8 w-8 items-center justify-center rounded-full bg-orange-500 text-sm font-bold text-black">
                  {step.n}
                </div>
                <div className="text-xs font-semibold leading-snug text-white">{step.title}</div>
                <div className="mt-1 text-[10px] leading-snug text-gray-500">{step.sub}</div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <p className="flex items-center gap-2 text-xs text-gray-500">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
        Your data is secure and encrypted. Files are used only for verification.
      </p>
    </div>
  );
}
