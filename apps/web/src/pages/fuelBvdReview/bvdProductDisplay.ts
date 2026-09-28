/** BVD product codes → operator-friendly labels (presentation only). */
export const BVD_KNOWN_PRODUCT_LABELS: Record<string, string> = {
  TA: "Fuel",
  DF: "DEF",
  S: "Scale",
  C: "Cash",
  AD: "Additive",
  O: "Oil",
  L: "Lubricant",
  TF: "Trailer",
};

export function bvdProductDisplayLabel(prodCode: string): string {
  const raw = prodCode.trim();
  if (!raw) return "—";
  const mapped = BVD_KNOWN_PRODUCT_LABELS[raw.toUpperCase()];
  return mapped ?? raw;
}
