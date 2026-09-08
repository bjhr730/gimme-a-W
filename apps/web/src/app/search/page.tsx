import Link from "next/link";
import { PageTitle } from "@/components/page-title";
import { TeamLogo } from "@/components/team-logo";
import { searchTeams } from "@/lib/queries";

export const metadata = { title: "Search" };
export const dynamic = "force-dynamic";

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q = "" } = await searchParams;
  const results = await searchTeams(q);
  return (
    <>
      <PageTitle title="Search" />
      <form action="/search" className="mb-4 flex gap-2">
        <input
          type="search"
          name="q"
          defaultValue={q}
          placeholder="Team name, city or abbreviation"
          autoFocus
          className="min-w-0 flex-1 rounded-md border border-line-strong bg-surface px-3 py-2 text-base text-ink placeholder:text-muted focus:border-pitch focus:outline-none"
        />
        <button type="submit" className="label rounded-md bg-pitch px-4 py-2 text-sm text-white">
          Go
        </button>
      </form>
      {q.trim().length >= 2 && results.length === 0 ? (
        <p className="text-ink-2">No teams match “{q}”.</p>
      ) : null}
      <ul className="grid gap-1 sm:grid-cols-2">
        {results.map((t) => (
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
    </>
  );
}
