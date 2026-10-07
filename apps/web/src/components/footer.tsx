const SOURCES = [
  { name: "football-data.org", href: "https://www.football-data.org", covers: "soccer" },
  {
    name: "football-data.co.uk",
    href: "https://www.football-data.co.uk",
    covers: "soccer shots, corners, closing odds",
  },
  { name: "nflverse", href: "https://github.com/nflverse/nflverse-data", covers: "NFL" },
  {
    name: "CollegeFootballData",
    href: "https://collegefootballdata.com",
    covers: "college football",
  },
  { name: "ESPN", href: "https://www.espn.com", covers: "American football scores" },
];

/**
 * Says where the data comes from and what this is.
 *
 * Two of these sources ask for attribution by name, and the rest are worth
 * naming anyway: a page of predictions with no provenance invites the reader to
 * treat them as authoritative.
 */
export function Footer() {
  return (
    <footer className="mx-auto mt-10 w-full max-w-5xl border-t border-line px-3 py-6 text-xs text-muted sm:px-5">
      <p className="mb-2">
        A personal, non-commercial project. Model output, not betting advice — and not affiliated
        with any league, club or data provider.
      </p>
      <p className="leading-relaxed">
        Data from{" "}
        {SOURCES.map((source, i) => (
          <span key={source.name}>
            <a
              href={source.href}
              rel="noreferrer noopener external"
              target="_blank"
              className="underline decoration-line underline-offset-2 hover:text-pitch"
            >
              {source.name}
            </a>
            <span className="text-muted/70"> ({source.covers})</span>
            {i < SOURCES.length - 1 ? ", " : "."}
          </span>
        ))}
      </p>
    </footer>
  );
}
