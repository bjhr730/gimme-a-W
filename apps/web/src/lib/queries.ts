import { and, asc, desc, eq, gte, ilike, lt, lte, or, sql } from "drizzle-orm";
import { alias } from "drizzle-orm/pg-core";
import { competition, game, odds, season, standing, team, teamGameStat, venue } from "@gimme/db";
import { db } from "./db";

const home = alias(team, "home");
const away = alias(team, "away");

type TeamLike = {
  id: unknown;
  name: unknown;
  shortName: unknown;
  abbreviation: unknown;
  logoUrl: unknown;
  color: unknown;
};

// Works for the base table and both aliases; the explicit return type keeps drizzle's column types.
function teamCols<T extends TeamLike>(
  t: T,
): {
  id: T["id"];
  name: T["name"];
  shortName: T["shortName"];
  abbreviation: T["abbreviation"];
  logoUrl: T["logoUrl"];
  color: T["color"];
} {
  return {
    id: t.id,
    name: t.name,
    shortName: t.shortName,
    abbreviation: t.abbreviation,
    logoUrl: t.logoUrl,
    color: t.color,
  };
}

const gameCols = {
  id: game.id,
  kickoff: game.kickoff,
  status: game.status,
  statusDetail: game.statusDetail,
  period: game.period,
  clock: game.clock,
  week: game.week,
  homeScore: game.homeScore,
  awayScore: game.awayScore,
  neutralSite: game.neutralSite,
  competitionSlug: competition.slug,
  competitionName: competition.name,
  sportId: competition.sportId,
  home: teamCols(home),
  away: teamCols(away),
};

export type GameRow = Awaited<ReturnType<typeof gamesForDate>>[number];

function baseGames() {
  return db()
    .select(gameCols)
    .from(game)
    .innerJoin(competition, eq(game.competitionId, competition.id))
    .innerJoin(home, eq(game.homeTeamId, home.id))
    .innerJoin(away, eq(game.awayTeamId, away.id));
}

/**
 * A "sports day" runs midnight to midnight in US Eastern time, so a Thursday
 * night NFL kickoff stays on Thursday and a Saturday European match stays on
 * Saturday for viewers in the Americas. Computed in SQL to avoid DST math here.
 */
const SPORTS_TZ = "America/New_York";
const kickoffDay = sql<string>`to_char(${game.kickoff} at time zone ${SPORTS_TZ}, 'YYYY-MM-DD')`;

export async function gamesForDate(
  day: string,
  opts: { sportId?: "soccer" | "american_football"; competitionSlug?: string } = {},
) {
  const filters = [eq(kickoffDay, day)];
  if (opts.competitionSlug) filters.push(eq(competition.slug, opts.competitionSlug));
  else if (opts.sportId) filters.push(eq(competition.sportId, opts.sportId));
  return baseGames()
    .where(and(...filters))
    .orderBy(asc(game.kickoff), asc(competition.name));
}

/** Days around `day` that have at least one game, for the date strip's dots. */
export async function daysWithGames(
  from: string,
  to: string,
  opts: { sportId?: "soccer" | "american_football"; competitionSlug?: string } = {},
): Promise<Set<string>> {
  const filters = [gte(kickoffDay, from), lte(kickoffDay, to)];
  if (opts.competitionSlug) filters.push(eq(competition.slug, opts.competitionSlug));
  else if (opts.sportId) filters.push(eq(competition.sportId, opts.sportId));
  const rows = await db()
    .select({ day: kickoffDay })
    .from(game)
    .innerJoin(competition, eq(game.competitionId, competition.id))
    .where(and(...filters))
    .groupBy(sql`1`);
  return new Set(rows.map((r) => r.day));
}

export async function gameById(id: number) {
  const rows = await db()
    .select({
      ...gameCols,
      attendance: game.attendance,
      weather: game.weather,
      conferenceGame: game.conferenceGame,
      venue: { name: venue.name, city: venue.city, state: venue.state, country: venue.country },
      seasonLabel: season.label,
    })
    .from(game)
    .innerJoin(competition, eq(game.competitionId, competition.id))
    .innerJoin(season, eq(game.seasonId, season.id))
    .innerJoin(home, eq(game.homeTeamId, home.id))
    .innerJoin(away, eq(game.awayTeamId, away.id))
    .leftJoin(venue, eq(game.venueId, venue.id))
    .where(eq(game.id, id))
    .limit(1);
  const g = rows[0];
  if (!g) return null;

  const [stats, oddsRows] = await Promise.all([
    db()
      .select({ teamId: teamGameStat.teamId, stats: teamGameStat.stats })
      .from(teamGameStat)
      .where(eq(teamGameStat.gameId, id)),
    db()
      .select({
        bookmaker: odds.bookmaker,
        market: odds.market,
        selection: odds.selection,
        line: odds.line,
        price: odds.price,
        capturedAt: odds.capturedAt,
      })
      .from(odds)
      .where(eq(odds.gameId, id))
      .orderBy(desc(odds.capturedAt)),
  ]);

  // Latest line per bookmaker/market/selection.
  const latest = new Map<string, (typeof oddsRows)[number]>();
  for (const o of oddsRows) {
    const key = `${o.bookmaker}|${o.market}|${o.selection}`;
    if (!latest.has(key)) latest.set(key, o);
  }

  return {
    ...g,
    homeStats: (stats.find((s) => s.teamId === g.home.id)?.stats ?? {}) as Record<string, unknown>,
    awayStats: (stats.find((s) => s.teamId === g.away.id)?.stats ?? {}) as Record<string, unknown>,
    odds: [...latest.values()],
  };
}

