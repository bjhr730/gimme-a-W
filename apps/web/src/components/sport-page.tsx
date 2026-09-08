import Link from "next/link";
import { DateStrip } from "@/components/date-strip";
import { GameGroups } from "@/components/game-groups";
import { PageTitle } from "@/components/page-title";
import { SPORTS, addDays, longDate, parseDateParam, todayIso, type SportKey } from "@/lib/format";
import {
  competitionsWithSeasons,
  daysWithGames,
  gamesForDate,
  winProbabilities,
} from "@/lib/queries";

export async function SportPage({
  sport,
  searchParams,
}: {
  sport: SportKey;
  searchParams: Promise<{ date?: string }>;
}) {
  const meta = SPORTS[sport];
  const params = await searchParams;
  const today = todayIso();
  const day = parseDateParam(params.date);
  const scope = meta.competition
    ? { competitionSlug: meta.competition }
    : { sportId: meta.sportId };
  const [games, withGames, competitions] = await Promise.all([
    gamesForDate(day, scope),
    daysWithGames(addDays(day, -3), addDays(day, 3), scope),
    competitionsWithSeasons(meta.sportId),
  ]);
  const tables = meta.competition
    ? competitions.filter((c) => c.slug === meta.competition)
    : competitions;
  const picks = await winProbabilities(games.map((g) => g.id));

  return (
    <>
      <PageTitle eyebrow={meta.label} title={day === today ? "Today" : longDate(day)} />
      <div className="mb-4">
        <DateStrip base={`/${sport}`} selected={day} today={today} withGames={withGames} />
      </div>
      <GameGroups games={games} picks={picks} emptyText={`No ${meta.label} games on this day.`} />

      <section className="mt-8">
        <h2 className="label mb-2 text-xs text-muted">Standings</h2>
        <ul className="grid gap-1 sm:grid-cols-2">
          {tables.map((c) => (
            <li key={c.slug}>
              <Link
                href={`/standings/${c.slug}`}
                className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 hover:border-line-strong"
              >
                <span>
                  <span className="block text-[15px] text-ink">{c.name}</span>
                  <span className="label text-[11px] text-muted">
                    {c.country ?? c.level ?? ""} {c.seasonLabel ? `· ${c.seasonLabel}` : ""}
                  </span>
                </span>
                <span className="label text-xs text-pitch">Table</span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}
