import { describe, expect, it, vi } from "vitest";
import {
  columnSyncWidthPx,
  syncTableHeaderColumnWidths,
} from "./processedChargeTableStickyLayout";

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
    Object.defineProperty(tds[0], "scrollWidth", { value: 40, configurable: true });
    Object.defineProperty(tds[1], "scrollWidth", { value: 80, configurable: true });
    const ths = header.querySelectorAll("th");
    Object.defineProperty(ths[0], "scrollWidth", { value: 40, configurable: true });
    Object.defineProperty(ths[1], "scrollWidth", { value: 80, configurable: true });
    syncTableHeaderColumnWidths(body, header);
    expect(ths[0]?.style.width).toBe("40px");
    expect(ths[1]?.style.width).toBe("80px");
    expect(body.style.width).toBe("120px");
    expect(header.style.width).toBe("120px");
  });

  it("header minimum wins when body column is squeezed narrower than header label", () => {
    document.body.innerHTML = `
      <table id="body"><tbody><tr><td>3.9890</td></tr></tbody></table>
      <table id="header"><thead><tr><th><span>Retail price</span></th></tr></thead></table>
    `;
    const body = document.getElementById("body") as HTMLTableElement;
    const header = document.getElementById("header") as HTMLTableElement;
    const td = body.querySelector("td") as HTMLCellElement;
    const th = header.querySelector("th") as HTMLTableCellElement;
    vi.spyOn(td, "getBoundingClientRect").mockReturnValue({ width: 55 } as DOMRect);
    Object.defineProperty(td, "scrollWidth", { value: 55, configurable: true });
    vi.spyOn(th, "getBoundingClientRect").mockReturnValue({ width: 55 } as DOMRect);
    Object.defineProperty(th, "scrollWidth", { value: 78, configurable: true });
    const widthPx = columnSyncWidthPx(td, th);
    expect(widthPx).toBe(78);
    syncTableHeaderColumnWidths(body, header);
    expect(th.style.width).toBe("78px");
    expect(td.style.width).toBe("78px");
  });
});
