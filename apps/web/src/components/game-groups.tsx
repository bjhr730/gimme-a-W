import Link from "next/link";
import type { GameRow } from "@/lib/queries";
import { GameCard, type WinPick } from "./game-card";

/** Games grouped by competition, in the order they were fetched (kickoff then name). */
export function GameGroups({
  games,
  emptyText,
  picks,
}: {
  games: GameRow[];
  emptyText: string;
  picks?: Map<number, WinPick>;
}) {
  if (games.length === 0) {
    return (
      <p className="rounded-md border border-dashed border-line-strong px-4 py-8 text-center text-ink-2">
        {emptyText}
      </p>
    );
  }
  const groups = new Map<string, { name: string; games: GameRow[] }>();
  for (const g of games) {
    const entry = groups.get(g.competitionSlug) ?? { name: g.competitionName, games: [] };
    entry.games.push(g);
    groups.set(g.competitionSlug, entry);
  }
  return (
    <div className="grid gap-4">
      {[...groups.entries()].map(([slug, group]) => (
        <section key={slug} className="overflow-hidden rounded-md border border-line bg-surface">
          <header className="flex items-center justify-between border-b border-line bg-surface-2/70 px-3 py-1.5">
            <h2 className="label text-xs text-ink-2">{group.name}</h2>
            <Link href={`/standings/${slug}`} className="label text-[11px] text-pitch">
              Table
            </Link>
          </header>
          {group.games.map((g) => (
            <GameCard key={g.id} g={g} pick={picks?.get(g.id)} />
          ))}
        </section>
      ))}
    </div>
  );
}
