import { describe, expect, it } from "vitest";
import { applicantDlConfirmRequestUrl } from "./applicantDlConfirm";

const TOKEN = "Iij8sN52eiWNUcoVKfVNT8G04s5lQYGpBGvuhPelVFc";
const PAGE = "https://demo.truckerp.me";
const PATH = "/driver-onboarding/applicant/application/dl-confirm";
const QS = `?token=${encodeURIComponent(TOKEN)}`;

describe("applicantDlConfirmRequestUrl", () => {
  it("API_BASE empty → same-origin relative path at site root", () => {
    expect(
      applicantDlConfirmRequestUrl({
        onboardingToken: TOKEN,
        apiBase: "",
        pageOrigin: PAGE,
      }),
    ).toBe(`${PATH}${QS}`);
  });

  it("API_BASE /api/v1 → same-origin relative /api/v1 path", () => {
    expect(
      applicantDlConfirmRequestUrl({
        onboardingToken: TOKEN,
        apiBase: "/api/v1",
        pageOrigin: PAGE,
      }),
    ).toBe(`/api/v1${PATH}${QS}`);
  });

  it("API_BASE trailing slash is collapsed", () => {
    expect(
      applicantDlConfirmRequestUrl({
        onboardingToken: TOKEN,
        apiBase: "/api/v1/",
        pageOrigin: PAGE,
      }),
    ).toBe(`/api/v1${PATH}${QS}`);
  });

  it("absolute same-origin API_BASE stays relative for fetch", () => {
    expect(
      applicantDlConfirmRequestUrl({
        onboardingToken: TOKEN,
        apiBase: "https://demo.truckerp.me/api/v1",
        pageOrigin: PAGE,
      }),
    ).toBe(`/api/v1${PATH}${QS}`);
  });

  it("absolute different-origin API_BASE keeps the full URL", () => {
    expect(
      applicantDlConfirmRequestUrl({
        onboardingToken: TOKEN,
        apiBase: "https://api.example.test/api/v1",
        pageOrigin: PAGE,
      }),
    ).toBe(`https://api.example.test/api/v1${PATH}${QS}`);
  });

  it("does not use String.replace on window.location.origin", () => {
    const out = applicantDlConfirmRequestUrl({
      onboardingToken: `${PAGE}/evil`,
      apiBase: "/api/v1",
      pageOrigin: PAGE,
    });
    expect(out.startsWith("/api/v1")).toBe(true);
    expect(out).toContain(`token=${encodeURIComponent(`${PAGE}/evil`)}`);
    expect(out).not.toContain("https://demo.truckerp.me/driver-onboarding");
  });
});
