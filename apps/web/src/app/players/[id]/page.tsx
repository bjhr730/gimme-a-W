import Link from "next/link";
import { notFound } from "next/navigation";
import { LocalTime } from "@/components/local-time";
import { TeamLogo } from "@/components/team-logo";
import { statNumber } from "@/lib/format";
import { PlayerStatusNote } from "@/components/injury-report";
import { playerById, playerInjury } from "@/lib/queries";

export const revalidate = 300;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await playerById(Number(id));
  return { title: data?.player.fullName ?? "Player" };
}

type Stats = Record<string, unknown>;

const FOOTBALL_LOG: [string, string][] = [
  ["completions", "C"],
  ["passingAttempts", "ATT"],
  ["passingYards", "Pass"],
  ["passingTouchdowns", "PTD"],
  ["rushingAttempts", "CAR"],
  ["rushingYards", "Rush"],
  ["rushingTouchdowns", "RTD"],
  ["receptions", "REC"],
  ["receivingYards", "Recv"],
  ["receivingTouchdowns", "ReTD"],
];

const SOCCER_LOG: [string, string][] = [
  ["totalGoals", "G"],
  ["goalAssists", "A"],
  ["totalShots", "SH"],
  ["shotsOnTarget", "SOT"],
  ["yellowCards", "YC"],
];

function age(birth: string | null): number | null {
  if (!birth) return null;
  const b = new Date(birth);
  const now = new Date();
  let a = now.getUTCFullYear() - b.getUTCFullYear();
  const m = now.getUTCMonth() - b.getUTCMonth();
  if (m < 0 || (m === 0 && now.getUTCDate() < b.getUTCDate())) a -= 1;
  return a;
}

export default async function PlayerPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await playerById(Number(id));
  if (!data) notFound();
  const status = await playerInjury(Number(id));
  const { player, teams, log } = data;
  const soccer = player.sportId === "soccer";
  const current = teams[0];
  const cols = soccer ? SOCCER_LOG : FOOTBALL_LOG;
  // Only show columns this player has ever recorded, so a kicker's log is not all dashes.
  const used = cols.filter(([k]) => log.some((g) => (g.stats as Stats)[k] !== undefined));
  const totals = Object.fromEntries(
    used.map(([k]) => [
      k,
      log.reduce((sum, g) => {
        const v = (g.stats as Stats)[k];
        return typeof v === "number" ? sum + v : sum;
      }, 0),
    ]),
  );
  const playerAge = age(player.birthDate);

  return (
    <>
      <div className="mb-4 flex items-center gap-4">
        {player.headshotUrl ? (
          <img
            src={player.headshotUrl}
            alt=""
            width={96}
            height={96}
            className="h-20 w-20 rounded-full bg-surface-2 object-cover object-top"
          />
        ) : (
          <span className="display flex h-20 w-20 items-center justify-center rounded-full bg-surface-2 text-3xl text-muted">
            {player.fullName.slice(0, 1)}
          </span>
        )}
        <div className="min-w-0">
          <p className="label text-xs text-muted">
            {player.position ?? (soccer ? "Player" : "")}
            {current?.jersey ? ` · #${current.jersey}` : ""}
          </p>
          <h1 className="display text-3xl font-extrabold leading-none sm:text-4xl">{player.fullName}</h1>
          {current ? (
            <Link href={`/teams/${current.team.id}`} className="mt-1 flex items-center gap-2 text-sm text-ink-2 hover:text-pitch">
              <TeamLogo src={current.team.logoUrl} name={current.team.name} size={20} />
              {current.team.name}
              <span className="text-muted">· {current.seasonLabel}</span>
            </Link>
          ) : null}
        </div>
      </div>

      {status ? <PlayerStatusNote row={status} /> : null}

      <dl className="mb-6 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {[
          ["Age", playerAge ?? "–"],
          ["Height", player.heightCm ? `${player.heightCm} cm` : "–"],
          ["Weight", player.weightKg ? `${player.weightKg} kg` : "–"],
          ["From", player.nationality ?? "–"],
        ].map(([k, v]) => (
          <div key={String(k)} className="rounded-md border border-line bg-surface px-3 py-2">
            <dt className="label text-[11px] text-muted">{k}</dt>
            <dd className="tnum text-[15px]">{v}</dd>
          </div>
        ))}
      </dl>

      <section className="rounded-md border border-line bg-surface">
        <h2 className="label flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-ink-2">
          <span>Game log</span>
          <span className="text-muted">last {log.length}</span>
        </h2>
        {log.length === 0 ? (
          <p className="px-3 py-4 text-sm text-ink-2">No box scores collected for this player yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead>
                <tr className="border-b border-line">
                  <th className="label px-3 py-1.5 text-left text-[11px] text-muted">Game</th>
                  <th className="label px-2 py-1.5 text-right text-[11px] text-muted">Score</th>
                  {used.map(([k, label]) => (
                    <th key={k} className="label px-2 py-1.5 text-right text-[11px] text-muted">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {log.map((g) => {
                  const own = g.teamId === g.home.id ? g.home : g.away;
                  const opp = g.teamId === g.home.id ? g.away : g.home;
                  const home = g.teamId === g.home.id;
                  const s = g.stats as Stats;
                  return (
                    <tr key={g.id} className="border-b border-line last:border-b-0">
                      <td className="px-3 py-1.5">
                        <Link href={`/games/${g.id}`} className="flex items-center gap-2 hover:text-pitch">
                          <span className="label w-6 text-[10px] text-muted">{home ? "vs" : "at"}</span>
                          <TeamLogo src={opp.logoUrl} name={opp.name} size={18} />
                          <span className="truncate">{opp.shortName ?? opp.name}</span>
                          <span className="label text-[10px] text-muted">
                            <LocalTime iso={g.kickoff.toISOString()} mode="datetime" />
                          </span>
                        </Link>
                      </td>
                      <td className="tnum px-2 py-1.5 text-right text-ink-2">
                        {g.status === "final" || g.status === "in_progress"
                          ? `${home ? g.homeScore : g.awayScore}–${home ? g.awayScore : g.homeScore}`
                          : "–"}
                        {soccer && s.starter === false ? (
                          <span className="label ml-1 text-[9px] text-muted">sub</span>
                        ) : null}
                        {own.id ? null : null}
                      </td>
                      {used.map(([k]) => (
                        <td key={k} className="tnum px-2 py-1.5 text-right">
                          {statNumber(s[k])}
                        </td>
                      ))}
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr className="border-t border-line-strong">
                  <td className="label px-3 py-1.5 text-[11px] text-muted" colSpan={2}>
                    Total
                  </td>
                  {used.map(([k]) => (
                    <td key={k} className="tnum px-2 py-1.5 text-right font-semibold">
                      {statNumber(totals[k])}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
