import type { FuelBvdRow } from "../../api";
import { operationalCell } from "./bvdParsedDisplay";

function displayCell(row: FuelBvdRow, field: string): string {
  return operationalCell(row, field);
}
import { parseBvdMoneyString } from "./bvdParsedValidation";

const MONEY_EPS = 0.005;

export type BvdTxnTaxLine = { key: string; label: string; amount: string };

function nearlyEqual(a: number, b: number): boolean {
  return Math.abs(a - b) <= MONEY_EPS;
}

export function isNonZeroMoney(raw: string): boolean {
  const n = parseBvdMoneyString(raw);
  if (n === null) return false;
  return Math.abs(n) > MONEY_EPS;
}

function normalizePlacePart(s: string): string {
  return s.trim().replace(/\s+/g, " ");
}

function titleCaseWords(s: string): string {
  const t = normalizePlacePart(s);
  if (!t) return "";
  return t
    .toLowerCase()
    .replace(/\b([a-z])/g, (m) => m.toUpperCase());
}

/** Main row location — city + prov when possible; dedupe identical site name & city. */
export function formatBvdTxnLocationShort(row: FuelBvdRow): string {
  const siteName = normalizePlacePart(displayCell(row, "site_name"));
  const siteCity = normalizePlacePart(displayCell(row, "site_city"));
  const prov = normalizePlacePart(displayCell(row, "prov_st"));

  const city =
    siteCity ||
    (siteName && siteCity && siteName.toLowerCase() === siteCity.toLowerCase() ? siteName : siteCity) ||
    siteName;

  const cityLabel = titleCaseWords(city);
  if (cityLabel && prov) return `${cityLabel}, ${prov}`;
  if (cityLabel) return cityLabel;
  if (siteName && prov) return `${titleCaseWords(siteName)}, ${prov}`;
  return siteName ? titleCaseWords(siteName) : "—";
}

export type BvdTxnSiteDetail = {
  primaryLine: string;
  secondaryLine: string;
  siteNumberLine: string;
};

/** Expanded site block — name, city/prov, optional site #. */
export function formatBvdTxnSiteDetail(row: FuelBvdRow): BvdTxnSiteDetail {
  const siteName = normalizePlacePart(displayCell(row, "site_name"));
  const siteCity = normalizePlacePart(displayCell(row, "site_city"));
  const prov = normalizePlacePart(displayCell(row, "prov_st"));
  const siteNumber = displayCell(row, "site_number");

  const nameLine =
    siteName && siteCity && siteName.toLowerCase() === siteCity.toLowerCase()
      ? titleCaseWords(siteCity)
      : siteName ? titleCaseWords(siteName) : "";

  let secondaryLine = "";
  if (siteCity && siteName && siteName.toLowerCase() !== siteCity.toLowerCase()) {
    secondaryLine = prov ? `${titleCaseWords(siteCity)}, ${prov}` : titleCaseWords(siteCity);
  } else if (siteCity && prov) {
    secondaryLine = `${titleCaseWords(siteCity)}, ${prov}`;
  } else if (prov) {
    secondaryLine = prov;
  }

  const siteNumberLine = siteNumber ? `Site # ${siteNumber}` : "";

  return {
    primaryLine: nameLine || secondaryLine || "—",
    secondaryLine: nameLine && secondaryLine ? secondaryLine : "",
    siteNumberLine,
  };
}

/** Jul 23 02:17 from BVD datetime strings. */
export function formatBvdTransactionDateTime(raw: string): string {
  const t = raw.trim();
  if (!t) return "—";
  const isoLike = t.includes("T") ? t : t.replace(" ", "T");
  const d = new Date(isoLike);
  if (Number.isNaN(d.getTime())) {
    const m = t.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})/);
    if (m) {
      const month = new Date(`${m[1]}-${m[2]}-${m[3]}T12:00:00`).toLocaleString("en-US", { month: "short" });
      return `${month} ${m[3]} ${m[4]}:${m[5]}`;
    }
    return t;
  }
  const month = d.toLocaleString("en-US", { month: "short" });
  const day = d.getDate();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  return `${month} ${day} ${hh}:${mm}`;
}

const TAX_FIELDS: { field: string; label: string }[] = [
  { field: "hst", label: "HST" },
  { field: "gst", label: "GST" },
  { field: "pst", label: "PST" },
  { field: "qst", label: "QST" },
];

export function bvdTxnNonZeroTaxLines(row: FuelBvdRow): BvdTxnTaxLine[] {
  const lines: BvdTxnTaxLine[] = [];
  for (const { field, label } of TAX_FIELDS) {
    const raw = displayCell(row, field);
    if (isNonZeroMoney(raw)) {
      lines.push({ key: field, label, amount: raw });
    }
  }
  return lines;
}

export function bvdTxnDiscountAmount(row: FuelBvdRow): string | null {
  const raw = displayCell(row, "disc_amt");
  return isNonZeroMoney(raw) ? raw : null;
}

export type BvdTxnPriceDisplay = {
  showRetail: boolean;
  retail: string;
  billed: string;
};

export function bvdTxnPriceDisplay(row: FuelBvdRow): BvdTxnPriceDisplay {
  const retail = displayCell(row, "retail");
  const billed = displayCell(row, "billed");
  const retailN = parseBvdMoneyString(retail);
  const billedN = parseBvdMoneyString(billed);
  const showRetail =
    retail.length > 0 &&
    billed.length > 0 &&
    retailN !== null &&
    billedN !== null &&
    !nearlyEqual(retailN, billedN);
  return { showRetail, retail, billed };
}
