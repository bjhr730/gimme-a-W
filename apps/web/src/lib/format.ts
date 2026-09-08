export type SportKey = "soccer" | "nfl" | "cfb";

export const SPORTS: Record<
  SportKey,
  { label: string; short: string; sportId: "soccer" | "american_football"; competition?: string }
> = {
  soccer: { label: "Soccer", short: "Soccer", sportId: "soccer" },
  nfl: { label: "NFL", short: "NFL", sportId: "american_football", competition: "nfl" },
  cfb: {
    label: "College Football",
    short: "CFB",
    sportId: "american_football",
    competition: "college-football",
  },
};

export function sportKeyForCompetition(slug: string, sportId: string): SportKey {
  if (slug === "nfl") return "nfl";
  if (slug === "college-football") return "cfb";
  return sportId === "soccer" ? "soccer" : "nfl";
}

/** The app's "sports day" follows US Eastern time; see queries.ts. */
export const SPORTS_TZ = "America/New_York";

/** YYYY-MM-DD in UTC (for date arithmetic on plain calendar days). */
export function isoDate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Today's calendar date in the sports time zone. en-CA formats as YYYY-MM-DD. */
export function todayIso(): string {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: SPORTS_TZ,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return isoDate(d);
}

export function parseDateParam(value: string | string[] | undefined): string {
  const text = Array.isArray(value) ? value[0] : value;
  if (text && /^\d{4}-\d{2}-\d{2}$/.test(text) && !Number.isNaN(Date.parse(`${text}T00:00:00Z`))) {
    return text;
  }
  return todayIso();
}

export function weekdayLabel(iso: string, today: string): { top: string; bottom: string } {
  const d = new Date(`${iso}T00:00:00Z`);
  const weekday = d.toLocaleDateString("en-US", { weekday: "short", timeZone: "UTC" });
  const day = d.toLocaleDateString("en-US", { day: "numeric", timeZone: "UTC" });
  if (iso === today) return { top: "Today", bottom: day };
  return { top: weekday, bottom: day };
}

export function longDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function statNumber(value: unknown): string {
  if (value === null || value === undefined || value === "") return "–";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(1);
  return String(value);
}

/** Decimal odds to the American format most US readers expect. */
export function americanOdds(decimal: number | null | undefined): string {
  if (!decimal || decimal <= 1) return "–";
  const american = decimal >= 2 ? (decimal - 1) * 100 : -100 / (decimal - 1);
  const rounded = Math.round(american);
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

export function signed(n: number | null | undefined): string {
  if (n === null || n === undefined) return "–";
  if (n === 0) return "PK";
  return n > 0 ? `+${n}` : String(n);
}

/** Human labels for the stat keys ESPN uses. */
export const STAT_LABELS: Record<string, string> = {
  possessionPct: "Possession %",
  totalShots: "Shots",
  shotsOnTarget: "Shots on target",
  wonCorners: "Corners",
  foulsCommitted: "Fouls",
  shotAssists: "Key passes",
  goalAssists: "Assists",
  totalGoals: "Goals",
  appearances: "Appearances",
  form: "Form",
  record: "Record",
  rank: "Rank",
};

export const STAT_ORDER = [
  "possessionPct",
  "totalShots",
  "shotsOnTarget",
  "wonCorners",
  "foulsCommitted",
  "shotAssists",
];
