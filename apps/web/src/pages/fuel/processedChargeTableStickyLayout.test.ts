import { describe, expect, it, vi } from "vitest";
import { syncTableHeaderColumnWidths } from "./processedChargeTableStickyLayout";

describe("syncTableHeaderColumnWidths", () => {
  it("sets header cell widths from measured body cells", () => {
    document.body.innerHTML = `
      <table id="body"><tbody><tr><td>a</td><td>b</td></tr></tbody></table>
      <table id="header"><thead><tr><th></th><th></th></tr></thead></table>
    `;
    const body = document.getElementById("body") as HTMLTableElement;
    const header = document.getElementById("header") as HTMLTableElement;
    const tds = body.querySelectorAll("td");
    vi.spyOn(tds[0], "getBoundingClientRect").mockReturnValue({ width: 40 } as DOMRect);
    vi.spyOn(tds[1], "getBoundingClientRect").mockReturnValue({ width: 80 } as DOMRect);
    vi.spyOn(body, "getBoundingClientRect").mockReturnValue({ width: 120 } as DOMRect);
    syncTableHeaderColumnWidths(body, header);
    const ths = header.querySelectorAll("th");
    expect(ths[0]?.style.width).toBe("40px");
    expect(ths[1]?.style.width).toBe("80px");
    expect(header.style.width).toBe("120px");
  });
});
