/** Two-line header labels for processed charge tables (readability over compression). */
const TWO_LINE_HEADERS: Record<string, [string, string]> = {
  "Date / Time": ["Date /", "Time"],
  "Source driver": ["Source", "driver"],
  "Retail price": ["Retail", "price"],
  "Billed price": ["Billed", "price"],
  "Final amount": ["Final", "amount"],
  "Provider ref": ["Provider", "ref"],
  "Provider reason": ["Provider", "reason"],
};

export function processedChargeHeaderLineCount(label: string): number {
  return TWO_LINE_HEADERS[label] ? 2 : 1;
}

export function ProcessedChargeHeaderLabel({ label }: { label: string }) {
  const lines = TWO_LINE_HEADERS[label];
  if (!lines) {
    return <>{label}</>;
  }
  return (
    <span className="bvd-processed-header-label" data-processed-header-wrap="true">
      <span className="bvd-processed-header-label__line">{lines[0]}</span>
      <span className="bvd-processed-header-label__line">{lines[1]}</span>
    </span>
  );
}
