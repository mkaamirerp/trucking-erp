/**
 * Parse pasted bulk broker rows for create API.
 * Supported:
 * - Rank,Company Name,MC Number,Headquarters CSV (quoted HQ fields); header row is auto-skipped
 * - Name<TAB>MC or Name, MC (legacy) or name-only lines
 * Skips empty lines and lines starting with #.
 */

export type ParsedBrokerRow = {
  name: string;
  mc_number: string | null;
  notes?: string | null;
};

/** Split one CSV line; honors double-quoted fields (commas inside quotes). */
function parseCsvLine(line: string): string[] {
  const fields: string[] = [];
  let cur = "";
  let i = 0;
  let inQuotes = false;
  while (i < line.length) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"') {
        if (line[i + 1] === '"') {
          cur += '"';
          i += 2;
          continue;
        }
        inQuotes = false;
        i++;
        continue;
      }
      cur += c;
      i++;
      continue;
    }
    if (c === '"') {
      inQuotes = true;
      i++;
      continue;
    }
    if (c === ",") {
      fields.push(cur.trim());
      cur = "";
      i++;
      continue;
    }
    cur += c;
    i++;
  }
  fields.push(cur.trim());
  return fields;
}

function stripQuotes(s: string): string {
  const t = s.trim();
  if (t.length >= 2 && t.startsWith('"') && t.endsWith('"')) {
    return t.slice(1, -1).replace(/""/g, '"').trim();
  }
  return t;
}

function looksLikeRankMcCsvHeader(fields: string[]): boolean {
  const a = (fields[0] ?? "").toLowerCase();
  const b = (fields[1] ?? "").toLowerCase();
  return a === "rank" && (b.includes("company") || b.includes("name"));
}

function looksLikeRankMcDataRow(fields: string[]): boolean {
  if (fields.length < 4) return false;
  return /^\d+$/.test((fields[0] ?? "").trim());
}

export function parseBrokerBulkInput(raw: string): ParsedBrokerRow[] {
  const out: ParsedBrokerRow[] = [];

  for (const line of raw.split(/\r?\n/)) {
    const s = line.trim();
    if (!s || s.startsWith("#")) continue;

    if (!s.includes("\t")) {
      const csvFields = parseCsvLine(s).map(stripQuotes);
      if (looksLikeRankMcCsvHeader(csvFields)) {
        continue;
      }
      if (looksLikeRankMcDataRow(csvFields)) {
        const name = (csvFields[1] ?? "").trim();
        const mcRaw = (csvFields[2] ?? "").trim();
        const hq = (csvFields[3] ?? "").trim();
        if (!name) continue;
        out.push({
          name,
          mc_number: mcRaw || null,
          notes: hq ? `HQ: ${hq}` : null,
        });
        continue;
      }
    }

    if (s.includes("\t")) {
      const parts = s.split("\t").map((p) => p.trim().replace(/^"|"$/g, ""));
      const name = (parts[0] ?? "").trim();
      const mc = parts[1]?.trim() || null;
      if (!name) continue;
      out.push({ name, mc_number: mc });
      continue;
    }

    let name: string;
    let mc: string | null = null;
    const idx = s.indexOf(",");
    if (idx >= 0) {
      name = s.slice(0, idx).trim().replace(/^"|"$/g, "");
      mc = s.slice(idx + 1).trim().replace(/^"|"$/g, "") || null;
    } else {
      name = s.replace(/^"|"$/g, "");
    }
    if (!name) continue;
    out.push({ name, mc_number: mc });
  }

  return out;
}
