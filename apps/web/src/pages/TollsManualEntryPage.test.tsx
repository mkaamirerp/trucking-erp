import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const apiMocks = vi.hoisted(() => ({
  listTollManualStages: vi.fn(),
  createTollManualStage: vi.fn(),
  patchTollManualStage: vi.fn(),
  validateTollManualStage: vi.fn(),
  discardTollManualStage: vi.fn(),
}));

vi.mock("../api", () => ({
  listTollManualStages: apiMocks.listTollManualStages,
  createTollManualStage: apiMocks.createTollManualStage,
  patchTollManualStage: apiMocks.patchTollManualStage,
  validateTollManualStage: apiMocks.validateTollManualStage,
  discardTollManualStage: apiMocks.discardTollManualStage,
}));

import TollsManualEntryPage from "./TollsManualEntryPage";

const stage = {
  stage_id: 4,
  source_type: "MANUAL",
  file_format: null,
  status: "DRAFT",
  event_date: "2026-03-01",
  event_time: "10:15",
  agency_raw: "ILTOLL",
  trip_charge: "7.35",
  transponder_number: "02400000001",
  plate_number: null,
  plate_state: null,
  entry_location: "I-90-WEST",
  exit_location: "I-94-EAST",
  notes: "roadside receipt",
  unresolved_vehicle_identity: false,
};

let root: Root | null = null;
let host: HTMLDivElement | null = null;

async function renderPage() {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      <MemoryRouter>
        <TollsManualEntryPage />
      </MemoryRouter>,
    );
  });
}

describe("TollsManualEntryPage", () => {
  beforeEach(() => {
    (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
    apiMocks.listTollManualStages.mockReset();
    apiMocks.createTollManualStage.mockReset();
    apiMocks.patchTollManualStage.mockReset();
    apiMocks.validateTollManualStage.mockReset();
    apiMocks.discardTollManualStage.mockReset();
    apiMocks.listTollManualStages.mockResolvedValue([]);
  });

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it("shows Manual Entry beside CSV and PDF without unit or payroll fields", async () => {
    await renderPage();
    expect(host?.textContent).toContain("CSV File Imports");
    expect(host?.textContent).toContain("PDF Reviews");
    expect(host?.textContent).toContain("Manual Entry");
    expect(host?.textContent).toContain("Toll date");
    expect(host?.textContent).toContain("Agency");
    expect(host?.textContent).toContain("Amount");
    expect(host?.textContent).toContain("Transponder");
    expect(host?.textContent).toContain("Plate");
    expect(host?.textContent).not.toContain("Driver");
    expect(host?.textContent).not.toContain("Owner Operator");
    expect(host?.textContent).not.toContain("Payroll");
    expect(host?.textContent).not.toContain("Settlement");
    expect(host?.textContent).not.toContain("Unit number");
  });

  it("creates and edits a MANUAL review stage", async () => {
    apiMocks.listTollManualStages.mockResolvedValueOnce([]).mockResolvedValue([stage]);
    apiMocks.createTollManualStage.mockResolvedValue(stage);
    apiMocks.patchTollManualStage.mockResolvedValue({ ...stage, notes: "updated evidence", status: "DRAFT" });
    await renderPage();
    const amount = Array.from(host!.querySelectorAll("label")).find((el) => el.textContent?.includes("Amount"));
    const input = amount!.querySelector("input") as HTMLInputElement;
    await act(async () => {
      input.value = "7.35";
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    const create = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Create draft");
    await act(async () => {
      create!.click();
    });
    expect(apiMocks.createTollManualStage).toHaveBeenCalled();
    expect(host?.textContent).toContain("source MANUAL");
    expect(host?.textContent).not.toContain("Tolls imported successfully");
    const save = Array.from(host!.querySelectorAll("button")).find((el) => el.textContent === "Save edits");
    await act(async () => {
      save!.click();
    });
    expect(apiMocks.patchTollManualStage).toHaveBeenCalledWith(4, expect.any(Object));
  });
});
