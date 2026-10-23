// Dates as the pages show them.

// "19 Oct 2026, 09:30 UTC", or without the year where it is plain.
export function stamp(iso: string, year = false): string {
  const text = new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    ...(year ? { year: "numeric" } : {}),
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${text} UTC`;
}
