import Link from "next/link";
import { statNumber } from "@/lib/format";

export type PlayerStatRow = {
  teamId: number;
  stats: unknown;
  player: {
    id: number;
    fullName: string;
    shortName: string | null;
    position: string | null;
    headshotUrl: string | null;
  };
};

type Stats = Record<string, unknown>;

const FOOTBALL_TABLES: { title: string; category: string; cols: [string, string][] }[] = [
  {
    title: "Passing",
    category: "passing",
    cols: [
      ["completions", "C"],
      ["passingAttempts", "ATT"],
      ["passingYards", "YDS"],
      ["passingTouchdowns", "TD"],
      ["interceptions", "INT"],
    ],
  },
  {
    title: "Rushing",
    category: "rushing",
    cols: [
      ["rushingAttempts", "CAR"],
      ["rushingYards", "YDS"],
      ["yardsPerRushAttempt", "AVG"],
      ["rushingTouchdowns", "TD"],
    ],
  },
  {
    title: "Receiving",
    category: "receiving",
    cols: [
      ["receptions", "REC"],
      ["receivingYards", "YDS"],
      ["yardsPerReception", "AVG"],
      ["receivingTouchdowns", "TD"],
    ],
  },
];

const SOCCER_COLS: [string, string][] = [
  ["totalGoals", "G"],
  ["goalAssists", "A"],
  ["totalShots", "SH"],
  ["shotsOnTarget", "SOT"],
  ["foulsCommitted", "F"],
  ["yellowCards", "YC"],
];

function Name({ p }: { p: PlayerStatRow["player"] }) {
  return (
    <Link href={`/players/${p.id}`} className="flex min-w-0 items-center gap-2 hover:text-pitch">
      <span className="truncate">{p.shortName ?? p.fullName}</span>
      {p.position ? <span className="label text-[10px] text-muted">{p.position}</span> : null}
    </Link>
  );
}

function Table({ title, cols, rows }: { title: string; cols: [string, string][]; rows: PlayerStatRow[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="min-w-0 overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-line">
            <th className="label px-2 py-1 text-left text-[11px] text-muted">{title}</th>
            {cols.map(([k, label]) => (
              <th key={k} className="label px-2 py-1 text-right text-[11px] text-muted">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const s = r.stats as Stats;
            return (
              <tr key={r.player.id} className="border-b border-line last:border-b-0">
                <td className="max-w-[180px] px-2 py-1">
                  <Name p={r.player} />
                </td>
                {cols.map(([k]) => (
                  <td key={k} className="tnum px-2 py-1 text-right text-ink-2">
                    {statNumber(s[k])}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function num(v: unknown): number {
  return typeof v === "number" ? v : Number.NaN;
}

export function FootballBoxScore({ rows }: { rows: PlayerStatRow[] }) {
  return (
    <div className="grid gap-3">
      {FOOTBALL_TABLES.map((t) => {
        const yardsKey = t.cols[t.cols.length === 5 ? 2 : 1][0];
        const subset = rows
          .filter((r) => {
            const s = r.stats as Stats;
            const cats = Array.isArray(s.categories) ? (s.categories as string[]) : [];
            return cats.includes(t.category);
          })
          .sort((a, b) => num((b.stats as Stats)[yardsKey]) - num((a.stats as Stats)[yardsKey]));
        return <Table key={t.category} title={t.title} cols={t.cols} rows={subset} />;
      })}
    </div>
  );
}

export function SoccerLineup({ rows }: { rows: PlayerStatRow[] }) {
  const starters = rows.filter((r) => (r.stats as Stats).starter === true);
  const bench = rows.filter((r) => (r.stats as Stats).starter !== true);
  const sortByPlace = (a: PlayerStatRow, b: PlayerStatRow) =>
    num((a.stats as Stats).formationPlace) - num((b.stats as Stats).formationPlace);
  const formation = (rows[0]?.stats as Stats | undefined)?.formation;
  return (
    <div className="grid gap-2">
      {formation ? <p className="label text-[11px] text-muted">Formation {String(formation)}</p> : null}
      <Table title="Starters" cols={SOCCER_COLS} rows={[...starters].sort(sortByPlace)} />
      <Table
        title="Bench"
        cols={SOCCER_COLS}
        rows={bench.filter((r) => (r.stats as Stats).subbedIn === true || num((r.stats as Stats).appearances) > 0)}
      />
    </div>
  );
}
