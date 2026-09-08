import Link from "next/link";
import { notFound } from "next/navigation";
import { LocalTime } from "@/components/local-time";
import { StatusPill } from "@/components/status-pill";
import { TeamLogo } from "@/components/team-logo";
import { FootballBoxScore, SoccerLineup } from "@/components/player-stats";
import { STAT_HIDDEN, STAT_LABELS, STAT_ORDER, americanOdds, signed, statNumber } from "@/lib/format";
import { gameById, gamePicks, gamePlayers } from "@/lib/queries";

export const revalidate = 60;

export async function generateMetadata({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const g = await gameById(Number(id));
  if (!g) return { title: "Game" };
  return { title: `${g.away.shortName ?? g.away.name} at ${g.home.shortName ?? g.home.name}` };
}

function TeamHeader({
  team,
  score,
  winner,
  align,
}: {
  team: { id: number; name: string; shortName: string | null; logoUrl: string | null };
  score: number | null;
  winner: boolean;
  align: "left" | "right";
}) {
  return (
    <div
      className={`flex min-w-0 items-center gap-2 sm:gap-3 ${align === "right" ? "flex-row-reverse text-right" : ""}`}
    >
      <TeamLogo src={team.logoUrl} name={team.name} size={40} />
      <div className="min-w-0 flex-1">
        <Link href={`/teams/${team.id}`} className="block truncate text-[15px] font-semibold text-ink">
          <span className="sm:hidden">{team.shortName ?? team.name}</span>
          <span className="hidden sm:inline">{team.name}</span>
        </Link>
        <span
          className={`display tnum block text-4xl leading-none ${winner ? "font-extrabold text-ink" : "font-semibold text-ink-2"}`}
        >
          {score ?? "–"}
        </span>
      </div>
    </div>
  );
}

export default async function GamePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const g = await gameById(Number(id));
  if (!g) notFound();
  const [players, picks] = await Promise.all([gamePlayers(g.id), gamePicks(g.id)]);
  const awayPlayers = players.filter((p) => p.teamId === g.away.id);
  const homePlayers = players.filter((p) => p.teamId === g.home.id);

  const final = g.status === "final";
  const homeWin = final && g.homeScore !== null && g.awayScore !== null && g.homeScore > g.awayScore;
  const awayWin = final && g.homeScore !== null && g.awayScore !== null && g.awayScore > g.homeScore;

  const statKeys = [
    ...STAT_ORDER.filter((k) => k in g.homeStats || k in g.awayStats),
    ...Object.keys({ ...g.homeStats, ...g.awayStats }).filter(
      (k) => !STAT_ORDER.includes(k) && !STAT_HIDDEN.has(k),
    ),
  ];
  const soccer = g.sportId === "soccer";
  const byMarket = (market: string) => g.odds.filter((o) => o.market === market);
  const h2h = byMarket("h2h");
  const spread = byMarket("spread");
  const total = byMarket("total");
  const pick = (rows: typeof g.odds, sel: string) => rows.find((o) => o.selection === sel);
  const weather = g.weather as { summary?: string; temperature_f?: number };

  return (
    <>
      <p className="label mb-2 text-xs text-muted">
        <Link href={`/standings/${g.competitionSlug}`} className="hover:text-pitch">
          {g.competitionName}
        </Link>
        {g.week ? ` · Week ${g.week}` : ""} · {g.seasonLabel}
      </p>

      <section className="rounded-md border border-line bg-surface p-4">
        <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
          <TeamHeader team={g.away} score={g.awayScore} winner={awayWin} align="left" />
          <div className="label px-2 text-center text-xs text-muted">
            {g.neutralSite ? "vs" : "at"}
          </div>
          <TeamHeader team={g.home} score={g.homeScore} winner={homeWin} align="right" />
        </div>
        <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 border-t border-line pt-3 text-sm text-ink-2">
          <StatusPill status={g.status} detail={g.statusDetail} kickoff={g.kickoff} clock={g.clock} />
          <LocalTime iso={g.kickoff.toISOString()} mode="datetime" />
          {g.venue?.name ? (
            <span>
              {g.venue.name}
              {g.venue.city ? `, ${g.venue.city}` : ""}
            </span>
          ) : null}
          {weather?.summary ? (
            <span>
              {weather.summary}
              {weather.temperature_f !== undefined ? ` · ${weather.temperature_f}°F` : ""}
            </span>
          ) : null}
          {g.attendance ? <span className="tnum">Att. {g.attendance.toLocaleString("en-US")}</span> : null}
        </div>
      </section>

      {(g.homeStats.form || g.awayStats.form || g.homeStats.record || g.awayStats.record) ? (
        <section className="mt-4 grid grid-cols-2 gap-2">
          {[g.away, g.home].map((t, i) => {
            const s = i === 0 ? g.awayStats : g.homeStats;
            return (
              <div key={t.id} className="rounded-md border border-line bg-surface px-3 py-2">
                <p className="label text-[11px] text-muted">{t.shortName ?? t.name}</p>
                {s.form ? (
                  <p className="mt-1 flex gap-1">
                    {String(s.form)
                      .split("")
                      .map((ch, j) => (
                        <span
                          key={j}
                          className={`label inline-flex h-6 w-6 items-center justify-center rounded text-xs ${
                            ch === "W"
                              ? "bg-pitch text-white"
                              : ch === "L"
                                ? "bg-leather text-white"
                                : "bg-surface-2 text-ink-2"
                          }`}
                        >
                          {ch}
                        </span>
                      ))}
                  </p>
                ) : null}
                {s.record ? <p className="tnum mt-1 text-sm text-ink-2">Record {String(s.record)}</p> : null}
                {s.rank ? <p className="tnum text-sm text-ink-2">Ranked #{String(s.rank)}</p> : null}
              </div>
            );
          })}
        </section>
      ) : null}

      {statKeys.length > 0 ? (
        <section className="mt-4 rounded-md border border-line bg-surface">
          <h2 className="label border-b border-line px-3 py-1.5 text-xs text-ink-2">Match stats</h2>
          <table className="w-full text-sm">
            <tbody>
              {statKeys.map((k) => {
                const a = g.awayStats[k];
                const h = g.homeStats[k];
                const an = typeof a === "number" ? a : Number.NaN;
                const hn = typeof h === "number" ? h : Number.NaN;
                const aWin = !Number.isNaN(an) && !Number.isNaN(hn) && an > hn;
                const hWin = !Number.isNaN(an) && !Number.isNaN(hn) && hn > an;
                return (
                  <tr key={k} className="border-b border-line last:border-b-0">
                    <td className={`tnum w-16 px-3 py-1.5 ${aWin ? "font-semibold text-ink" : "text-ink-2"}`}>
                      {statNumber(a)}
                    </td>
                    <td className="label px-3 py-1.5 text-center text-[11px] text-muted">
                      {STAT_LABELS[k] ?? k}
                    </td>
                    <td className={`tnum w-16 px-3 py-1.5 text-right ${hWin ? "font-semibold text-ink" : "text-ink-2"}`}>
                      {statNumber(h)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </section>
      ) : null}

      {g.odds.length > 0 ? (
        <section className="mt-4 rounded-md border border-line bg-surface">
          <h2 className="label flex items-center justify-between border-b border-line px-3 py-1.5 text-xs text-ink-2">
            <span>Lines · {g.odds[0].bookmaker}</span>
            <span className="text-muted">
              <LocalTime iso={g.odds[0].capturedAt.toISOString()} mode="datetime" />
            </span>
          </h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-line">
                <th className="label px-3 py-1.5 text-left text-[11px] text-muted">Market</th>
                <th className="label px-3 py-1.5 text-right text-[11px] text-muted">{g.away.abbreviation ?? "Away"}</th>
                {soccer ? <th className="label px-3 py-1.5 text-right text-[11px] text-muted">Draw</th> : null}
                <th className="label px-3 py-1.5 text-right text-[11px] text-muted">{g.home.abbreviation ?? "Home"}</th>
              </tr>
            </thead>
            <tbody>
              {h2h.length ? (
                <tr className="border-b border-line">
                  <td className="px-3 py-1.5 text-ink-2">Moneyline</td>
                  <td className="tnum px-3 py-1.5 text-right">{americanOdds(Number(pick(h2h, "away")?.price))}</td>
                  {soccer ? <td className="tnum px-3 py-1.5 text-right">{americanOdds(Number(pick(h2h, "draw")?.price))}</td> : null}
                  <td className="tnum px-3 py-1.5 text-right">{americanOdds(Number(pick(h2h, "home")?.price))}</td>
                </tr>
              ) : null}
              {spread.length ? (
                <tr className="border-b border-line">
                  <td className="px-3 py-1.5 text-ink-2">Spread</td>
                  <td className="tnum px-3 py-1.5 text-right">
                    {signed(Number(pick(spread, "away")?.line))}{" "}
                    <span className="text-muted">{americanOdds(Number(pick(spread, "away")?.price))}</span>
                  </td>
                  {soccer ? <td /> : null}
                  <td className="tnum px-3 py-1.5 text-right">
                    {signed(Number(pick(spread, "home")?.line))}{" "}
                    <span className="text-muted">{americanOdds(Number(pick(spread, "home")?.price))}</span>
                  </td>
                </tr>
              ) : null}
              {total.length ? (
                <tr>
                  <td className="px-3 py-1.5 text-ink-2">Total</td>
                  <td className="tnum px-3 py-1.5 text-right">
                    O {statNumber(Number(pick(total, "over")?.line))}{" "}
                    <span className="text-muted">{americanOdds(Number(pick(total, "over")?.price))}</span>
                  </td>
                  {soccer ? <td /> : null}
                  <td className="tnum px-3 py-1.5 text-right">
                    U {statNumber(Number(pick(total, "under")?.line))}{" "}
                    <span className="text-muted">{americanOdds(Number(pick(total, "under")?.price))}</span>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </section>
      ) : null}

      {players.length > 0 ? (
        <section className="mt-4 grid gap-4 lg:grid-cols-2">
          {[
            { team: g.away, rows: awayPlayers },
            { team: g.home, rows: homePlayers },
          ].map(({ team, rows }) => (
            <div key={team.id} className="min-w-0 rounded-md border border-line bg-surface">
              <h2 className="label flex items-center gap-2 border-b border-line px-3 py-1.5 text-xs text-ink-2">
                <TeamLogo src={team.logoUrl} name={team.name} size={18} />
                {team.name}
              </h2>
              <div className="px-1 py-1">
                {soccer ? <SoccerLineup rows={rows} /> : <FootballBoxScore rows={rows} />}
              </div>
            </div>
          ))}
        </section>
      ) : null}

      <section className="mt-4 rounded-md border border-dashed border-line-strong px-4 py-3 text-sm text-ink-2">
        <span className="label text-[11px] text-muted">Prediction</span>
        {picks.length > 0 ? (
          <ul className="mt-1 grid gap-1">
            {picks.map((p) => (
              <li key={p.author} className="flex flex-wrap items-baseline gap-x-2">
                <span className="font-semibold text-ink">{p.author}</span>
                {p.pickTeam ? (
                  <span>
                    {p.pickTeam.shortName ?? p.pickTeam.name}
                    {p.winProbability ? (
                      <span className="tnum"> {Math.round(Number(p.winProbability) * 100)}% to win</span>
                    ) : null}
                  </span>
                ) : null}
                {p.spread ? <span className="tnum text-muted">spread {signed(Number(p.spread))}</span> : null}
              </li>
            ))}
          </ul>
        ) : null}
        <p className="mt-1 text-muted">
          Our own model arrives in phase 4. Until then the bookmaker line and the picks above are the best estimates available.
        </p>
      </section>
    </>
  );
}
