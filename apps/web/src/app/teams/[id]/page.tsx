import Link from "next/link";
import { notFound } from "next/navigation";
import { GameCard } from "@/components/game-card";
import { PageTitle } from "@/components/page-title";
import { TeamLogo } from "@/components/team-logo";
import { teamById } from "@/lib/queries";

export const revalidate = 120;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await teamById(Number(id));
  return { title: data?.team.name ?? "Team" };
}

export default async function TeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await teamById(Number(id));
  if (!data) notFound();
  const { team, recent, upcoming, standings } = data;
  const soccer = team.sportId === "soccer";

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <TeamLogo src={team.logoUrl} name={team.name} size={56} />
        <PageTitle
          eyebrow={team.location && team.location !== team.name ? team.location : soccer ? "Club" : "Team"}
          title={team.name}
        />
      </div>

      {standings.length > 0 ? (
        <section className="mb-4 grid gap-2 sm:grid-cols-2">
          {standings.map((s) => (
            <Link
              key={s.competitionSlug}
              href={`/standings/${s.competitionSlug}`}
              className="flex items-center justify-between rounded-md border border-line bg-surface px-3 py-2 hover:border-line-strong"
            >
              <span>
                <span className="block text-[15px]">{s.competitionName}</span>
                <span className="label text-[11px] text-muted">
                  {s.groupName || s.seasonLabel}
                </span>
              </span>
              <span className="text-right">
                <span className="display tnum block text-2xl font-extrabold leading-none">
                  {s.rank ? `#${s.rank}` : "–"}
                </span>
                <span className="tnum text-xs text-ink-2">
                  {soccer
                    ? `${s.wins ?? 0}-${s.draws ?? 0}-${s.losses ?? 0} · ${s.points ?? 0} pts`
                    : `${s.wins ?? 0}-${s.losses ?? 0}${s.draws ? `-${s.draws}` : ""}`}
                </span>
              </span>
            </Link>
          ))}
        </section>
      ) : null}

      <section className="mb-6">
        <h2 className="label mb-2 text-xs text-muted">Upcoming</h2>
        {upcoming.length ? (
          <div className="overflow-hidden rounded-md border border-line bg-surface">
            {upcoming.map((g) => (
              <GameCard key={g.id} g={g} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-2">No upcoming games collected yet.</p>
        )}
      </section>

      <section>
        <h2 className="label mb-2 text-xs text-muted">Recent results</h2>
        {recent.length ? (
          <div className="overflow-hidden rounded-md border border-line bg-surface">
            {recent.map((g) => (
              <GameCard key={g.id} g={g} />
            ))}
          </div>
        ) : (
          <p className="text-sm text-ink-2">No results collected yet.</p>
        )}
      </section>
    </>
  );
}
