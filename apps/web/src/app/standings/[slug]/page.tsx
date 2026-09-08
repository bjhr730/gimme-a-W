import { notFound } from "next/navigation";
import { PageTitle } from "@/components/page-title";
import { StandingsTable } from "@/components/standings-table";
import { standingsForCompetition } from "@/lib/queries";

export const revalidate = 300;

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await standingsForCompetition(slug);
  return { title: data ? `${data.competition.name} standings` : "Standings" };
}

export default async function StandingsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const data = await standingsForCompetition(slug);
  if (!data) notFound();
  const { competition, asOf, seasonLabel, groups } = data;
  return (
    <>
      <PageTitle
        eyebrow={seasonLabel ? `Standings · ${seasonLabel}` : "Standings"}
        title={competition.name}
        aside={asOf ? <span className="tnum">as of {asOf}</span> : null}
      />
      {groups.length === 0 ? (
        <p className="text-ink-2">No table collected yet for this competition.</p>
      ) : (
        <div className="grid gap-4">
          {groups.map((group) => (
            <section key={group.name} className="min-w-0 rounded-md border border-line bg-surface">
              {group.name ? (
                <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">{group.name}</h2>
              ) : null}
              <StandingsTable entries={group.entries} sportId={competition.sportId} />
            </section>
          ))}
        </div>
      )}
    </>
  );
}
