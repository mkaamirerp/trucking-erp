/**
 * Fuel home page overflow probe (Chromium). Simulates app shell + expanded BVD txn table.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const here = dirname(fileURLToPath(import.meta.url));
const themes = readFileSync(join(here, "../src/styles/themes.css"), "utf8");
const fuelHome = readFileSync(join(here, "../src/pages/fuel/fuel-home.css"), "utf8");
const bvdCss = readFileSync(join(here, "../src/pages/fuelBvdReview/bvd-parsed-statement.css"), "utf8");
const fixture = JSON.parse(
  readFileSync(join(here, "../../../tests/fixtures/fuel_bvd_972201_expected.json"), "utf8"),
);
const rows = fixture.rows
  .filter((r) => r.row_type === "TRANSACTION")
  .slice(0, 12)
  .map((r, i) => ({ ...r, id: i + 1 }));

function txnTableBody() {
  const thead = `<tr>
  <th class="bvd-txn-rows__col-chevron"></th>
  <th class="bvd-txn-rows__col-compact">Date / Time</th>
  <th class="bvd-txn-rows__col-compact">Unit</th>
  <th class="bvd-txn-rows__col-flex bvd-txn-rows__col-driver">Source driver</th>
  <th class="bvd-txn-rows__col-flex">Location</th>
  <th class="bvd-txn-rows__col-compact">Product</th>
  <th class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">Qty</th>
  <th class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">Discount</th>
  <th class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">HST</th>
  <th class="bvd-txn-rows__col-compact bvd-txn-rows__col-amount">Final amount</th>
  <th class="bvd-txn-rows__col-compact">Currency</th>
</tr>`;
  const body = rows
    .map(
      (r) => `<tr class="bvd-purchase-row bvd-txn-rows__main">
    <td class="bvd-txn-rows__chevron-cell">▸</td>
    <td class="bvd-txn-rows__col-compact">${r.transaction_date}</td>
    <td class="bvd-txn-rows__col-compact">${r.unit_number}</td>
    <td class="bvd-txn-rows__col-flex bvd-txn-rows__col-driver">${r.driver_name}</td>
    <td class="bvd-txn-rows__col-flex">${r.site_city}, ${r.prov_st}</td>
    <td class="bvd-txn-rows__col-compact">${r.prod}</td>
    <td class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">${r.qty}</td>
    <td class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">${r.disc_amt}</td>
    <td class="bvd-txn-rows__col-compact bvd-txn-rows__col-numeric">${r.hst}</td>
    <td class="bvd-txn-rows__col-compact bvd-txn-rows__col-amount">${r.final_amt}</td>
    <td class="bvd-txn-rows__col-compact">${r.cur}</td>
  </tr>`,
    )
    .join("");
  return `<div class="bvd-statement__table-wrap bvd-txn-rows" data-testid="bvd-txn-wrap">
    <table class="bvd-statement__table bvd-statement__table--txn bvd-statement__table--purchases bvd-txn-rows__table">
      <thead>${thead}</thead><tbody>${body}</tbody>
    </table></div>`;
}

function pageHtml() {
  return `<!DOCTYPE html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width, initial-scale=1"/>
<style>
:root { --trk-border:#333; --trk-surface:#1a1a1a; --trk-surface-2:#222; --trk-bg:#111; --trk-text:#eee; --trk-text-muted:#aaa; --trk-accent:#3b82f6;
  --trk-layout-max-width: 100%; --trk-page-padding-x: 1.5rem; --trk-page-padding-y: 1.5rem; --trk-dense-gutter: 0.75rem; }
*, *::before, *::after { box-sizing: border-box; }
html, body { margin:0; padding:0; background:#111; color:#eee; font-family:system-ui,sans-serif; }
${themes}
${fuelHome}
${bvdCss}
</style></head><body>
<div class="trk-app-shell">
  <div style="height:48px;border-bottom:1px solid #333">nav</div>
  <main class="trk-app-main">
    <div class="trk-page trk-page--dense" data-testid="fuel-home">
      <section class="fuel-recent-activity rounded-lg border px-3 py-2" data-testid="fuel-recent-activity">
        <div class="trk-scroll-x fuel-recent-activity__scroll">
          <table class="fuel-recent-activity__table text-xs">
            <thead><tr><th></th><th>Provider</th><th>Invoice</th><th>Account</th><th>Period</th><th>Due</th><th>Pay</th><th>Disc</th><th>CAD</th><th>USD</th><th>Total</th><th></th></tr></thead>
            <tbody>
              <tr><td>▾</td><td>BVD</td><td>972201</td><td>4237111</td><td>Jul 2026</td><td>—</td><td>—</td><td>0</td><td>1</td><td>2</td><td>3</td><td>Open</td></tr>
              <tr><td colspan="12" class="fuel-recent-activity__detail-cell px-2 py-2">
                <div class="fuel-activity-txn-contained" data-testid="fuel-activity-txn-scroll">
                  <div class="bvd-statement-filters"><div class="bvd-statement-filters__row">
                    <label class="bvd-statement-filters__label">Search</label>
                    <input class="bvd-statement-filters__search" />
                  </div></div>
                  ${txnTableBody()}
                </div>
              </td></tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  </main>
</div>
</body></html>`;
}

const browser = await chromium.launch();
for (const w of [1920, 1280, 1100, 900]) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 } });
  await page.setContent(pageHtml(), { waitUntil: "load" });
  const m = await page.evaluate(() => {
    const doc = document.documentElement;
    const record = document.querySelector("[data-testid='fuel-activity-txn-scroll']");
    const bvdWrap = document.querySelector("[data-testid='bvd-txn-wrap']");
    const pageHScroll = doc.scrollWidth > doc.clientWidth;
    const recordHScroll = record ? record.scrollWidth > record.clientWidth : false;
    const bvdHScroll = bvdWrap ? bvdWrap.scrollWidth > bvdWrap.clientWidth : false;
    return {
      docClientWidth: doc.clientWidth,
      docScrollWidth: doc.scrollWidth,
      pageHorizontalScrollbar: pageHScroll,
      recordClientWidth: record?.clientWidth ?? null,
      recordScrollWidth: record?.scrollWidth ?? null,
      recordHorizontalScrollbar: recordHScroll,
      bvdWrapClientWidth: bvdWrap?.clientWidth ?? null,
      bvdWrapScrollWidth: bvdWrap?.scrollWidth ?? null,
      bvdInternalScrollbar: bvdHScroll,
    };
  });
  console.log(`\n=== ${w}px ===\n${JSON.stringify(m, null, 2)}`);
  await page.close();
}
await browser.close();
