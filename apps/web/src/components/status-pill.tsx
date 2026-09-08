import { LocalTime } from "./local-time";

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
        {clock && clock !== "0:00" ? clock : detail ?? "Live"}
      </span>
    );
  }
  if (status === "final") {
    return <span className="label text-xs text-muted">{detail ?? "Final"}</span>;
  }
  if (status === "scheduled") {
    return (
      <span className="label text-xs text-ink-2">
        <LocalTime iso={kickoff.toISOString()} />
      </span>
    );
  }
  return <span className="label text-xs text-leather">{detail ?? status}</span>;
}
