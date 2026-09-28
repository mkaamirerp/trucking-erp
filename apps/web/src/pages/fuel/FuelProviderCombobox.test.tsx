import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import FuelProviderCombobox from "./FuelProviderCombobox";

const catalog = [
  { provider_code: "BVD", display_name: "BVD", connection_methods: [], supported_connection_methods: [] },
  { provider_code: "WEX", display_name: "WEX", connection_methods: [], supported_connection_methods: [] },
  { provider_code: "PILOT", display_name: "Pilot", connection_methods: [], supported_connection_methods: [] },
];

describe("FuelProviderCombobox", () => {
  let container: HTMLDivElement;
  let root: Root;

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("opens dropdown with search inside; no standalone page search", async () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    await act(async () => {
      root.render(
        <FuelProviderCombobox catalog={catalog} value="BVD" onChange={() => undefined} />,
      );
    });
    expect(container.querySelector('input[placeholder="Search…"]')).toBeNull();
    const trigger = container.querySelector('[data-testid="fuel-provider-combobox-trigger"]') as HTMLButtonElement;
    await act(async () => {
      trigger.click();
    });
    const search = container.querySelector('[data-testid="fuel-provider-combobox-search"]') as HTMLInputElement;
    expect(search).toBeTruthy();
    expect(search.placeholder).toBe("Search providers...");
    await act(async () => {
      search.value = "wex";
      search.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(container.textContent).toContain("WEX");
  });
});
