import Link from "next/link";
import type { InjuryRow } from "@/lib/queries";
import { TeamLogo } from "./team-logo";

type Team = {
  id: number;
  name: string;
  shortName: string | null;
  abbreviation: string | null;
  logoUrl: string | null;
};

const TONE: Record<InjuryRow["availability"], string> = {
  out: "bg-leather text-white",
  doubtful: "bg-leather/25 text-leather",
  questionable: "bg-surface-2 text-ink-2",
  available: "bg-pitch-soft text-pitch",
};

const SHORT: Record<InjuryRow["availability"], string> = {
  out: "OUT",
  doubtful: "DOUBT",
  questionable: "QUES",
  available: "FIT",
};

/** Compact badge used inside market tables, where space is tight. */
export function StatusBadge({ row }: { row: InjuryRow }) {
  if (row.availability === "available") return null;
  return (
    <span
      className={`label rounded px-1 text-[9px] leading-4 ${TONE[row.availability]}`}
      title={`${row.status}${row.injuryType ? ` · ${row.injuryType}` : ""}`}
    >
      {SHORT[row.availability]}
    </span>
  );
}

// ESPN fills these in when it has nothing to say, so they are noise on screen.
const EMPTY_WORDING = new Set(["undisclosed", "not specified", "general soreness", ""]);

function ailment(row: InjuryRow): string {
  const parts: string[] = [];
  for (const part of [row.injuryType, row.detail]) {
    if (!part) continue;
    const clean = part.trim();
    if (EMPTY_WORDING.has(clean.toLowerCase())) continue;
    // ESPN repeats itself: type "Concussion", detail "Concussion"
    if (parts.some((p) => p.toLowerCase() === clean.toLowerCase())) continue;
    parts.push(clean);
  }
  return parts.join(" · ");
}

function formatReturn(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function TeamColumn({ team, rows }: { team: Team; rows: InjuryRow[] }) {
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface">
      <h3 className="label flex items-center gap-2 border-b border-line px-3 py-1.5 text-[11px] text-ink-2">
        <TeamLogo src={team.logoUrl} name={team.name} size={16} />
        <span className="truncate">{team.shortName ?? team.name}</span>
        <span className="tnum ml-auto text-muted">{rows.length}</span>
      </h3>
      {rows.length === 0 ? (
        <p className="px-3 py-2 text-sm text-muted">Nobody listed.</p>
      ) : (
        <ul className="divide-y divide-line">
          {rows.map((r) => {
            const back = formatReturn(r.returnDate);
            const what = ailment(r);
            return (
              <li key={r.playerId} className="px-3 py-1.5 text-sm">
                <div className="flex items-baseline gap-2">
                  <Link href={`/players/${r.playerId}`} className="min-w-0 truncate hover:text-pitch">
                    {r.playerName}
                  </Link>
                  {r.position ? (
                    <span className="label text-[10px] text-muted">{r.position}</span>
                  ) : null}
                  <span
                    className={`label ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] ${TONE[r.availability]}`}
                  >
                    {r.status}
                  </span>
                </div>
                {what || back ? (
                  <p className="text-xs text-muted">
                    {what}
                    {what && back ? " · " : ""}
                    {back ? `back ${back}` : ""}
                  </p>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

/**
 * The availability report for both teams, shown above the markets it changes.
 * Players listed as out are left out of the projections entirely.
 */
export function InjuryReport({
  rows,
  home,
  away,
}: {
  rows: InjuryRow[];
  home: Team;
  away: Team;
}) {
  if (rows.length === 0) return null;
  const forTeam = (id: number) => rows.filter((r) => r.teamId === id);
  const outCount = rows.filter((r) => r.availability === "out").length;
  return (
    <section className="mt-4">
      <h2 className="display mb-2 flex flex-wrap items-baseline gap-x-2 text-xl font-extrabold">
        Availability
        <span className="label text-[11px] font-normal text-muted">
          {outCount > 0 ? `${outCount} ruled out · left out of the projections` : "doubts only"}
        </span>
      </h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <TeamColumn team={away} rows={forTeam(away.id)} />
        <TeamColumn team={home} rows={forTeam(home.id)} />
      </div>
    </section>
  );
}

/** The banner on a player's own page: what the report says, in full. */
export function PlayerStatusNote({ row }: { row: InjuryRow }) {
  if (row.availability === "available") return null;
  const what = ailment(row);
  const back = formatReturn(row.returnDate);
  return (
    <section
      className={`mb-4 rounded-md border-l-4 border border-line bg-surface px-3 py-2 ${
        row.availability === "out" ? "border-l-leather" : "border-l-line-strong"
      }`}
    >
      <p className="flex flex-wrap items-baseline gap-2">
        <span className={`label rounded px-1.5 py-0.5 text-[10px] ${TONE[row.availability]}`}>
          {row.status}
        </span>
        {what ? <span className="text-sm text-ink">{what}</span> : null}
        {back ? <span className="text-sm text-ink-2">expected back {back}</span> : null}
      </p>
      {row.comment ? <p className="mt-1 text-sm text-ink-2">{row.comment}</p> : null}
      <p className="label mt-1 text-[10px] text-muted">
        {row.availability === "out"
          ? "Left out of this week's projections."
          : "Kept in the projections, with the chance of playing applied."}
      </p>
    </section>
  );
}

/** The whole squad's report, on a team page. */
export function TeamAvailability({ rows }: { rows: InjuryRow[] }) {
  if (rows.length === 0) return null;
  return (
    <section className="mt-6">
      <h2 className="label mb-2 text-xs text-muted">Availability · {rows.length} listed</h2>
      <ul className="grid gap-1 sm:grid-cols-2">
        {rows.map((r) => {
          const what = ailment(r);
          return (
            <li
              key={r.playerId}
              className="flex items-baseline gap-2 rounded-md border border-line bg-surface px-3 py-1.5 text-sm"
            >
              <Link href={`/players/${r.playerId}`} className="min-w-0 truncate hover:text-pitch">
                {r.playerName}
              </Link>
              {r.position ? <span className="label text-[10px] text-muted">{r.position}</span> : null}
              {what ? <span className="truncate text-xs text-muted">{what}</span> : null}
              <span className={`label ml-auto shrink-0 rounded px-1.5 py-0.5 text-[10px] ${TONE[r.availability]}`}>
                {r.status}
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
