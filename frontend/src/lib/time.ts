/**
 * The backend stores and expects **naive IST** timestamps (no timezone offset).
 * These helpers keep the frontend consistent with that regardless of the
 * viewer's local timezone.
 *
 * Note on display: `new Date("2026-08-18T14:30:00")` is parsed as *local* time,
 * and formatting it back with a local formatter shows the same wall-clock — so
 * plain display of the stored strings already shows the correct IST numbers.
 * The two things that genuinely break off-IST are (1) request windows built from
 * the local clock and (2) any comparison against a real "now" instant. These
 * helpers fix both.
 */

/** Format an instant as an IST wall-clock string "yyyy-MM-ddTHH:mm:ss" (no offset). */
export function formatISTNaive(d: Date): string {
  const p = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    hour12: false,
  })
    .formatToParts(d)
    .reduce((acc, part) => { acc[part.type] = part.value; return acc; }, {} as Record<string, string>);
  // Intl may emit "24" for midnight in some engines; normalize.
  const hour = p.hour === "24" ? "00" : p.hour;
  return `${p.year}-${p.month}-${p.day}T${hour}:${p.minute}:${p.second}`;
}

/** A request window [start, end] as IST-naive strings, hoursBack before / hoursFwd after now. */
export function istWindow(hoursBack: number, hoursFwd: number): { start: string; end: string } {
  const now = Date.now();
  return {
    start: formatISTNaive(new Date(now - hoursBack * 3600_000)),
    end: formatISTNaive(new Date(now + hoursFwd * 3600_000)),
  };
}

/**
 * "Now" expressed on the same basis as chart data: the stored IST wall-clock
 * strings are parsed via `new Date(str)` as local time, so we reinterpret the
 * IST wall-clock of the current instant the same way. This makes a "now" marker
 * line up with the data on any host.
 */
export function istNowMs(): number {
  return new Date(formatISTNaive(new Date())).getTime();
}
