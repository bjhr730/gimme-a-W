import Link from "next/link";
import { notFound } from "next/navigation";
import { GameCard } from "@/components/game-card";
import { PageTitle } from "@/components/page-title";
import { TeamLogo } from "@/components/team-logo";
import { eloRank, teamById, teamExtras } from "@/lib/queries";

export const revalidate = 120;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await teamById(Number(id));
  return { title: data?.team.name ?? "Team" };
}

function FormPills({ form }: { form: string | null }) {
  if (!form) return null;
  return (
    <span className="flex gap-1">
      {form.split("").map((ch, i) => (
        <span
          key={i}
          className={`label inline-flex h-6 w-6 items-center justify-center rounded text-xs ${
            ch === "W" ? "bg-pitch text-white" : ch === "L" ? "bg-leather text-white" : "bg-surface-2 text-ink-2"
          }`}
        >
          {ch}
        </span>
      ))}
    </span>
  );
}

export default async function TeamPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const data = await teamById(Number(id));
  if (!data) notFound();
  const { team, recent, upcoming, standings } = data;
  const soccer = team.sportId === "soccer";
  const [extras, rank] = await Promise.all([teamExtras(team.id), eloRank(team.id, team.sportId)]);
  const form = extras.form[0];
  const formStats = (form?.stats ?? {}) as Record<string, number>;

  // Roster grouped by position, football units first when we know them.
  const byPosition = new Map<string, typeof extras.roster>();
  for (const r of extras.roster) {
    const key = r.position ?? "—";
    byPosition.set(key, [...(byPosition.get(key) ?? []), r]);
  }

  return (
    <>
      <div className="mb-4 flex items-center gap-3">
        <TeamLogo src={team.logoUrl} name={team.name} size={56} />
        <PageTitle
          eyebrow={team.location && team.location !== team.name ? team.location : soccer ? "Club" : "Team"}
          title={team.name}
        />
      </div>

      <section className="mb-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
        <div className="rounded-md border border-line bg-surface px-3 py-2">
          <p className="label text-[11px] text-muted">Elo rating</p>
          <p className="display tnum text-2xl font-extrabold leading-none">
            {extras.elo ? Math.round(Number(extras.elo.value)) : "–"}
          </p>
          {rank ? (
            <p className="tnum text-xs text-ink-2">
              #{rank.rank} of {rank.of} {soccer ? "clubs" : "teams"}
            </p>
          ) : null}
        </div>
        <div className="rounded-md border border-line bg-surface px-3 py-2">
          <p className="label text-[11px] text-muted">Last {formStats.games ?? 5}</p>
          <div className="mt-1">
            <FormPills form={form?.form ?? null} />
          </div>
          {form ? (
            <p className="tnum mt-1 text-xs text-ink-2">
              {formStats.wins}-{formStats.draws}-{formStats.losses}
              {form.ppg ? ` · ${Number(form.ppg).toFixed(2)} ppg` : ""}
            </p>
          ) : (
            <p className="text-xs text-ink-2">No form yet</p>
          )}
        </div>
        <div className="rounded-md border border-line bg-surface px-3 py-2">
          <p className="label text-[11px] text-muted">Scoring, last {formStats.games ?? 5}</p>
          <p className="display tnum text-2xl font-extrabold leading-none">
            {form ? `${formStats.avg_for} – ${formStats.avg_against}` : "–"}
          </p>
          <p className="tnum text-xs text-ink-2">
            {form?.marginPerGame ? `${Number(form.marginPerGame) > 0 ? "+" : ""}${Number(form.marginPerGame).toFixed(2)} per game` : ""}
          </p>
        </div>
        <div className="rounded-md border border-line bg-surface px-3 py-2">
          <p className="label text-[11px] text-muted">Rest</p>
          <p className="display tnum text-2xl font-extrabold leading-none">
            {form?.restDays !== null && form?.restDays !== undefined ? `${form.restDays}d` : "–"}
          </p>
          <p className="text-xs text-ink-2">since last game</p>
        </div>
      </section>

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
                <span className="label text-[11px] text-muted">{s.groupName || s.seasonLabel}</span>
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

      <div className="grid gap-6 lg:grid-cols-2">
        <section>
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
      </div>

      {extras.roster.length > 0 ? (
        <section className="mt-6">
          <h2 className="label mb-2 text-xs text-muted">Roster · {extras.roster.length} players</h2>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {[...byPosition.entries()].map(([pos, players]) => (
              <div key={pos} className="rounded-md border border-line bg-surface">
                <h3 className="label border-b border-line px-3 py-1 text-[11px] text-muted">{pos}</h3>
                <ul>
                  {players.map((r) => (
                    <li key={r.player.id}>
                      <Link
                        href={`/players/${r.player.id}`}
                        className="flex items-center gap-2 px-3 py-1 text-sm hover:bg-surface-2/60"
                      >
                        <span className="tnum w-7 text-right text-muted">{r.jersey ?? ""}</span>
                        <span className="truncate">{r.player.fullName}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  );
}
