import { LocalTime } from "./local-time";

// The source's own label sometimes lags the status it ships with: finished games
// arrived carrying "Scheduled", which the pill then printed over their score.
// A label that describes a game not yet played tells us nothing about one that is
// under way or over, so it is ignored in favour of the status we parsed.
const PREGAME_LABELS = new Set(["scheduled", "pregame", "pre-game", "upcoming", "tbd"]);

function meaningful(detail: string | null): string | null {
  if (!detail) return null;
  return PREGAME_LABELS.has(detail.trim().toLowerCase()) ? null : detail;
}

export function StatusPill({
  status,
  detail,
  kickoff,
  clock,
}: {
  status: string;
  detail: string | null;
  kickoff: Date;
  clock?: string | null;
}) {
  if (status === "in_progress") {
    return (
      <span className="label inline-flex items-center gap-1 text-xs text-live">
        <span aria-hidden="true" className="inline-block h-1.5 w-1.5 rounded-full bg-live" />
        {clock && clock !== "0:00" ? clock : meaningful(detail) ?? "Live"}
      </span>
    );
  }
  if (status === "final") {
    return <span className="label text-xs text-muted">{meaningful(detail) ?? "Final"}</span>;
  }
  if (status === "scheduled") {
    return (
      <span className="label text-xs text-ink-2">
        <LocalTime iso={kickoff.toISOString()} />
      </span>
    );
  }
  return <span className="label text-xs text-leather">{meaningful(detail) ?? status}</span>;
}
