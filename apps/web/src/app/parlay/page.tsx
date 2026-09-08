import Link from "next/link";
import { PageTitle } from "@/components/page-title";
import { ParlayBuilder } from "@/components/parlay-builder";
import { parlayForToday } from "@/lib/queries";
import { parseDateParam } from "@/lib/format";

export const revalidate = 300;
export const metadata = {
  title: "Parlay of the day",
  description: "The most likely call in each of today's games, stacked into one ticket.",
};

export default async function ParlayPage({
  searchParams,
}: {
  searchParams: Promise<{ date?: string }>;
}) {
  const { date } = await searchParams;
  const start = parseDateParam(date);
  const { day, legs } = await parlayForToday(start);

  return (
    <>
      <PageTitle
        eyebrow="Most likely to happen"
        title="Parlay of the day"
        aside={
          <Link href="/models" className="label text-xs text-pitch">
            How the models do →
          </Link>
        }
      />
      {legs.length < 2 ? (
        <p className="max-w-[70ch] text-ink-2">
          No parlay yet. The models publish for games in the coming week, so this fills in
          once the next slate is priced. Try the{" "}
          <Link href="/" className="text-pitch">
            day&apos;s games
          </Link>{" "}
          in the meantime.
        </p>
      ) : (
        <ParlayBuilder legs={legs} day={day} />
      )}
    </>
  );
}
