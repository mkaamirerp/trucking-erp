import { afterEach, describe, expect, it, vi } from "vitest";
import {
  copyTextToClipboard,
  isRestrictedDlCaptureUrl,
  NO_APPLICANT_EMAIL_MESSAGE,
  parseApiErrorDetail,
  QR_ISSUE_FAILED_MESSAGE,
  applyEmailCaptureLinkResponse,
  EMAIL_FAILED_LINK_READY_MESSAGE,
  DL_CAPTURE_EMAIL_HANDOFF_ENABLED,
} from "./dlCaptureHandoff";

describe("handoff helpers", () => {
  it("accepts restricted capture URLs only", () => {
    expect(isRestrictedDlCaptureUrl("https://demo.truckerp.me/dl-capture/abc")).toBe(true);
    expect(isRestrictedDlCaptureUrl("https://demo.truckerp.me/onboarding?token=invite")).toBe(false);
  });

  it("parses no-email API detail", () => {
    const err = new Error(JSON.stringify({ detail: NO_APPLICANT_EMAIL_MESSAGE }));
    expect(parseApiErrorDetail(err, "x")).toBe(NO_APPLICANT_EMAIL_MESSAGE);
  });

  it("QR failure fallback message", () => {
    expect(QR_ISSUE_FAILED_MESSAGE).toContain("Could not create the phone capture link");
  });

  it("SMTP failure updates captureLink for QR/copy and does not claim emailed", () => {
    const next = applyEmailCaptureLinkResponse({
      link: "https://demo.truckerp.me/dl-capture/new-restricted-token",
      emailed: false,
      email_error: "Could not send the capture link email. Try QR or copy link.",
    });
    expect(next.captureLink).toBe("https://demo.truckerp.me/dl-capture/new-restricted-token");
    expect(isRestrictedDlCaptureUrl(next.captureLink)).toBe(true);
    expect(next.emailFailed).toBe(true);
    expect(next.emailNote.toLowerCase()).not.toContain("capture link emailed");
    expect(next.emailNote).toMatch(/QR|copy/i);
    const ok = applyEmailCaptureLinkResponse({
      link: "https://demo.truckerp.me/dl-capture/ok-token",
      emailed: true,
    });
    expect(ok.emailFailed).toBe(false);
    expect(ok.emailNote).toBe("Capture link emailed");
    expect(ok.captureLink).toBe("https://demo.truckerp.me/dl-capture/ok-token");
  });

  it("SMTP failure without email_error still says QR/copy remain usable", () => {
    const next = applyEmailCaptureLinkResponse({
      link: "https://demo.truckerp.me/dl-capture/fallback-token",
      emailed: false,
    });
    expect(next.emailFailed).toBe(true);
    expect(next.captureLink).toContain("/dl-capture/fallback-token");
    expect(next.emailNote).toBe(EMAIL_FAILED_LINK_READY_MESSAGE);
  });

  it("email handoff capability is off until the live email endpoint is deployed", () => {
    expect(DL_CAPTURE_EMAIL_HANDOFF_ENABLED).toBe(false);
  });
});

describe("copyTextToClipboard", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("copies restricted capture URL via clipboard API", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    const url = "https://demo.truckerp.me/dl-capture/restricted-token";
    expect(isRestrictedDlCaptureUrl(url)).toBe(true);
    const ok = await copyTextToClipboard(url);
    expect(ok).toBe(true);
    expect(writeText).toHaveBeenCalledWith(url);
  });
});
