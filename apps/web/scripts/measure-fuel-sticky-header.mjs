/**
 * Verify processed charge table sticky header + orange rule (Chromium).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const themes = readFileSync(join(here, "../src/styles/themes.css"), "utf8");
const fuelHome = readFileSync(join(here, "../src/pages/fuel/fuel-home.css"), "utf8");
const bvdCss = readFileSync(join(here, "../src/pages/fuelBvdReview/bvd-parsed-statement.css"), "utf8");

const rows = Array.from({ length: 40 }, (_, i) => `<tr class="bvd-txn-rows__main">
  <td class="bvd-txn-rows__chevron-cell">▸</td>
  <td class="bvd-txn-rows__col-compact">Dec ${10 + (i % 5)}</td>
  <td class="bvd-txn-rows__col-compact">${6600 + i}</td>
  <td class="bvd-txn-rows__col-flex">Driver ${i}</td>
  <td class="bvd-txn-rows__col-compact">155.77</td>
</tr>`).join("");

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
:root { --trk-heading:#F59E0B; --trk-border:#252A38; --trk-border-strong:#3A3F52; --trk-surface:#141720; --trk-surface-2:#1C1F2B; --trk-bg:#0D0F14; --trk-text:#E8ECF4; --trk-dense-gutter:12px; --trk-page-padding-x:1.5rem; --trk-page-padding-y:1.5rem; }
html,body{margin:0;height:100%} body{background:var(--trk-bg);color:var(--trk-text);font-family:system-ui}
.trk-app-main{height:400px;overflow:auto;padding:12px}
${themes}${fuelHome}${bvdCss}
</style></head><body>
<header style="position:sticky;top:0;z-index:40;height:56px;background:#111;border-bottom:1px solid #333">Nav</header>
<main class="trk-app-main">
  <section class="processed-statement-section processed-statement-section--charges">
    <div class="bvd-txn-rows bvd-statement__table-wrap" style="max-height:240px;overflow:auto">
      <table class="bvd-statement__table bvd-txn-rows__table bvd-statement__table--txn">
        <thead class="bvd-txn-rows__thead"><tr class="bvd-txn-rows__header-row">
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-chevron"></th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact">Date</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact">Unit</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-flex">Driver</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact">Amt</th>
        </tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  </section>
  <div style="height:200px"></div>
</main>
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 500 } });
await page.setContent(html, { waitUntil: "load" });
const before = await page.evaluate(() => {
  const th = document.querySelector("th.bvd-txn-rows__header-cell:nth-child(2)");
  const style = th ? getComputedStyle(th) : null;
  return {
    headerHeight: th ? Math.round(th.getBoundingClientRect().height) : null,
    position: style?.position,
    boxShadow: style?.boxShadow,
    top: style?.top,
    headerTopBeforeScroll: th ? Math.round(th.getBoundingClientRect().top) : null,
  };
});
const wrapTop = await page.evaluate(() => {
  const wrap = document.querySelector(".bvd-txn-rows.bvd-statement__table-wrap");
  return wrap ? Math.round(wrap.getBoundingClientRect().top) : null;
});
await page.evaluate(() => {
  document.querySelector(".bvd-txn-rows.bvd-statement__table-wrap")?.scrollTo(0, 200);
});
await page.waitForTimeout(100);
const after = await page.evaluate((expectedTop) => {
  const th = document.querySelector("th.bvd-txn-rows__header-cell:nth-child(2)");
  const wrap = document.querySelector(".bvd-txn-rows.bvd-statement__table-wrap");
  const doc = document.documentElement;
  const top = th ? Math.round(th.getBoundingClientRect().top) : null;
  return {
    headerTopAfterScroll: top,
    wrapTop: expectedTop,
    stickyHeld: top !== null && Math.abs(top - expectedTop) <= 2,
    docScrollWidth: doc.scrollWidth,
    docClientWidth: doc.clientWidth,
  };
}, wrapTop);
console.log(JSON.stringify({ before, after }, null, 2));
await browser.close();