export async function teamById(id: number) {
  const rows = await db().select().from(team).where(eq(team.id, id)).limit(1);
  const t = rows[0];
  if (!t) return null;
  const now = new Date();
  const [recent, upcoming, standings] = await Promise.all([
    baseGames()
      .where(and(or(eq(game.homeTeamId, id), eq(game.awayTeamId, id)), lt(game.kickoff, now)))
      .orderBy(desc(game.kickoff))
      .limit(10),
    baseGames()
      .where(and(or(eq(game.homeTeamId, id), eq(game.awayTeamId, id)), gte(game.kickoff, now)))
      .orderBy(asc(game.kickoff))
      .limit(5),
    db()
      .select({
        competitionSlug: competition.slug,
        competitionName: competition.name,
        seasonLabel: season.label,
        asOf: sql<string>`${standing.asOf}::text`,
        groupName: standing.groupName,
        rank: standing.rank,
        played: standing.played,
        wins: standing.wins,
        draws: standing.draws,
        losses: standing.losses,
        points: standing.points,
      })
      .from(standing)
      .innerJoin(season, eq(standing.seasonId, season.id))
      .innerJoin(competition, eq(season.competitionId, competition.id))
      .where(eq(standing.teamId, id))
      .orderBy(desc(standing.asOf))
      .limit(5),
  ]);
  // keep only the latest snapshot per competition
  const seen = new Set<string>();
  const latestStandings = standings.filter((s) => {
    if (seen.has(s.competitionSlug)) return false;
    seen.add(s.competitionSlug);
    return true;
  });
  return { team: t, recent, upcoming, standings: latestStandings };
}

export async function competitionsWithSeasons(sportId?: "soccer" | "american_football") {
  const rows = await db()
    .select({
      id: competition.id,
      slug: competition.slug,
      name: competition.name,
      country: competition.country,
      sportId: competition.sportId,
      level: competition.level,
      seasonLabel: sql<string>`max(${season.label})`,
      gameCount: sql<number>`count(distinct ${game.id})::int`,
    })
    .from(competition)
    .leftJoin(season, eq(season.competitionId, competition.id))
    .leftJoin(game, eq(game.competitionId, competition.id))
    .where(sportId ? eq(competition.sportId, sportId) : undefined)
    .groupBy(competition.id)
    .orderBy(desc(sql`count(distinct ${game.id})`), asc(competition.name));
  return rows;
}

export async function standingsForCompetition(slug: string) {
  const comp = await db()
    .select({
      id: competition.id,
      slug: competition.slug,
      name: competition.name,
      sportId: competition.sportId,
    })
    .from(competition)
    .where(eq(competition.slug, slug))
    .limit(1);
  const c = comp[0];
  if (!c) return null;

  // Dates are handled as text end to end so the driver never shifts them by a time zone.
  const latest = await db()
    .select({ asOf: sql<string>`max(${standing.asOf})::text`, seasonId: standing.seasonId })
    .from(standing)
    .innerJoin(season, eq(standing.seasonId, season.id))
    .where(eq(season.competitionId, c.id))
    .groupBy(standing.seasonId)
    .orderBy(desc(sql`max(${standing.asOf})`))
    .limit(1);
  const snap = latest[0];
  if (!snap) return { competition: c, asOf: null, seasonLabel: null, groups: [] };

  const rows = await db()
    .select({
      groupName: standing.groupName,
      rank: standing.rank,
      played: standing.played,
      wins: standing.wins,
      draws: standing.draws,
      losses: standing.losses,
      points: standing.points,
      pointsFor: standing.pointsFor,
      pointsAgainst: standing.pointsAgainst,
      stats: standing.stats,
      team: teamCols(team),
      seasonLabel: season.label,
    })
    .from(standing)
    .innerJoin(team, eq(standing.teamId, team.id))
    .innerJoin(season, eq(standing.seasonId, season.id))
    .where(and(eq(standing.seasonId, snap.seasonId), sql`${standing.asOf}::text = ${snap.asOf}`))
    .orderBy(asc(standing.groupName), asc(standing.rank), asc(team.name));

  const groups = new Map<string, typeof rows>();
  for (const r of rows) {
    const list = groups.get(r.groupName) ?? [];
    list.push(r);
    groups.set(r.groupName, list);
  }
  return {
    competition: c,
    asOf: snap.asOf,
    seasonLabel: rows[0]?.seasonLabel ?? null,
    groups: [...groups.entries()].map(([name, entries]) => ({ name, entries })),
  };
}

export async function searchTeams(q: string) {
  const text = q.trim();
  if (text.length < 2) return [];
  return db()
    .select({
      id: team.id,
      name: team.name,
      shortName: team.shortName,
      abbreviation: team.abbreviation,
      logoUrl: team.logoUrl,
      sportId: team.sportId,
    })
    .from(team)
    .where(
      or(
        ilike(team.name, `%${text}%`),
        ilike(team.location, `%${text}%`),
        ilike(team.abbreviation, `${text}%`),
      ),
    )
    .orderBy(asc(team.name))
    .limit(30);
}
