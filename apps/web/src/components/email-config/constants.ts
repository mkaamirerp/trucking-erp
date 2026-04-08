export const STATUS_BADGE: Record<string, string> = {
  NOT_CONNECTED: "Not connected",
  CONNECTING: "Connecting",
  CONNECTED: "Connected",
  ERROR: "Error",
  DISABLED: "Disabled",
  NOT_CONFIGURED: "Not configured",
  CONFIGURED: "Configured",
  TESTING: "Testing",
};

export const STATUS_COLORS: Record<string, string> = {
  NOT_CONNECTED: "bg-[#1e293b] text-[#94a3b8]",
  CONNECTING: "bg-amber-900/40 text-amber-200",
  CONNECTED: "bg-emerald-900/40 text-emerald-300",
  ERROR: "bg-red-900/40 text-red-400",
  DISABLED: "bg-[#1e293b] text-[#64748b]",
  NOT_CONFIGURED: "bg-[#1e293b] text-[#94a3b8]",
  CONFIGURED: "bg-[#1e293b] text-[#94a3b8]",
  TESTING: "bg-amber-900/40 text-amber-200",
};

export function formatLastTested(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return "—";
  }
}
