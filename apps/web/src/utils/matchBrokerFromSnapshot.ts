import type { BrokerContact } from "@/api";

function normalizeLabel(s: string): string {
  return s
    .toLowerCase()
    .replace(/[.,/#–—\-]+/g, " ")
    .replace(/[^\w\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function digitsOnly(s: string): string {
  return s.replace(/\D/g, "");
}

/** Match parsed contact hints to a broker contact row (same broker only). */
export function matchBrokerContactFromParsed(
  contacts: BrokerContact[],
  opts: { name?: string | null; email?: string | null; phone?: string | null },
): BrokerContact | null {
  const email = opts.email?.trim().toLowerCase();
  const phoneD = opts.phone ? digitsOnly(opts.phone) : "";
  const nameRaw = opts.name?.trim();
  const nameN = nameRaw ? normalizeLabel(nameRaw) : "";

  for (const c of contacts) {
    if (email && c.email?.trim().toLowerCase() === email) return c;
  }
  if (phoneD.length >= 10) {
    const tail = phoneD.slice(-10);
    for (const c of contacts) {
      const p = c.phone ? digitsOnly(c.phone) : "";
      if (p.length >= 10 && p.slice(-10) === tail) return c;
    }
  }
  if (nameN.length >= 3) {
    for (const c of contacts) {
      const cn = normalizeLabel(c.name || "");
      if (!cn) continue;
      if (cn === nameN || cn.includes(nameN) || nameN.includes(cn)) return c;
    }
  }
  return null;
}
