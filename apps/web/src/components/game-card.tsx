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

export function GameCard({ g }: { g: GameRow }) {
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
      <div className="w-16 text-right">
        <StatusPill
          status={g.status}
          detail={g.statusDetail}
          kickoff={g.kickoff}
          clock={g.clock}
        />
      </div>
    </Link>
  );
}
