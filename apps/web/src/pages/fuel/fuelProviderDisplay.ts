/** Human-readable provider labels for Fuel activity and processed workspace headers. */
export function fuelProviderTableLabel(providerCode: string): string {
  const code = providerCode.trim().toUpperCase();
  if (code === "NATIONWIDE") return "Nationwide";
  if (code === "MANUAL_ENTRY") return "Manual Entry";
  return providerCode;
}
