import { describe, expect, it } from "vitest";
import {
  expandDocFocusVariants,
  findBestDocLineIndex,
  docFocusForStopCity,
  docFocusForStopStreet,
  newDraftStop,
} from "./loadWorkspaceShared";

const SAMPLE = [
  "RATE CONFIRMATION",
  "Broker: Jaysm Logistics LLC",
  "Load #: 884422",
  "Linehaul Rate: $2,450.00",
  "PICKUP",
  "Shipper: Acme Warehouse",
  "123 Main St, Chicago, IL 60601",
  "Appt: 10/25/2025 08:00 FCFS",
  "DELIVERY",
  "Consignee: Big Box Retail",
  "500 Commerce Dr, Dallas, TX 75201",
  "Appt: 10/27/2025 14:00",
  "Commodity: Dry grocery",
  "Weight: 42,000 lbs",
  "Miles: 925",
].join("\n");

describe("expandDocFocusVariants", () => {
  it("includes currency formatting variants", () => {
    const v = expandDocFocusVariants("2450");
    expect(v.some((x) => x.includes("2,450"))).toBe(true);
  });

  it("includes ISO date slash variants", () => {
    const v = expandDocFocusVariants("2025-10-25");
    expect(v).toContain("10/25/2025");
  });
});

describe("findBestDocLineIndex", () => {
  const lines = SAMPLE.split(/\r?\n/);

  it("prefers linehaul amount over generic rate headers", () => {
    const idx = findBestDocLineIndex(lines, {
      primaryValue: "2450",
      hintTokens: ["rate", "linehaul"],
    });
    expect(lines[idx]).toContain("2,450");
  });

  it("finds broker load reference by value", () => {
    const idx = findBestDocLineIndex(lines, {
      primaryValue: "884422",
      hintTokens: ["load #"],
    });
    expect(lines[idx]).toContain("884422");
  });

  it("scopes pickup city without matching delivery city", () => {
    const stop = {
      stop_type: "PICKUP",
      city: "Chicago",
      street: null,
      state_or_province: null,
      postal_code: null,
      facility_name: null,
      country: null,
      reference_number: null,
      appointment_type: null,
      appointment_date: null,
      appointment_time_text: null,
      scheduled_at: null,
      notes: null,
      commodity_notes: null,
      sequence: 0,
      created_at: null,
      updated_at: null,
      _key: "t",
    };
    const idx = findBestDocLineIndex(lines, docFocusForStopCity(stop, 0));
    expect(lines[idx]).toContain("Chicago");
    expect(lines[idx]).not.toContain("Dallas");
  });

  it("street field matches street fragment not only city", () => {
    const stop = {
      stop_type: "PICKUP",
      city: "Chicago",
      street: "123 Main St",
      state_or_province: "IL",
      postal_code: "60601",
      facility_name: null,
      country: null,
      reference_number: null,
      appointment_type: null,
      appointment_date: null,
      appointment_time_text: null,
      scheduled_at: null,
      notes: null,
      commodity_notes: null,
      sequence: 0,
      created_at: null,
      updated_at: null,
      _key: "t",
    };
    const idx = findBestDocLineIndex(lines, docFocusForStopStreet(stop, 0));
    expect(lines[idx]).toContain("123 Main");
  });

  it("does not jump on empty primary value", () => {
    const stop = newDraftStop(0, "PICKUP");
    stop.city = "";
    expect(findBestDocLineIndex(lines, docFocusForStopCity(stop, 0))).toBe(-1);
  });

  it("finds commodity and weight by field value", () => {
    expect(
      lines[
        findBestDocLineIndex(lines, {
          primaryValue: "Dry grocery",
          hintTokens: ["commodity"],
        })
      ],
    ).toContain("Dry grocery");
    expect(
      lines[
        findBestDocLineIndex(lines, {
          primaryValue: "42000",
          hintTokens: ["weight"],
        })
      ],
    ).toContain("42,000");
  });

  it("returns -1 for empty document", () => {
    expect(findBestDocLineIndex([], { primaryValue: "x" })).toBe(-1);
  });
});
