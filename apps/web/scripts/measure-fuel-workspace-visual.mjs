/**
 * Fuel workspace gutter + BVD txn header/body row heights (Chromium).
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const themes = readFileSync(join(here, "../src/styles/themes.css"), "utf8");
const fuelHome = readFileSync(join(here, "../src/pages/fuel/fuel-home.css"), "utf8");
const bvdCss = readFileSync(join(here, "../src/pages/fuelBvdReview/bvd-parsed-statement.css"), "utf8");

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root { --trk-border:#252A38; --trk-border-strong:#3A3F52; --trk-surface:#141720; --trk-surface-2:#1C1F2B; --trk-bg:#0D0F14; --trk-text:#E8ECF4; --trk-text-muted:#7A8299; --trk-accent:#60A5FA;
  --trk-layout-max-width: none; --trk-page-padding-x: 1.5rem; --trk-page-padding-y: 1.5rem; --trk-dense-gutter: clamp(0.5rem, 0.6vw, 0.75rem); }
*, *::before, *::after { box-sizing: border-box; }
html, body { margin:0; padding:0; background:var(--trk-bg); color:var(--trk-text); font-family:system-ui,sans-serif; }
${themes}
${fuelHome}
${bvdCss}
</style></head><body>
<div class="trk-app-shell">
  <main class="trk-app-main">
    <div class="trk-page trk-page--dense" data-testid="fuel-home">
      <section class="fuel-recent-activity" data-testid="fuel-recent-activity">
        <div class="fuel-activity-txn-contained">
          <div class="bvd-statement__table-wrap bvd-txn-rows" data-testid="bvd-txn-wrap">
            <table class="bvd-statement__table bvd-statement__table--txn bvd-txn-rows__table">
              <thead class="bvd-txn-rows__thead">
                <tr class="bvd-txn-rows__header-row">
                  <th class="bvd-txn-rows__col-chevron bvd-txn-rows__header-cell" scope="col"></th>
                  <th class="bvd-txn-rows__col-compact bvd-txn-rows__header-cell" scope="col"><button type="button" class="bvd-txn-rows__sort-btn"><span class="bvd-txn-rows__sort-label">Date / Time</span></button></th>
                  <th class="bvd-txn-rows__col-compact bvd-txn-rows__header-cell" scope="col"><button type="button" class="bvd-txn-rows__sort-btn"><span class="bvd-txn-rows__sort-label">Retail price</span></button></th>
                </tr>
              </thead>
              <tbody>
                <tr class="bvd-txn-rows__main">
                  <td class="bvd-txn-rows__chevron-cell">▸</td>
                  <td class="bvd-txn-rows__col-compact">Dec 10 03:22</td>
                  <td class="bvd-txn-rows__col-compact">3.1067</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  </main>
</div>
</body></html>`;

const browser = await chromium.launch();
for (const width of [1920, 1440]) {
  const page = await browser.newPage({ viewport: { width, height: 900 } });
  await page.setContent(html, { waitUntil: "load" });
  const m = await page.evaluate(() => {
    const doc = document.documentElement;
    const fuelHome = document.querySelector('[data-testid="fuel-home"]');
    const main = document.querySelector(".trk-app-main");
    const headerTh = document.querySelector("thead.bvd-txn-rows__thead th.bvd-txn-rows__header-cell:nth-child(2)");
    const bodyTd = document.querySelector("tbody tr.bvd-txn-rows__main td.bvd-txn-rows__col-compact");
    const fuelRect = fuelHome?.getBoundingClientRect();
    return {
      viewportWidth: doc.clientWidth,
      docClientWidth: doc.clientWidth,
      docScrollWidth: doc.scrollWidth,
      leftGutter: fuelRect ? Math.round(fuelRect.left) : null,
      rightGutter: fuelRect ? Math.round(doc.clientWidth - fuelRect.right) : null,
      mainPaddingLeft: main ? getComputedStyle(main).paddingLeft : null,
      headerHeightPx: headerTh ? Math.round(headerTh.getBoundingClientRect().height) : null,
      bodyRowHeightPx: bodyTd
        ? Math.round(bodyTd.closest("tr").getBoundingClientRect().height)
        : null,
    };
  });
  console.log(`\n=== ${width}px ===\n${JSON.stringify(m, null, 2)}`);
  await page.close();
}
await browser.close();
