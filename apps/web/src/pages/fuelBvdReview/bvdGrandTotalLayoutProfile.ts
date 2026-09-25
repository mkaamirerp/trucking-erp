/**
 * Fallback Grand Total column geometry when rendered PDF header text is insufficient.
 * Coordinates are relative column indices from PRODUCT (0-based), not pixels.
 * Applied only after primary header-band detection fails (see bvdFieldSlots.ts).
 */
export const BVD_GRAND_TOTAL_PROFILE_COLUMN_ORDER: readonly string[] = [
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
] as const;

/** Default relative width units per column when building bands from product anchor X. */
export const BVD_GRAND_TOTAL_PROFILE_COLUMN_WIDTH = 72;
