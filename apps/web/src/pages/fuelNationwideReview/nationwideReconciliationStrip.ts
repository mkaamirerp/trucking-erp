import type { FuelNationwideSourceReconciliation } from "../../api";

export type NationwideValidationMetric = {
  label: string;
  value: string;
  status: "pass" | "fail" | "na";
  detail?: string;
};

export function nationwideReconciliationStrip(
  report: FuelNationwideSourceReconciliation | null,
): { metrics: NationwideValidationMetric[]; allPass: boolean } {
  if (!report) {
    return { metrics: [], allPass: false };
  }
  const metrics: NationwideValidationMetric[] = [
    {
      label: "Provider precision gates",
      value: report.passed ? "Pass" : "Fail",
      status: report.passed ? "pass" : "fail",
      detail: "Backend Nationwide reconciliation (USD extension vs control, CAD tax stack)",
    },
    {
      label: "USD printed row totals",
      value: report.usd_row_total_sum ?? "—",
      status: "na",
      detail: "Sum of source transaction Total column (may differ from provider billing control)",
    },
    {
      label: "USD provider control",
      value: report.usd_provider_control ?? "—",
      status: report.passed ? "pass" : "na",
      detail: report.usd_precision_extension
        ? `Extension ${report.usd_precision_extension} → control; Δ ${report.usd_precision_difference ?? "—"}`
        : undefined,
    },
    {
      label: "CAD ex-tax / GST / subtotal",
      value: [report.cad_ex_tax_control, report.cad_gst, report.cad_subtotal].filter(Boolean).join(" · ") || "—",
      status: report.passed ? "pass" : "fail",
    },
  ];
  return { metrics, allPass: report.passed };
}
