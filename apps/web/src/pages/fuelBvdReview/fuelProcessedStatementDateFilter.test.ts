import { describe, expect, it } from "vitest";
import {
  buildMonthRelativeWeeks,
  daysInCalendarMonth,
  monthRelativeWeekBounds,
  parseBvdStatementTransactionDate,
  transactionDateInPeriod,
} from "./fuelProcessedStatementDateFilter";

describe("fuelProcessedStatementDateFilter", () => {
  it("Week 1–4 use fixed day ranges", () => {
    expect(monthRelativeWeekBounds(2026, 7, 1)).toEqual({ fromDay: 1, toDay: 7 });
    expect(monthRelativeWeekBounds(2026, 7, 2)).toEqual({ fromDay: 8, toDay: 14 });
    expect(monthRelativeWeekBounds(2026, 7, 3)).toEqual({ fromDay: 15, toDay: 21 });
    expect(monthRelativeWeekBounds(2026, 7, 4)).toEqual({ fromDay: 22, toDay: 28 });
  });

  it("Week 5 runs through month end", () => {
    expect(monthRelativeWeekBounds(2026, 7, 5)).toEqual({ fromDay: 29, toDay: 31 });
    expect(monthRelativeWeekBounds(2028, 2, 5)).toEqual({ fromDay: 29, toDay: 29 });
  });

  it("February 2028 Week 5 is Feb 29 only", () => {
    expect(daysInCalendarMonth(2028, 2)).toBe(29);
    const weeks = buildMonthRelativeWeeks(2028, 2);
    const w5 = weeks.find((w) => w.week === 5);
    expect(w5?.fromDay).toBe(29);
    expect(w5?.toDay).toBe(29);
    expect(w5?.label).toContain("29");
  });

  it("non-leap February has four weeks ending on 28", () => {
    expect(daysInCalendarMonth(2026, 2)).toBe(28);
    const weeks = buildMonthRelativeWeeks(2026, 2);
    expect(weeks.some((w) => w.week === 5)).toBe(false);
    expect(weeks[weeks.length - 1].toDay).toBe(28);
  });

  it("custom date range filters inclusively", () => {
    const d = parseBvdStatementTransactionDate("2025-12-12 14:00:00")!;
    expect(
      transactionDateInPeriod(d, { kind: "custom", from: "2025-12-12", to: "2025-12-14" }),
    ).toBe(true);
    expect(
      transactionDateInPeriod(d, { kind: "custom", from: "2025-12-13", to: "2025-12-14" }),
    ).toBe(false);
  });

  it("All transactions passes any parsed date", () => {
    const d = parseBvdStatementTransactionDate("2026-07-23 02:17:56")!;
    expect(transactionDateInPeriod(d, { kind: "all" })).toBe(true);
  });

  it("week filter uses month-relative bounds", () => {
    const d = parseBvdStatementTransactionDate("2026-07-23 02:17:56")!;
    expect(transactionDateInPeriod(d, { kind: "week", year: 2026, month: 7, week: 4 })).toBe(true);
    expect(transactionDateInPeriod(d, { kind: "week", year: 2026, month: 7, week: 3 })).toBe(false);
  });
});
