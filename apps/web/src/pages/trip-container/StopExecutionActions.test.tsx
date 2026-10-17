import { act, type ReactNode } from "react";

(globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import type { LoadStop } from "@/api";
import StopExecutionActions from "./StopExecutionActions";

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

function mount(node: ReactNode) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(node);
  });
}

const stop = {
  id: 4,
  load_id: 9,
  stop_type: "PICKUP",
  sequence: 0,
  arrived_at: null,
  departed_at: null,
} as LoadStop;

describe("StopExecutionActions", () => {
  it("confirms arrival without delivering the Load or completing the Trip", async () => {
    const calls = { arrival: 0, departure: 0, deliver: 0, complete: 0 };
    mount(
      <StopExecutionActions
        tripId={3}
        loadId={9}
        tripStatus="in_progress"
        membershipStatus="active"
        stop={stop}
        onRecorded={async () => undefined}
        recordArrival={async () => {
          calls.arrival += 1;
          return {
            trip_id: 3,
            load_id: 9,
            stop_id: 4,
            stop_type: "PICKUP",
            arrived_at: "2026-10-16T12:00:00Z",
            departed_at: null,
            replayed: false,
            load_status: "ready",
            trip_status: "in_progress",
            membership_status_within_trip: "active",
          };
        }}
        recordDeparture={async () => {
          calls.departure += 1;
          throw new Error("departure should not run");
        }}
      />,
    );
    const opener = container.querySelector("[data-testid='arrive-4']") as HTMLButtonElement;
    expect(opener).not.toBeNull();
    expect(container.querySelector("[data-testid='depart-4']")).toBeNull();
    await act(async () => {
      opener.click();
    });
    expect(calls.arrival).toBe(0);
    expect(calls.deliver).toBe(0);
    expect(calls.complete).toBe(0);
    await act(async () => {
      (container.querySelector("[data-testid='arrive-submit-4']") as HTMLButtonElement).click();
    });
    expect(calls.arrival).toBe(1);
    expect(calls.departure).toBe(0);
    expect(calls.deliver).toBe(0);
    expect(calls.complete).toBe(0);
  });

  it("shows the backend error and ignores a second click while the request is pending", async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    let calls = 0;
    mount(
      <StopExecutionActions
        tripId={3}
        loadId={9}
        tripStatus="in_progress"
        membershipStatus="active"
        stop={stop}
        onRecorded={async () => undefined}
        recordArrival={async () => {
          calls += 1;
          await gate;
          throw new Error(JSON.stringify({ detail: { detail: "Arrival rejected", code: "INVALID_STOP_TYPE" } }));
        }}
      />,
    );
    await act(async () => {
      (container.querySelector("[data-testid='arrive-4']") as HTMLButtonElement).click();
    });
    const submit = container.querySelector("[data-testid='arrive-submit-4']") as HTMLButtonElement;
    await act(async () => {
      submit.click();
      submit.click();
    });
    expect(calls).toBe(1);
    await act(async () => {
      release();
    });
    expect(container.querySelector("[data-testid='stop-execution-error-4']")?.textContent).toContain("Arrival rejected");
  });

  it("confirms unloading start without arrival, departure, delivery, or trip completion", async () => {
    const calls = { unload: 0, arrival: 0, departure: 0 };
    const drop = { ...stop, stop_type: "DROP", arrived_at: "2026-10-16T12:00:00Z", unloading_started_at: null };
    mount(
      <StopExecutionActions
        tripId={3}
        loadId={9}
        tripStatus="in_progress"
        membershipStatus="active"
        stop={drop}
        onRecorded={async () => undefined}
        recordArrival={async () => {
          calls.arrival += 1;
          throw new Error("arrival");
        }}
        recordDeparture={async () => {
          calls.departure += 1;
          throw new Error("departure");
        }}
        recordUnloadingStart={async () => {
          calls.unload += 1;
          return {
            trip_id: 3,
            load_id: 9,
            stop_id: 4,
            stop_type: "DROP",
            arrived_at: "2026-10-16T12:00:00Z",
            departed_at: null,
            unloading_started_at: "2026-10-16T12:05:00Z",
            unloading_completed_at: null,
            replayed: false,
            load_status: "ready",
            trip_status: "in_progress",
            membership_status_within_trip: "active",
          };
        }}
      />,
    );
    expect(container.querySelector("[data-testid='arrive-4']")).toBeNull();
    await act(async () => {
      (container.querySelector("[data-testid='unload-start-4']") as HTMLButtonElement).click();
    });
    expect(calls.unload).toBe(0);
    await act(async () => {
      (container.querySelector("[data-testid='unload-start-submit-4']") as HTMLButtonElement).click();
    });
    expect(calls.unload).toBe(1);
    expect(calls.arrival).toBe(0);
    expect(calls.departure).toBe(0);
  });
});
