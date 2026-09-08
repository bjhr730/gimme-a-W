import Link from "next/link";
import { TeamLogo } from "./team-logo";

type Entry = {
  rank: number | null;
  played: number | null;
  wins: number | null;
  draws: number | null;
  losses: number | null;
  points: number | null;
  pointsFor: number | null;
  pointsAgainst: number | null;
  stats: unknown;
  team: {
    id: number;
    name: string;
    shortName: string | null;
    abbreviation: string | null;
    logoUrl: string | null;
  };
};

export function StandingsTable({
  entries,
  sportId,
  highlightTeamId,
}: {
  entries: Entry[];
  sportId: string;
  highlightTeamId?: number;
}) {
  const soccer = sportId === "soccer";
  const thBase = "label px-2 py-1.5 text-[11px] text-muted";
  const th = `${thBase} text-right`;
  const td = "tnum px-2 py-1.5 text-right";
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-sm">
        <thead className="border-b border-line">
          <tr>
            <th className={`${thBase} w-7 text-left`}>#</th>
            <th className={`${thBase} text-left`}>Team</th>
            {soccer ? (
              <>
                <th className={th}>P</th>
                <th className={th}>W</th>
                <th className={th}>D</th>
                <th className={th}>L</th>
                <th className={th}>GD</th>
                <th className={`${th} text-ink`}>Pts</th>
              </>
            ) : (
              <>
                <th className={th}>W</th>
                <th className={th}>L</th>
                <th className={th}>T</th>
                <th className={th}>PF</th>
                <th className={th}>PA</th>
                <th className={th}>Diff</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {entries.map((e, i) => {
            const gd =
              e.pointsFor !== null && e.pointsAgainst !== null ? e.pointsFor - e.pointsAgainst : null;
            const highlight = e.team.id === highlightTeamId;
            return (
              <tr
                key={e.team.id}
                className={`border-b border-line last:border-b-0 ${highlight ? "bg-pitch-soft" : ""}`}
              >
                <td className="tnum px-2 py-1.5 text-muted">{e.rank ?? i + 1}</td>
                <td className="px-2 py-1.5">
                  <Link href={`/teams/${e.team.id}`} className="flex items-center gap-2">
                    <TeamLogo src={e.team.logoUrl} name={e.team.name} size={20} />
                    <span className="truncate sm:hidden">{e.team.shortName ?? e.team.name}</span>
                    <span className="hidden truncate sm:inline">{e.team.name}</span>
                  </Link>
                </td>
                {soccer ? (
                  <>
                    <td className={td}>{e.played ?? "–"}</td>
                    <td className={td}>{e.wins ?? "–"}</td>
                    <td className={td}>{e.draws ?? "–"}</td>
                    <td className={td}>{e.losses ?? "–"}</td>
                    <td className={td}>{gd === null ? "–" : gd > 0 ? `+${gd}` : gd}</td>
                    <td className={`${td} font-semibold text-ink`}>{e.points ?? "–"}</td>
                  </>
                ) : (
                  <>
                    <td className={`${td} font-semibold text-ink`}>{e.wins ?? "–"}</td>
                    <td className={td}>{e.losses ?? "–"}</td>
                    <td className={td}>{e.draws ?? 0}</td>
                    <td className={td}>{e.pointsFor ?? "–"}</td>
                    <td className={td}>{e.pointsAgainst ?? "–"}</td>
                    <td className={td}>{gd === null ? "–" : gd > 0 ? `+${gd}` : gd}</td>
                  </>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
