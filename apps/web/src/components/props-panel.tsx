import Link from "next/link";
import type { InjuryRow, PropRow } from "@/lib/queries";
import { StatusBadge } from "./injury-report";

type Team = { id: number; name: string; shortName: string | null; abbreviation: string | null };

type Statuses = Map<number, InjuryRow>;

function pct(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `${Math.round(Number(v) * 100)}%`;
}

function label(t: Team): string {
  return t.abbreviation ?? t.shortName ?? t.name;
}

function PlayerName({
  row,
  statuses,
  team,
}: {
  row: { subjectId: number; playerName: string | null; playerPosition: string | null };
  statuses: Statuses;
  team?: Team;
}) {
  const status = statuses.get(row.subjectId);
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      {team ? <span className="label w-9 shrink-0 text-[10px] text-muted">{label(team)}</span> : null}
      <Link href={`/players/${row.subjectId}`} className="min-w-0 truncate hover:text-pitch">
        {row.playerName}
      </Link>
      {row.playerPosition ? (
        <span className="label shrink-0 text-[10px] text-muted">{row.playerPosition}</span>
      ) : null}
      {status ? <StatusBadge row={status} /> : null}
    </span>
  );
}

function YardsTable({
  title,
  rows,
  statuses,
}: {
  title: string;
  rows: PropRow[];
  statuses: Statuses;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface">
      <h3 className="label border-b border-line px-3 py-1.5 text-[11px] text-ink-2">{title}</h3>
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            <th className="label px-3 py-1 text-left text-[11px] text-muted">Player</th>
            <th className="label px-2 py-1 text-right text-[11px] text-muted">Projection</th>
            <th className="label px-2 py-1 text-right text-[11px] text-muted">Middle half</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const q = (r.quantiles ?? {}) as { p25?: number; p75?: number };
            return (
              <tr key={`${r.market}-${r.subjectId}`} className="border-b border-line last:border-b-0">
                <td className="max-w-[170px] px-3 py-1">
                  <PlayerName row={r} statuses={statuses} />
                </td>
                <td className="tnum px-2 py-1 text-right font-semibold">{Number(r.mean).toFixed(0)}</td>
                <td className="tnum px-2 py-1 text-right text-ink-2">
                  {q.p25 !== undefined && q.p75 !== undefined ? `${Math.round(q.p25)}–${Math.round(q.p75)}` : "–"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ScorerList({
  title,
  rows,
  teams,
  statuses,
}: {
  title: string;
  rows: PropRow[];
  teams: Team[];
  statuses: Statuses;
}) {
  if (rows.length === 0) return null;
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface">
      <h3 className="label border-b border-line px-3 py-1.5 text-[11px] text-ink-2">{title}</h3>
      <ul className="divide-y divide-line">
        {rows.map((r) => {
          const team = teams.find((t) => t.id === r.teamId);
          const p = Number(r.probability);
          return (
            <li key={r.subjectId} className="flex items-center gap-2 px-3 py-1.5 text-sm">
              <span className="min-w-0 flex-1">
                <PlayerName row={r} statuses={statuses} team={team} />
              </span>
              <span className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-surface-2">
                <span className="block h-full bg-pitch" style={{ width: `${Math.min(100, p * 100)}%` }} />
              </span>
              <span className="tnum w-10 shrink-0 text-right font-semibold">{pct(r.probability)}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function CountTile({ title, rows, teams }: { title: string; rows: PropRow[]; teams: Team[] }) {
  const means = rows.filter((r) => r.selection === "");
  if (means.length === 0) return null;
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface">
      <h3 className="label border-b border-line px-3 py-1.5 text-[11px] text-ink-2">{title}</h3>
      <div className="grid gap-2 p-3 sm:grid-cols-2">
        {means.map((m) => {
          const team = teams.find((t) => t.id === m.subjectId);
          const lines = rows
            .filter((r) => r.subjectType === m.subjectType && r.subjectId === m.subjectId && r.selection.startsWith("over"))
            .sort((a, b) => Number(a.line) - Number(b.line));
          return (
            <div key={`${m.subjectType}-${m.subjectId}`}>
              <p className="flex items-baseline gap-2">
                <span className="label text-[11px] text-muted">{team ? team.name : "Match"}</span>
                <span className="display tnum text-2xl font-extrabold">{Number(m.mean).toFixed(1)}</span>
              </p>
              <ul className="mt-1 flex flex-wrap gap-1">
                {lines.map((l) => (
                  <li key={l.selection} className="tnum rounded bg-surface-2 px-1.5 py-0.5 text-[11px] text-ink-2">
                    {l.selection.replace("over", "O")} {pct(l.probability)}
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>
    </div>
  );
}

type SoccerPlayer = {
  playerId: number;
  name: string | null;
  position: string | null;
  teamId: number | null;
  goalProbability: number | null;
  expectedGoals: number | null;
  assistProbability: number | null;
  expectedAssists: number | null;
  expectedSot: number | null;
  sotProbability: number | null;
};

/** Fold the per-market rows back into one row per player. */
function soccerPlayers(rows: PropRow[]): SoccerPlayer[] {
  const byPlayer = new Map<number, SoccerPlayer>();
  const get = (r: PropRow) => {
    let entry = byPlayer.get(r.subjectId);
    if (!entry) {
      entry = {
        playerId: r.subjectId,
        name: r.playerName,
        position: r.playerPosition,
        teamId: r.teamId,
        goalProbability: null,
        expectedGoals: null,
        assistProbability: null,
        expectedAssists: null,
        expectedSot: null,
        sotProbability: null,
      };
      byPlayer.set(r.subjectId, entry);
    }
    return entry;
  };
  for (const r of rows) {
    if (r.subjectType !== "player") continue;
    const entry = get(r);
    if (r.market === "anytime_scorer") {
      entry.goalProbability = r.probability === null ? null : Number(r.probability);
      entry.expectedGoals = r.mean === null ? null : Number(r.mean);
    } else if (r.market === "anytime_assist") {
      entry.assistProbability = r.probability === null ? null : Number(r.probability);
      entry.expectedAssists = r.mean === null ? null : Number(r.mean);
    } else if (r.market === "player_shots_on_target") {
      if (r.selection === "") entry.expectedSot = r.mean === null ? null : Number(r.mean);
      if (r.selection === "over 0.5") {
        entry.sotProbability = r.probability === null ? null : Number(r.probability);
      }
    }
  }
  return [...byPlayer.values()];
}

function Cell({ probability, quantity }: { probability: number | null; quantity: number | null }) {
  if (probability === null && quantity === null) return <span className="text-muted">–</span>;
  return (
    <span className="block leading-tight">
      <span className="tnum block font-semibold">{probability === null ? "–" : pct(probability)}</span>
      {quantity !== null ? (
        <span className="tnum block text-[11px] text-muted">{quantity.toFixed(2)}</span>
      ) : null}
    </span>
  );
}

/**
 * Goals, assists and shots on target for the players most likely to produce
 * them. The big number is the chance of at least one; the small number under it
 * is how many the model expects.
 */
function SoccerPlayerTable({
  rows,
  teams,
  statuses,
}: {
  rows: PropRow[];
  teams: Team[];
  statuses: Statuses;
}) {
  const players = soccerPlayers(rows);
  if (players.length === 0) return null;
  const ranked = players
    .filter((p) => (p.goalProbability ?? 0) > 0 || (p.expectedSot ?? 0) > 0)
    .sort((a, b) => (b.goalProbability ?? 0) - (a.goalProbability ?? 0))
    .slice(0, 14);
  if (ranked.length === 0) return null;
  return (
    <div className="min-w-0 rounded-md border border-line bg-surface lg:col-span-2">
      <h3 className="label border-b border-line px-3 py-1.5 text-[11px] text-ink-2">
        Goals, assists and shots on target
      </h3>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[340px] text-sm">
          <thead>
            <tr className="border-b border-line">
              <th className="label px-3 py-1 text-left text-[11px] text-muted">Player</th>
              <th className="label px-2 py-1 text-right text-[11px] text-muted">Goal</th>
              <th className="label px-2 py-1 text-right text-[11px] text-muted">Assist</th>
              <th className="label px-2 py-1 text-right text-[11px] text-muted">On target</th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((p) => {
              const team = teams.find((t) => t.id === p.teamId);
              const status = statuses.get(p.playerId);
              return (
                <tr key={p.playerId} className="border-b border-line last:border-b-0">
                  <td className="max-w-[190px] px-3 py-1.5">
                    <span className="flex min-w-0 items-center gap-1.5">
                      {team ? (
                        <span className="label w-9 shrink-0 text-[10px] text-muted">{label(team)}</span>
                      ) : null}
                      <Link href={`/players/${p.playerId}`} className="min-w-0 truncate hover:text-pitch">
                        {p.name}
                      </Link>
                      {p.position ? (
                        <span className="label shrink-0 text-[10px] text-muted">{p.position}</span>
                      ) : null}
                      {status ? <StatusBadge row={status} /> : null}
                    </span>
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Cell probability={p.goalProbability} quantity={p.expectedGoals} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Cell probability={p.assistProbability} quantity={p.expectedAssists} />
                  </td>
                  <td className="px-2 py-1.5 text-right">
                    <Cell probability={p.sotProbability} quantity={p.expectedSot} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="border-t border-line px-3 py-1.5 text-[11px] text-muted">
        Top line: chance of at least one. Below it: how many the model expects.
      </p>
    </div>
  );
}

export function PropsPanel({
  rows,
  home,
  away,
  soccer,
  statuses,
}: {
  rows: PropRow[];
  home: Team;
  away: Team;
  soccer: boolean;
  statuses?: Statuses;
}) {
  if (rows.length === 0) return null;
  const teams = [home, away];
  const byStatus: Statuses = statuses ?? new Map();
  const byMarket = (m: string) => rows.filter((r) => r.market === m);
  const top = (list: PropRow[], n: number) =>
    [...list].sort((a, b) => Number(b.probability ?? b.mean) - Number(a.probability ?? a.mean)).slice(0, n);
  const topMean = (list: PropRow[], n: number) => [...list].sort((a, b) => Number(b.mean) - Number(a.mean)).slice(0, n);

  return (
    <section className="mt-4">
      <h2 className="display mb-2 text-xl font-extrabold">Player and team markets</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        {soccer ? (
          <>
            <SoccerPlayerTable rows={rows} teams={teams} statuses={byStatus} />
            <CountTile title="Shots on target" rows={byMarket("shots_on_target")} teams={teams} />
            <CountTile title="Corners" rows={[...byMarket("corners"), ...byMarket("match_corners")]} teams={teams} />
          </>
        ) : (
          <>
            <YardsTable title="Passing yards" rows={topMean(byMarket("passing_yards"), 2)} statuses={byStatus} />
            <YardsTable title="Rushing yards" rows={topMean(byMarket("rushing_yards"), 6)} statuses={byStatus} />
            <YardsTable title="Receiving yards" rows={topMean(byMarket("receiving_yards"), 8)} statuses={byStatus} />
            <ScorerList title="Anytime touchdown" rows={top(byMarket("anytime_td"), 10)} teams={teams} statuses={byStatus} />
          </>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        {soccer
          ? "Each player takes a share of the team's expected goals and shots on target, from their recent rate and the minutes they are likely to play. Players reported out are left out."
          : "Projections use each player's last eight games, the team's share of volume, what the opponent has allowed, and the market's game script. Middle half = 25th to 75th percentile. Players reported out are left out."}
      </p>
    </section>
  );
}
