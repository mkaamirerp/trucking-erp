import { act, useState, type ReactNode } from "react";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { LoadCustodySnapshot, TripDetail, TripMemberLoad } from "@/api";
import TripCustodyPanel, { type CustodyPanelApi } from "./TripCustodyPanel";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function member(status: string): TripMemberLoad {
  return {
    trip_load_id: 1,
    load_id: 9,
    status_within_trip: status,
    sequence_hint: 0,
    added_at: "2026-10-16T00:00:00Z",
    completed_at: status === "completed" ? "2026-10-16T02:00:00Z" : null,
    removed_at: null,
    load_number: "L9",
  };
}

function trip(status: string, membership: string): TripDetail {
  return {
    id: 3,
    tenant_id: 1,
    trip_number: "T3",
    status,
    job_type: "linehaul",
    driver_id: 1,
    truck_id: 2,
    trailer_id: 8,
    cancelled_at: null,
    created_at: "2026-10-16T00:00:00Z",
    updated_at: "2026-10-16T00:00:00Z",
    member_loads: [member(membership)],
  };
}

function snap(partial: Partial<LoadCustodySnapshot>): LoadCustodySnapshot {
  return { load_id: 9, custody_owner: "unknown", custody_placement: "unknown", ...partial };
}

function mount(node: ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(node);
  });
}

async function settle() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

function api(overrides: Partial<CustodyPanelApi> = {}): CustodyPanelApi {
  return {
    listTerminals: async () => ({ items: [{ id: 4, name: "Albany Yard", is_active: true }] }),
    getLoadCustody: async () => snap({ custody_owner: "trip", custody_trip_id: 3, custody_placement: "on_trailer" }),
    acceptLoadCustody: async () => ({}),
    takeLoadCustody: async () => ({}),
    yardHandoffLoad: async () => ({}),
    finalDeliveryLoad: async () => ({}),
    completeTrip: async () => trip("completed", "completed"),
    ...overrides,
  };
}

