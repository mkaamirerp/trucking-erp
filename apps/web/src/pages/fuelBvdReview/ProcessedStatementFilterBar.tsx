import type { DatePeriodSelection, StatementMonthGroup } from "./fuelProcessedStatementDateFilter";

type Props = {
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  period: DatePeriodSelection;
  onPeriodChange: (period: DatePeriodSelection) => void;
  monthGroups: StatementMonthGroup[];
  filteredCount: number;
  totalCount: number;
  onClear: () => void;
};

export default function ProcessedStatementFilterBar({
  searchQuery,
  onSearchQueryChange,
  period,
  onPeriodChange,
  monthGroups,
  filteredCount,
  totalCount,
  onClear,
}: Props) {
  const periodValue =
    period.kind === "all"
      ? "all"
      : period.kind === "custom"
        ? "custom"
        : `week:${period.year}-${period.month}-${period.week}`;

  return (
    <div className="bvd-statement-filters" data-testid="bvd-statement-filters">
      <div className="bvd-statement-filters__row">
        <label className="bvd-statement-filters__label" htmlFor="bvd-statement-search">
          Search this statement
        </label>
        <input
          id="bvd-statement-search"
          type="search"
          className="bvd-statement-filters__search"
          data-testid="bvd-statement-search-input"
          placeholder="Unit, driver, card, auth, product, amount, date…"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
        />
      </div>
      <div className="bvd-statement-filters__row">
        <label className="bvd-statement-filters__label" htmlFor="bvd-statement-period">
          Date period
        </label>
        <select
          id="bvd-statement-period"
          className="bvd-statement-filters__select"
          data-testid="bvd-statement-period-select"
          value={periodValue}
          onChange={(e) => {
            const v = e.target.value;
            if (v === "all") {
              onPeriodChange({ kind: "all" });
              return;
            }
            if (v === "custom") {
              onPeriodChange({ kind: "custom", from: "", to: "" });
              return;
            }
            const m = v.match(/^week:(\d+)-(\d+)-(\d+)$/);
            if (m) {
              onPeriodChange({
                kind: "week",
                year: Number(m[1]),
                month: Number(m[2]),
                week: Number(m[3]) as 1 | 2 | 3 | 4 | 5,
              });
            }
          }}
        >
          <option value="all">All transactions</option>
          {monthGroups.map((g) => (
            <optgroup key={`${g.year}-${g.month}`} label={g.label}>
              {g.weeks.map((w) => (
                <option key={`${w.year}-${w.month}-${w.week}`} value={`week:${w.year}-${w.month}-${w.week}`}>
                  {w.label}
                </option>
              ))}
            </optgroup>
          ))}
          <option value="custom">Custom dates</option>
        </select>
      </div>
      {period.kind === "custom" ? (
        <div className="bvd-statement-filters__row bvd-statement-filters__custom-dates">
          <label className="bvd-statement-filters__label" htmlFor="bvd-statement-from">From</label>
          <input
            id="bvd-statement-from"
            type="date"
            className="bvd-statement-filters__date"
            data-testid="bvd-statement-date-from"
            value={period.from}
            onChange={(e) => onPeriodChange({ kind: "custom", from: e.target.value, to: period.to })}
          />
          <label className="bvd-statement-filters__label" htmlFor="bvd-statement-to">To</label>
          <input
            id="bvd-statement-to"
            type="date"
            className="bvd-statement-filters__date"
            data-testid="bvd-statement-date-to"
            value={period.to}
            onChange={(e) => onPeriodChange({ kind: "custom", from: period.from, to: e.target.value })}
          />
        </div>
      ) : null}
      <div className="bvd-statement-filters__meta">
        <span data-testid="bvd-statement-result-count">
          {filteredCount === totalCount
            ? `${totalCount} transaction${totalCount === 1 ? "" : "s"}`
            : `${filteredCount} of ${totalCount} transactions`}
        </span>
        {searchQuery.trim() || period.kind !== "all" ? (
          <button
            type="button"
            className="bvd-statement-filters__clear"
            data-testid="bvd-statement-clear-filters"
            onClick={onClear}
          >
            Clear filters
          </button>
        ) : null}
      </div>
    </div>
  );
}
