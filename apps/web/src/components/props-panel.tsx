import Link from "next/link";
import type { PropRow } from "@/lib/queries";

type Team = { id: number; name: string; shortName: string | null; abbreviation: string | null };

function pct(v: string | number | null | undefined): string {
  if (v === null || v === undefined) return "–";
  return `${Math.round(Number(v) * 100)}%`;
}

function label(t: Team): string {
  return t.abbreviation ?? t.shortName ?? t.name;
}

function YardsTable({ title, rows }: { title: string; rows: PropRow[] }) {
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
                  <Link href={`/players/${r.subjectId}`} className="flex items-center gap-2 hover:text-pitch">
                    <span className="truncate">{r.playerName}</span>
                    {r.playerPosition ? <span className="label text-[10px] text-muted">{r.playerPosition}</span> : null}
                  </Link>
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

function ScorerList({ title, rows, teams }: { title: string; rows: PropRow[]; teams: Team[] }) {
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
              <span className="label w-9 text-[10px] text-muted">{team ? label(team) : ""}</span>
              <Link href={`/players/${r.subjectId}`} className="min-w-0 flex-1 truncate hover:text-pitch">
                {r.playerName}
                {r.playerPosition ? <span className="label ml-1 text-[10px] text-muted">{r.playerPosition}</span> : null}
              </Link>
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2">
                <span className="block h-full bg-pitch" style={{ width: `${Math.min(100, p * 100)}%` }} />
              </span>
              <span className="tnum w-10 text-right font-semibold">{pct(r.probability)}</span>
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

export function PropsPanel({ rows, home, away, soccer }: { rows: PropRow[]; home: Team; away: Team; soccer: boolean }) {
  if (rows.length === 0) return null;
  const teams = [home, away];
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
            <CountTile title="Shots on target" rows={byMarket("shots_on_target")} teams={teams} />
            <CountTile title="Corners" rows={[...byMarket("corners"), ...byMarket("match_corners")]} teams={teams} />
            <ScorerList title="Anytime scorer" rows={top(byMarket("anytime_scorer"), 10)} teams={teams} />
          </>
        ) : (
          <>
            <YardsTable title="Passing yards" rows={topMean(byMarket("passing_yards"), 2)} />
            <YardsTable title="Rushing yards" rows={topMean(byMarket("rushing_yards"), 6)} />
            <YardsTable title="Receiving yards" rows={topMean(byMarket("receiving_yards"), 8)} />
            <ScorerList title="Anytime touchdown" rows={top(byMarket("anytime_td"), 10)} teams={teams} />
          </>
        )}
      </div>
      <p className="mt-2 text-xs text-muted">
        Projections use each player&apos;s last eight games, the team&apos;s share of volume, what the opponent has allowed, and the market&apos;s game script. Middle half = 25th to 75th percentile.
      </p>
    </section>
  );
}
