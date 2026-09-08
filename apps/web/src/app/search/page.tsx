import { PageTitle } from "@/components/page-title";
import { SearchBox } from "@/components/search-box";

export const metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <>
      <PageTitle eyebrow="Research" title="Search" />
      <p className="mb-3 max-w-[70ch] text-ink-2">
        Type a team to see its next and last games, two teams for the head-to-head, a player, a
        league for its table, or a day like “sunday” or “tomorrow” for that day&apos;s slate. Press{" "}
        <kbd className="rounded border border-line px-1 text-xs">/</kbd> anywhere to open search.
      </p>
      <SearchBox variant="page" />
    </>
  );
}
