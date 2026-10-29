import type { Load, LoadStop } from "@/api";

function normStopType(t: string | undefined): string {
  return (t || "").toUpperCase();
}

/** Stops in route order (by sequence). */
export function sortedStops(stops: LoadStop[] | null | undefined): LoadStop[] {
  if (!stops?.length) return [];
  return [...stops].sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
}

export function firstPickupStop(stops: LoadStop[] | null | undefined): LoadStop | undefined {
  return sortedStops(stops).find((s) => normStopType(s.stop_type) === "PICKUP");
}

export function lastDropStop(stops: LoadStop[] | null | undefined): LoadStop | undefined {
  const list = sortedStops(stops);
  for (let i = list.length - 1; i >= 0; i--) {
    const n = normStopType(list[i].stop_type);
    if (n === "DROP" || n === "DELIVERY") return list[i];
  }
  return undefined;
}

/** City and state only. A facility name is not a city. */
export function formatStopCityState(stop: LoadStop | undefined): string {
  if (!stop) return "—";
  const city = stop.city?.trim();
  const st = stop.state_or_province?.trim();
  if (city && st) return `${city}, ${st}`;
  if (city) return city;
  if (st) return st;
  return "—";
}

export function firstPickupAppointmentDate(stops: LoadStop[] | null | undefined): string | null | undefined {
  return firstPickupStop(stops)?.appointment_date ?? null;
}

/** Dispatch queue: pickup appointment date and time text when present. */
export function formatPickupAppointmentLabel(stops: LoadStop[] | null | undefined): string {
  const pu = firstPickupStop(stops);
  if (!pu) return "—";
  const d = pu.appointment_date?.trim();
  const t = pu.appointment_time_text?.trim();
  if (d && t) return `${d} ${t}`;
  if (d) return d;
  if (t) return t;
  return "—";
}

/** Load list / dispatch: origin → destination from stops. */
export function formatRouteFromStops(stops: LoadStop[] | null | undefined): string {
  const from = formatStopCityState(firstPickupStop(stops));
  const to = formatStopCityState(lastDropStop(stops));
  if (from === "—" && to === "—") return "—";
  return `${from} → ${to}`;
}
