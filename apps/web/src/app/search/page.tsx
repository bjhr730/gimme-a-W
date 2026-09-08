import Link from "next/link";
import { PageTitle } from "@/components/page-title";
import { TeamLogo } from "@/components/team-logo";
import { searchPlayers, searchTeams } from "@/lib/queries";

export const metadata = { title: "Search" };
export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const [teams, players] = await Promise.all([searchTeams(q), searchPlayers(q)]);
  const asked = q.trim().length >= 2;
  return (
    <>
      <PageTitle title="Search" />
      <form action="/search" className="mb-4 flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="Team, city, abbreviation or player"
          autoFocus
          className="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-pitch focus:outline-none"
        />
        <button type="submit" className="label rounded-md bg-pitch px-4 py-2 text-sm text-white">
          Go
        </button>
      </form>
      {asked && teams.length === 0 && players.length === 0 ? (
        <p className="text-ink-2">Nothing matches “{q}”.</p>
      ) : null}

      {teams.length > 0 ? (
        <section className="mb-5">
          <h2 className="label mb-2 text-xs text-muted">Teams</h2>
          <ul className="grid gap-1 sm:grid-cols-2">
            {teams.map((t) => (
              <li key={t.id}>
                <Link
                  href={`/teams/${t.id}`}
                  className="flex items-center gap-3 rounded-md border border-line bg-surface px-3 py-2 hover:border-line-strong"
                >
                  <TeamLogo src={t.logoUrl} name={t.name} size={28} />
                  <span className="min-w-0">
                    <span className="block truncate text-[15px]">{t.name}</span>
                    <span className="label text-[11px] text-muted">
                      {t.sportId === "soccer" ? "Soccer" : "Football"}
                      {t.abbreviation ? ` · ${t.abbreviation}` : ""}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {players.length > 0 ? (
        <section>
          <h2 className="label mb-2 text-xs text-muted">Players</h2>
          <ul className="grid gap-1 sm:grid-cols-2">
            {players.map((p) => (
              <li key={p.id}>
                <Link
                  href={`/players/${p.id}`}
                  className="flex items-center gap-3 rounded-md border border-line bg-surface px-3 py-2 hover:border-line-strong"
                >
                  {p.headshotUrl ? (
                    <img src={p.headshotUrl} alt="" width={28} height={28} className="h-7 w-7 rounded-full bg-surface-2 object-cover object-top" />
                  ) : (
                    <span className="label inline-flex h-7 w-7 items-center justify-center rounded-full bg-surface-2 text-[10px] text-ink-2">
                      {p.fullName.slice(0, 1)}
                    </span>
                  )}
                  <span className="min-w-0">
                    <span className="block truncate text-[15px]">{p.fullName}</span>
                    <span className="label text-[11px] text-muted">
                      {p.sportId === "soccer" ? "Soccer" : "Football"}
                      {p.position ? ` · ${p.position}` : ""}
                    </span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}
