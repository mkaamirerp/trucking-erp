/** BVD source labels for review UI (not database column names). */

export const BVD_FIELD_LABELS: Record<string, string> = {
  invoice_number: "Invoice Number",
  invoice_date: "Invoice Date",
  start_date: "Start Date",
  end_date: "End Date",
  due_date: "Due Date",
  client_name: "Client",
  client_address: "Address",
  client_phone: "Phone",
  client_email: "Email",
  card_number: "Card #",
  hst_number: "HST#",
  qst_number: "QST#",
  auth_code: "Auth Code",
  driver_name: "Driver Name",
  unit_number: "Unit #",
  transaction_date: "Date",
  site_number: "Site #",
  site_name: "Site Name",
  site_city: "Site City",
  prov_st: "Prov/ST",
  prod: "Prod",
  qty: "QTY",
  retail: "Retail",
  billed: "Billed",
  pre_tax_amt: "Pre Tax AMT",
  hst: "HST",
  gst: "GST",
  pst: "PST",
  qst: "QST",
  disc_rate: "Disc Rate",
  disc_amt: "Disc AMT",
  final_amt: "Final AMT",
  cur: "CUR",
  row_label: "Label",
  product: "Product",
  final_amount: "FINAL AMOUNT",
  legend_code: "Code",
  legend_product_name: "Product Name",
};

export const BVD_TRANSACTION_COLUMNS: { field: string; label: string }[] = [
  "auth_code",
  "driver_name",
  "unit_number",
  "transaction_date",
  "site_number",
  "site_name",
  "site_city",
  "prov_st",
  "prod",
  "qty",
  "retail",
  "billed",
  "pre_tax_amt",
  "hst",
  "gst",
  "pst",
  "qst",
  "disc_rate",
  "disc_amt",
  "final_amt",
  "cur",
].map((field) => ({ field, label: BVD_FIELD_LABELS[field] ?? field }));

export const BVD_HEADER_FIELDS: string[] = [
  "invoice_number",
  "invoice_date",
  "start_date",
  "end_date",
  "due_date",
  "client_name",
  "client_address",
  "client_phone",
  "client_email",
  "card_number",
  "hst_number",
  "qst_number",
];

export const BVD_REVIEW_TABS = [
  { id: "HEADER" as const, label: "Header" },
  { id: "TRANSACTIONS" as const, label: "Transactions" },
  { id: "CONTROLS" as const, label: "Controls" },
  { id: "GRAND_TOTAL" as const, label: "Grand Total" },
  { id: "LEGEND" as const, label: "Legend" },
];

export type BvdReviewTabId = (typeof BVD_REVIEW_TABS)[number]["id"];

export const BVD_GRAND_TOTAL_FIELDS: string[] = [
  "product",
  "qty",
  "pre_tax_amt",
  "hst",
  "gst",
  "pst",
  "qst",
  "disc_rate",
  "disc_amt",
  "final_amount",
  "cur",
];

export const BVD_SUBTOTAL_FIELDS: string[] = [
  "row_label",
  "qty",
  "pre_tax_amt",
  "hst",
  "gst",
  "pst",
  "qst",
  "disc_amt",
  "final_amt",
];

export const BVD_SECTION_TITLE: Record<string, string> = {
  HEADER: "HEADER",
  TRANSACTION: "TRANSACTIONS",
  TRANSACTION_SUBTOTAL: "TRANSACTION SUBTOTALS",
  PAGE1_SUMMARY: "PAGE SUMMARY",
  GRAND_TOTAL: "GRAND TOTAL",
  LEGEND: "LEGEND",
};

export const BVD_SECTION_ORDER = [
  "HEADER",
  "TRANSACTION",
  "TRANSACTION_SUBTOTAL",
  "PAGE1_SUMMARY",
  "GRAND_TOTAL",
  "LEGEND",
] as const;

export function reviewStatusLabel(status: string | null | undefined): string {
  switch (status) {
    case "SOURCE_REVIEWED":
      return "Completed";
    case "IN_REVIEW":
      return "In review";
    case "PENDING":
    default:
      return "Pending";
  }
}
