export const NATIONWIDE_TRANSACTION_COLUMNS: { field: keyof import("../../api").FuelNationwideRow; label: string }[] =
  [
    { field: "card_number", label: "Card Number" },
    { field: "unit_number", label: "Unit #" },
    { field: "transaction_date", label: "Date" },
    { field: "city", label: "City" },
    { field: "prov_st", label: "Pr/St" },
    { field: "product", label: "Product" },
    { field: "volume", label: "Volume" },
    { field: "ex_gst_per_unit", label: "Ex-GST ($/U)" },
    { field: "total", label: "Total" },
    { field: "network", label: "Network" },
    { field: "currency", label: "Currency" },
    { field: "usa_discount", label: "USA Discount" },
    { field: "missed_disc", label: "Missed Disc" },
    { field: "oon_fees", label: "OON Fees" },
  ];

export const NATIONWIDE_FIELD_LABELS: Record<string, string> = {
  account_code: "Account Code",
  invoice_number: "Invoice Number",
  invoice_start_date: "Start",
  invoice_end_date: "End",
  due_date: "Due",
  customer_name: "Customer",
  ...Object.fromEntries(NATIONWIDE_TRANSACTION_COLUMNS.map((c) => [c.field, c.label])),
  control_line_raw: "Control",
  control_type: "Control type",
  declared_amount: "Declared amount",
  gst: "GST",
  pst: "PST",
};