describe("TripCustodyPanel", () => {
  it("keeps handoff and trip completion as separate actions", async () => {
    const calls = { handoff: 0, complete: 0 };
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "active")}
        api={api({
          yardHandoffLoad: async (_tripId, _loadId, body) => {
            calls.handoff += 1;
            expect(body).toEqual({ terminal_id: 4, placement: "staged" });
            return {};
          },
          completeTrip: async () => {
            calls.complete += 1;
            return trip("completed", "completed");
          },
        })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    const complete = container.querySelector("[data-testid='complete-trip']") as HTMLButtonElement;
    expect(complete.disabled).toBe(true);
    act(() => {
      complete.click();
    });
    expect(calls.complete).toBe(0);

    const terminal = container.querySelector("[data-testid='handoff-terminal-9']") as HTMLSelectElement;
    const placement = container.querySelector("[data-testid='handoff-placement-9']") as HTMLSelectElement;
    const handoff = container.querySelector("[data-testid='handoff-9']") as HTMLButtonElement;
    expect(handoff.disabled).toBe(true);
    await act(async () => {
      terminal.value = "4";
      terminal.dispatchEvent(new Event("change", { bubbles: true }));
      placement.value = "staged";
      placement.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(handoff.disabled).toBe(false);
    await act(async () => {
      handoff.click();
    });
    await settle();
    expect(calls.handoff).toBe(1);
    expect(calls.complete).toBe(0);
  });

  it("shows Accept or Take Custody only for the matching planned state", async () => {
    mount(
      <TripCustodyPanel
        trip={trip("assigned", "planned")}
        api={api({ getLoadCustody: async () => snap({ custody_owner: "unknown", custody_placement: "unknown" }) })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    expect(container.querySelector("[data-testid='accept-custody-9']")).not.toBeNull();
    expect(container.querySelector("[data-testid='take-custody-9']")).toBeNull();
    expect(container.querySelector("[data-testid='handoff-9']")).toBeNull();

    act(() => root.unmount());
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "planned")}
        api={api({
          getLoadCustody: async () =>
            snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" }),
        })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    expect(container.querySelector("[data-testid='take-custody-9']")).not.toBeNull();
    expect(container.querySelector("[data-testid='accept-custody-9']")).toBeNull();
  });

  it("refreshes membership and custody after a successful handoff", async () => {
    function Host() {
      const [current, setCurrent] = useState(trip("in_progress", "active"));
      return (
        <TripCustodyPanel
          trip={current}
          api={api({
            getLoadCustody: async () =>
              current.member_loads[0].status_within_trip === "completed"
                ? snap({ custody_owner: "terminal", custody_terminal_id: 4, custody_placement: "staged" })
                : snap({ custody_owner: "trip", custody_trip_id: 3, custody_placement: "on_trailer" }),
            yardHandoffLoad: async () => ({}),
          })}
          onRefresh={async () => setCurrent(trip("in_progress", "completed"))}
        />
      );
    }
    mount(<Host />);
    await settle();
    expect(container.querySelector("[data-testid='custody-label-9']")?.textContent).toContain("trip 3");
    const terminal = container.querySelector("[data-testid='handoff-terminal-9']") as HTMLSelectElement;
    const placement = container.querySelector("[data-testid='handoff-placement-9']") as HTMLSelectElement;
    await act(async () => {
      terminal.value = "4";
      terminal.dispatchEvent(new Event("change", { bubbles: true }));
      placement.value = "on_trailer";
      placement.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      (container.querySelector("[data-testid='handoff-9']") as HTMLButtonElement).click();
    });
    await settle();
    expect(container.querySelector("[data-testid='membership-9']")?.textContent).toContain("completed");
    expect(container.querySelector("[data-testid='custody-label-9']")?.textContent).toContain("terminal 4");
    expect(container.querySelector("[data-testid='handoff-9']")).toBeNull();
    expect((container.querySelector("[data-testid='complete-trip']") as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows the backend error and does not change the displayed membership", async () => {
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "active")}
        api={api({
          yardHandoffLoad: async () => {
            throw new Error(JSON.stringify({ detail: { detail: "Terminal is inactive", code: "TERMINAL_INACTIVE" } }));
          },
        })}
        onRefresh={async () => {
          throw new Error("refresh should not run");
        }}
      />,
    );
    await settle();
    const terminal = container.querySelector("[data-testid='handoff-terminal-9']") as HTMLSelectElement;
    const placement = container.querySelector("[data-testid='handoff-placement-9']") as HTMLSelectElement;
    await act(async () => {
      terminal.value = "4";
      terminal.dispatchEvent(new Event("change", { bubbles: true }));
      placement.value = "staged";
      placement.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {
      (container.querySelector("[data-testid='handoff-9']") as HTMLButtonElement).click();
    });
    await settle();
    expect(container.querySelector("[data-testid='custody-action-error']")?.textContent).toBe(
      "Terminal is inactive (TERMINAL_INACTIVE)",
    );
    expect(container.querySelector("[data-testid='membership-9']")?.textContent).toContain("active");
  });

  it("hides Final Delivery when the Trip is not in progress or does not hold the Load", async () => {
    mount(
      <TripCustodyPanel
        trip={trip("assigned", "active")}
        api={api()}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    expect(container.querySelector("[data-testid='final-delivery-9']")).toBeNull();
    act(() => root.unmount());
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "active")}
        api={api({
          getLoadCustody: async () => snap({ custody_owner: "unknown", custody_placement: "unknown" }),
        })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    expect(container.querySelector("[data-testid='final-delivery-9']")).toBeNull();
  });

  it("confirms final delivery without completing the Trip", async () => {
    const calls = { deliver: 0, handoff: 0, complete: 0 };
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "active")}
        api={api({
          finalDeliveryLoad: async () => {
            calls.deliver += 1;
            return {};
          },
          yardHandoffLoad: async () => {
            calls.handoff += 1;
            return {};
          },
          completeTrip: async () => {
            calls.complete += 1;
            return trip("completed", "completed");
          },
        })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    const opener = container.querySelector("[data-testid='final-delivery-9']") as HTMLButtonElement;
    expect(opener).not.toBeNull();
    await act(async () => {
      opener.click();
    });
    expect(calls.deliver).toBe(0);
    await act(async () => {
      (container.querySelector("[data-testid='final-delivery-submit-9']") as HTMLButtonElement).click();
    });
    await settle();
    expect(calls.deliver).toBe(1);
    expect(calls.handoff).toBe(0);
    expect(calls.complete).toBe(0);
    expect((container.querySelector("[data-testid='complete-trip']") as HTMLButtonElement).disabled).toBe(true);
  });

  it("ignores a second handoff click while the first request is pending", async () => {
    let calls = 0;
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    mount(
      <TripCustodyPanel
        trip={trip("in_progress", "active")}
        api={api({
          yardHandoffLoad: async () => {
            calls += 1;
            await gate;
            return {};
          },
        })}
        onRefresh={async () => undefined}
      />,
    );
    await settle();
    const terminal = container.querySelector("[data-testid='handoff-terminal-9']") as HTMLSelectElement;
    const placement = container.querySelector("[data-testid='handoff-placement-9']") as HTMLSelectElement;
    await act(async () => {
      terminal.value = "4";
      terminal.dispatchEvent(new Event("change", { bubbles: true }));
      placement.value = "staged";
      placement.dispatchEvent(new Event("change", { bubbles: true }));
    });
    const handoff = container.querySelector("[data-testid='handoff-9']") as HTMLButtonElement;
    act(() => {
      handoff.click();
    });
    await settle();
    expect(calls).toBe(1);
    expect(handoff.disabled).toBe(true);
    act(() => {
      handoff.click();
    });
    expect(calls).toBe(1);
    await act(async () => {
      release();
    });
  });
});
