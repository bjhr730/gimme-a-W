import Link from "next/link";
import type { GameRow } from "@/lib/queries";
import { StatusPill } from "./status-pill";
import { TeamLogo } from "./team-logo";

function Side({
  team,
  score,
  winner,
  played,
}: {
  team: GameRow["home"];
  score: number | null;
  winner: boolean;
  played: boolean;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <TeamLogo src={team.logoUrl} name={team.name} />
      <span
        className={`truncate text-[15px] ${winner ? "font-semibold text-ink" : played ? "text-ink-2" : "text-ink"}`}
      >
        <span className="sm:hidden">{team.shortName ?? team.name}</span>
        <span className="hidden sm:inline">{team.name}</span>
      </span>
      <span
        className={`display tnum ml-auto pl-2 text-xl leading-none ${
          winner ? "font-extrabold text-ink" : "font-semibold text-ink-2"
        }`}
      >
        {score ?? ""}
      </span>
    </div>
  );
}

export type WinPick = { selection: string; probability: number };

function PickChip({ g, pick }: { g: GameRow; pick: WinPick }) {
  const team = pick.selection === "home" ? g.home : pick.selection === "away" ? g.away : null;
  const label = team ? (team.abbreviation ?? team.shortName ?? team.name) : "Draw";
  const pct = Math.round(pick.probability * 100);
  const hit =
    g.status === "final" && g.homeScore !== null && g.awayScore !== null
      ? pick.selection === "home"
        ? g.homeScore > g.awayScore
        : pick.selection === "away"
          ? g.awayScore > g.homeScore
          : g.homeScore === g.awayScore
      : null;
  return (
    <span
      className={`label mt-1 inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${
        hit === null
          ? "bg-pitch-soft text-pitch"
          : hit
            ? "bg-pitch text-white"
            : "bg-surface-2 text-muted line-through"
      }`}
      title="Our model's pick and win probability"
    >
      W {label} {pct}%
    </span>
  );
}

export function GameCard({ g, pick }: { g: GameRow; pick?: WinPick }) {
  const played = g.status === "final" || g.status === "in_progress";
  const hs = g.homeScore;
  const as = g.awayScore;
  const homeWin = g.status === "final" && hs !== null && as !== null && hs > as;
  const awayWin = g.status === "final" && hs !== null && as !== null && as > hs;
  return (
    <Link
      href={`/games/${g.id}`}
      className="grid grid-cols-[1fr_auto] items-center gap-3 border-b border-line px-3 py-2.5 last:border-b-0 hover:bg-surface-2/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-pitch"
    >
      <div className="grid gap-1.5">
        <Side team={g.away} score={as} winner={awayWin} played={played} />
        <Side team={g.home} score={hs} winner={homeWin} played={played} />
      </div>
      <div className="flex w-20 flex-col items-end text-right">
        <StatusPill
          status={g.status}
          detail={g.statusDetail}
          kickoff={g.kickoff}
          clock={g.clock}
        />
        {pick ? <PickChip g={g} pick={pick} /> : null}
      </div>
    </Link>
  );
}
