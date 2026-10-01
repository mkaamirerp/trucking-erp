/**
 * Page-scroll sticky processed headers (no nested vertical scroll on charge grids).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const themes = readFileSync(join(here, "../src/styles/themes.css"), "utf8");
const fuelHome = readFileSync(join(here, "../src/pages/fuel/fuel-home.css"), "utf8");
const bvdCss = readFileSync(join(here, "../src/pages/fuelBvdReview/bvd-parsed-statement.css"), "utf8");

const cardRows = Array.from({ length: 24 }, (_, i) => `<tr class="bvd-txn-rows__main">
  <td class="bvd-txn-rows__chevron-cell">▸</td><td class="bvd-txn-rows__col-compact">Dec ${i}</td>
  <td class="bvd-txn-rows__col-compact">${6600 + i}</td><td class="bvd-txn-rows__col-flex">Driver</td>
  <td class="bvd-txn-rows__col-compact">155.77</td></tr>`).join("");

const stickyShell = (id, testId, bodyRows) => `
<section class="processed-statement-section processed-statement-section--charges">
  <div class="bvd-processed-charge-table bvd-txn-rows" data-testid="${testId}">
    <div class="bvd-processed-charge-table__sticky-host" data-testid="${id}">
      <div class="bvd-processed-charge-table__sticky-clip">
        <div class="bvd-processed-charge-table__sticky-track" id="${id}-track">
          <table class="bvd-statement__table bvd-txn-rows__table bvd-processed-charge-table__header-table">
            <thead class="bvd-txn-rows__thead"><tr class="bvd-txn-rows__header-row">
              <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-chevron"></th>
              <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact" data-h="${id}">Date</th>
              <th class="bvd-txn-rows__header-cell">Unit</th><th class="bvd-txn-rows__header-cell">Driver</th>
              <th class="bvd-txn-rows__header-cell">Amt</th>
            </tr></thead>
          </table>
        </div>
      </div>
    </div>
    <div class="bvd-processed-charge-table__hscroll" id="${id}-hscroll">
      <table class="bvd-statement__table bvd-txn-rows__table" id="${id}-body">
        <tbody>${bodyRows}</tbody>
      </table>
    </div>
  </div>
</section>`;

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
:root { --trk-heading:#F59E0B; --trk-border:#252A38; --trk-surface:#141720; --trk-surface-2:#1C1F2B; --trk-bg:#0D0F14; --trk-text:#E8ECF4; }
html,body{margin:0;height:100%} body{background:var(--trk-bg);color:var(--trk-text);font-family:system-ui}
.trk-app-shell{display:flex;flex-direction:column;min-height:100vh}
.trk-app-main{flex:1 1 auto;overflow:auto;padding:12px;min-height:0;height:0}
${themes}${fuelHome}${bvdCss}
</style></head><body>
<div class="trk-app-shell">
<header style="position:sticky;top:0;z-index:40;height:3.5rem;background:#111;border-bottom:1px solid #333;display:flex;align-items:center;padding:0 16px">FleetPro Nav</header>
<main class="trk-app-main">
${stickyShell("card-sticky", "card-table", cardRows)}
${stickyShell("express-sticky", "express-table", cardRows.slice(0, 400))}
</main>
</div>
<script>
function sync(bodyId, trackId) {
  const body = document.getElementById(bodyId);
  const header = document.querySelector('#' + trackId + ' table');
  const row = body?.querySelector('tr');
  const hrow = header?.querySelector('tr');
  if (!row || !hrow) return;
  const cells = row.querySelectorAll('td');
  const ths = hrow.querySelectorAll('th');
  for (let i = 0; i < Math.min(cells.length, ths.length); i++) {
    const w = cells[i].getBoundingClientRect().width;
    ths[i].style.width = w + 'px';
  }
  if (header) header.style.width = body.getBoundingClientRect().width + 'px';
}
sync('card-sticky-body', 'card-sticky-track');
document.getElementById('card-sticky-hscroll')?.addEventListener('scroll', (e) => {
  const t = document.getElementById('card-sticky-track');
  if (t) t.style.transform = 'translate3d(-' + e.target.scrollLeft + 'px,0,0)';
});
</script>
</body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 700 } });
await page.setContent(html, { waitUntil: "load" });

const before = await page.evaluate(() => {
  const h = document.querySelector('[data-h="card-sticky"]');
  return { cardHeaderTop: h ? Math.round(h.getBoundingClientRect().top) : null };
});

await page.evaluate(() => document.querySelector(".trk-app-main")?.scrollTo(0, 350));
await page.waitForTimeout(80);

const after = await page.evaluate(() => {
  const main = document.querySelector(".trk-app-main");
  const hscroll = document.getElementById("card-sticky-hscroll");
  const h = document.querySelector('[data-h="card-sticky"]');
  const nav = document.querySelector("header");
  return {
    mainScrollTop: main?.scrollTop,
    cardHeaderTop: h ? Math.round(h.getBoundingClientRect().top) : null,
    navBottom: nav ? Math.round(nav.getBoundingClientRect().bottom) : null,
    hscrollHasVerticalBar: hscroll ? hscroll.scrollHeight > hscroll.clientHeight + 1 : null,
    hscrollOverflowY: hscroll ? getComputedStyle(hscroll).overflowY : null,
    docScrollWidth: document.documentElement.scrollWidth,
    docClientWidth: document.documentElement.clientWidth,
    stickyHostPosition: getComputedStyle(document.querySelector('[data-testid="card-sticky"]')).position,
  };
});

console.log(JSON.stringify({ before, after }, null, 2));
await browser.close();
