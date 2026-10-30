import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const getPersonApplicationForAdmin = vi.fn();
const getCompanyProfile = vi.fn();
const markAdminReviewEngaged = vi.fn();
const materializePersonForCombinedSetup = vi.fn();
const getCombinedDriverApproveReadiness = vi.fn();
const approvePersonApplicationForAdmin = vi.fn();

vi.mock("../api", () => ({
  getPersonApplicationForAdmin: (...a: unknown[]) => getPersonApplicationForAdmin(...a),
  getCompanyProfile: (...a: unknown[]) => getCompanyProfile(...a),
  markAdminReviewEngaged: (...a: unknown[]) => markAdminReviewEngaged(...a),
  materializePersonForCombinedSetup: (...a: unknown[]) => materializePersonForCombinedSetup(...a),
  getCombinedDriverApproveReadiness: (...a: unknown[]) => getCombinedDriverApproveReadiness(...a),
  approvePersonApplicationForAdmin: (...a: unknown[]) => approvePersonApplicationForAdmin(...a),
}));

import DriverOnboardingAdminDetailPage from "./DriverOnboardingAdminDetailPage";

const submitted = (over: Record<string, unknown> = {}) => ({
  id: 60,
  status: "SUBMITTED",
  application_type: "DRIVER",
  requested_role_code: "DRIVER",
  person_id: 9,
  reviewed_at: "2026-10-01T00:00:00Z",
  first_name: "Jane",
  last_name: "Driver",
  intake_payload: {},
  ...over,
});

function textButtons(label: string): HTMLButtonElement[] {
  return Array.from(document.querySelectorAll("button")).filter(
    (b) => b.textContent?.trim() === label,
  ) as HTMLButtonElement[];
}

describe("approve confirmation", () => {
  let root: Root;
  let host: HTMLDivElement;

  beforeEach(() => {
    vi.clearAllMocks();
    getCompanyProfile.mockResolvedValue({ person_setup_ui_mode: "segmented" });
    getCombinedDriverApproveReadiness.mockResolvedValue({ applies: false, ready: true });
    host = document.createElement("div");
    document.body.appendChild(host);
    root = createRoot(host);
  });

  afterEach(() => {
    act(() => root.unmount());
    host.remove();
  });

  async function render() {
    await act(async () => {
      root.render(
        <MemoryRouter initialEntries={["/admin/onboarding/60"]}>
          <Routes>
            <Route path="/admin/onboarding/:id" element={<DriverOnboardingAdminDetailPage />} />
          </Routes>
        </MemoryRouter>,
      );
    });
  }

  it("confirms before approving and prevents a second submit", async () => {
    getPersonApplicationForAdmin.mockResolvedValue(submitted());
    let resolveApprove: (v: unknown) => void = () => {};
    approvePersonApplicationForAdmin.mockReturnValue(new Promise((r) => { resolveApprove = r; }));
    await render();

    expect(textButtons("APPROVE").length).toBeGreaterThan(0);
    expect(document.querySelector('[data-testid="approve-confirm-dialog"]')).toBeNull();
    expect(approvePersonApplicationForAdmin).not.toHaveBeenCalled();

    await act(async () => { textButtons("APPROVE")[0].click(); });
    const dialog = document.querySelector('[data-testid="approve-confirm-dialog"]')!;
    expect(dialog.textContent).toContain("makes this person an active driver who can be assigned to trips");
    expect(dialog.textContent).toContain("No email is sent");
    expect(dialog.textContent).toContain("stays pending until you mark onboarding complete");
    expect(approvePersonApplicationForAdmin).not.toHaveBeenCalled();

    const confirm = document.querySelector('[data-testid="approve-confirm-button"]') as HTMLButtonElement;
    await act(async () => { confirm.click(); });
    await act(async () => { confirm.click(); });
    expect(approvePersonApplicationForAdmin).toHaveBeenCalledTimes(1);
    expect(approvePersonApplicationForAdmin).toHaveBeenCalledWith(60);
    expect(confirm.textContent).toBe("Approving...");
    expect(confirm.disabled).toBe(true);

    await act(async () => { resolveApprove(submitted({ status: "APPROVED" })); });
    expect(document.querySelector('[data-testid="approve-confirm-dialog"]')).toBeNull();
    expect(textButtons("APPROVE").length).toBe(0);
  });

  it("cancel closes the dialog without approving", async () => {
    getPersonApplicationForAdmin.mockResolvedValue(submitted());
    await render();
    await act(async () => { textButtons("APPROVE APPLICATION")[0].click(); });
    await act(async () => { textButtons("Cancel")[0].click(); });
    expect(document.querySelector('[data-testid="approve-confirm-dialog"]')).toBeNull();
    expect(approvePersonApplicationForAdmin).not.toHaveBeenCalled();
  });
});
