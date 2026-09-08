import { DateStrip } from "@/components/date-strip";
import { GameGroups } from "@/components/game-groups";
import { PageTitle } from "@/components/page-title";
import { addDays, longDate, parseDateParam, todayIso } from "@/lib/format";
import { daysWithGames, gamesForDate, winProbabilities } from "@/lib/queries";

export const revalidate = 120;

export default async function HomePage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const params = await searchParams;
  const today = todayIso();
  const day = parseDateParam(params.date);
  const [games, withGames] = await Promise.all([
    gamesForDate(day),
    daysWithGames(addDays(day, -3), addDays(day, 3)),
  ]);
  const picks = await winProbabilities(games.map((g) => g.id));
  return (
    <>
      <PageTitle eyebrow="All sports" title={day === today ? "Today" : longDate(day)} />
      <div className="mb-4">
        <DateStrip base="/" selected={day} today={today} withGames={withGames} />
      </div>
      <GameGroups
        games={games}
        picks={picks}
        emptyText="No games on this day. Try another date or a sport tab."
      />
    </>
  );
}
