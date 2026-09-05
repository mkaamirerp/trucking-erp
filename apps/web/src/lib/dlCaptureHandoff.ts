const CAPTURE_PATH = "/dl-capture/";

export function isRestrictedDlCaptureUrl(value: string): boolean {
  try {
    const url = new URL(value, "https://invalid.example");
    return url.pathname.includes(CAPTURE_PATH) && !url.pathname.includes("/onboarding");
  } catch {
    return value.includes(CAPTURE_PATH) && !value.includes("onboarding?token=");
  }
}

export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      /* fallback */
    }
  }
  if (typeof document === "undefined") return false;
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.setAttribute("readonly", "");
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  document.body.removeChild(ta);
  return ok;
}

export function parseApiErrorDetail(err: unknown, fallback: string): string {
  if (!(err instanceof Error) || !err.message) return fallback;
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) return parsed.detail.trim();
  } catch {
    /* not json */
  }
  const msg = err.message.trim();
  return msg || fallback;
}

export const NO_APPLICANT_EMAIL_MESSAGE = "No applicant email is available for this application.";
export const QR_ISSUE_FAILED_MESSAGE = "Could not create the phone capture link.";
export const EMAIL_FAILED_LINK_READY_MESSAGE =
  "Could not send the capture link email. QR and copy still work with the new link.";

/**
 * Email capture-link action. OFF while live API lacks
 * POST /applicant/application/dl-capture-link/email (frontend-only camera test).
 * Flip to true only after that endpoint is deployed.
 */
export const DL_CAPTURE_EMAIL_HANDOFF_ENABLED = false;

export function applyEmailCaptureLinkResponse(resp: {
  link: string;
  emailed?: boolean;
  email_error?: string | null;
}): { captureLink: string; emailNote: string; emailFailed: boolean } {
  if (resp.emailed) {
    return { captureLink: resp.link, emailNote: "Capture link emailed", emailFailed: false };
  }
  const note = (resp.email_error || "").trim() || EMAIL_FAILED_LINK_READY_MESSAGE;
  return { captureLink: resp.link, emailNote: note, emailFailed: true };
}
