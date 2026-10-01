/**
 * Page-scroll sticky headers + no nested vertical scroll on processed charge grids.
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

const expressRows = Array.from({ length: 12 }, (_, i) => `<tr class="bvd-express-rows__main">
  <td class="bvd-express-rows__col-compact">Dec ${i}</td><td class="bvd-express-rows__col-compact">110${i}</td>
  <td class="bvd-express-rows__col-flex">Express driver</td><td class="bvd-express-rows__col-compact">203.00</td></tr>`).join("");

const html = `<!DOCTYPE html><html><head><meta charset="utf-8"/>
<style>
:root { --trk-heading:#F59E0B; --trk-border:#252A38; --trk-border-strong:#3A3F52; --trk-surface:#141720; --trk-surface-2:#1C1F2B; --trk-bg:#0D0F14; --trk-text:#E8ECF4; --trk-dense-gutter:12px; --trk-page-padding-x:1.5rem; --trk-page-padding-y:1.5rem; --trk-topnav-height:3.5rem; }
html,body{margin:0;height:100%} body{background:var(--trk-bg);color:var(--trk-text);font-family:system-ui}
.trk-app-shell{display:flex;flex-direction:column;min-height:100vh}
.trk-app-main{flex:1 1 auto;overflow:auto;padding:12px;min-height:0;height:0}
${themes}${fuelHome}${bvdCss}
</style></head><body>
<div class="trk-app-shell">
<header style="position:sticky;top:0;z-index:40;height:var(--trk-topnav-height);background:#111;border-bottom:1px solid #333;display:flex;align-items:center;padding:0 16px">FleetPro Nav</header>
<main class="trk-app-main">
  <section class="processed-statement-section processed-statement-section--charges">
    <div class="bvd-txn-rows bvd-statement__table-wrap" data-testid="card-wrap">
      <table class="bvd-statement__table bvd-statement__table--txn bvd-txn-rows__table">
        <thead class="bvd-txn-rows__thead"><tr class="bvd-txn-rows__header-row">
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-chevron"></th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact" data-testid="card-h">Date</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact">Unit</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-flex">Driver</th>
          <th class="bvd-txn-rows__header-cell bvd-txn-rows__col-compact">Amt</th>
        </tr></thead><tbody>${cardRows}</tbody>
      </table>
    </div>
  </section>
  <section class="processed-statement-section processed-statement-section--charges" style="margin-top:2rem">
    <div class="bvd-express-rows bvd-statement__table-wrap" data-testid="express-wrap">
      <table class="bvd-express-rows__table bvd-statement__table bvd-statement__table--txn">
        <thead class="bvd-express-rows__thead"><tr class="bvd-express-rows__header-row">
          <th class="bvd-express-rows__header-cell bvd-express-rows__col-compact" data-testid="express-h">Date</th>
          <th class="bvd-express-rows__header-cell bvd-express-rows__col-compact">Unit</th>
          <th class="bvd-express-rows__header-cell bvd-express-rows__col-flex">Driver</th>
          <th class="bvd-express-rows__header-cell bvd-express-rows__col-compact">Total</th>
        </tr></thead><tbody>${expressRows}</tbody>
      </table>
    </div>
  </section>
</main>
</div></body></html>`;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 700 } });
await page.setContent(html, { waitUntil: "load" });

const metrics = await page.evaluate(() => {
  const main = document.querySelector(".trk-app-main");
  const cardWrap = document.querySelector('[data-testid="card-wrap"]');
  const expressWrap = document.querySelector('[data-testid="express-wrap"]');
  const cardH = document.querySelector('[data-testid="card-h"]');
  const style = (el) => (el ? getComputedStyle(el) : null);
  return {
    cardWrapOverflowY: style(cardWrap)?.overflowY,
    cardWrapMaxHeight: style(cardWrap)?.maxHeight,
    cardWrapClientHeight: cardWrap?.clientHeight,
    cardWrapScrollHeight: cardWrap?.scrollHeight,
    cardWrapHasVerticalScrollbar: cardWrap ? cardWrap.scrollHeight > cardWrap.clientHeight + 1 : null,
    expressWrapHasVerticalScrollbar: expressWrap
      ? expressWrap.scrollHeight > expressWrap.clientHeight + 1
      : null,
    mainScrollHeight: main?.scrollHeight,
    mainClientHeight: main?.clientHeight,
    headerHeight: cardH ? Math.round(cardH.getBoundingClientRect().height) : null,
  };
});

await page.evaluate(() => document.querySelector(".trk-app-main")?.scrollTo(0, 400));
await page.waitForTimeout(80);

const afterScroll = await page.evaluate(() => {
  const main = document.querySelector(".trk-app-main");
  const nav = document.querySelector("header");
  const cardH = document.querySelector('[data-testid="card-h"]');
  const expressH = document.querySelector('[data-testid="express-h"]');
  const navBottom = nav ? nav.getBoundingClientRect().bottom : 0;
  const cardTop = cardH ? cardH.getBoundingClientRect().top : null;
  const expressTop = expressH ? expressH.getBoundingClientRect().top : null;
  const doc = document.documentElement;
  return {
    mainScrollTop: main?.scrollTop,
    cardHeaderTop: cardTop !== null ? Math.round(cardTop) : null,
    expressHeaderTop: expressTop !== null ? Math.round(expressTop) : null,
    navBottom: Math.round(navBottom),
    cardStickyNearMainTop: cardTop !== null && Math.abs(cardTop - navBottom) <= 3,
    docScrollWidth: doc.scrollWidth,
    docClientWidth: doc.clientWidth,
  };
});

console.log(JSON.stringify({ metrics, afterScroll }, null, 2));
await browser.close();
