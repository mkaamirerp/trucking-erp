import type { FuelProcessedOperationalTransaction } from "../../api";
import { resolveManualProcessedSourceDetailFields } from "./manualProcessedSourceDetailsFields";

type Props = {
  operational: FuelProcessedOperationalTransaction | null | undefined;
  invoiceNumber?: string | null;
  providerRaw?: Record<string, unknown> | null;
};

function line(label: string, value: string | null) {
  if (!value) return null;
  return (
    <div className="grid grid-cols-[minmax(7rem,auto)_1fr] gap-x-2 gap-y-0.5 text-xs">
      <span className="text-[var(--trk-text-muted)]">{label}</span>
      <span className="text-[var(--trk-text)]">{value}</span>
    </div>
  );
}

export default function ManualProcessedSourceDetails({
  operational,
  invoiceNumber,
  providerRaw,
}: Props) {
  const fields = resolveManualProcessedSourceDetailFields(operational, providerRaw, invoiceNumber);
  const rows = [
    line("Entry method", fields.entryMethod),
    line("Vendor", fields.vendor),
    line("Store #", fields.storeNumber),
    line("Pump", fields.pump),
    line("Receipt / ticket", fields.receiptTicket),
    line("Authorization", fields.authorization),
    line("Card / account", fields.cardOrAccount),
    line("Invoice / ref", fields.invoiceReference),
    line("Trailer", fields.trailer),
    line("Company", fields.companyName),
    line("Vehicle ID (source)", fields.vehicleIdEvidence),
    line("Tax note", fields.taxNote),
    line("Price candidates", fields.priceCandidates),
    line("Rejected prices", fields.rejectedPrices),
  ].filter(Boolean);

  if (rows.length === 0) return null;

  return (
    <section
      className="mb-2 rounded-md border border-[var(--trk-border)] bg-[var(--trk-surface)] px-2 py-1.5"
      data-testid="manual-processed-source-details"
      aria-label="Manual entry source details"
    >
      <h3 className="mb-1 text-[10px] font-bold uppercase tracking-wide text-[var(--trk-text-muted)]">
        Source details
      </h3>
      <div className="space-y-0.5">{rows}</div>
    </section>
  );
}
