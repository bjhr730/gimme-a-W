import { and, asc, desc, eq, gte, ilike, lt, lte, or, sql } from "drizzle-orm";
import { alias } from "drizzle-orm/pg-core";
import {
  competition,
  game,
  modelRun,
  odds,
  pick,
  player,
  playerGameStat,
  playerStatus,
  prediction,
  rating,
  roster,
  season,
  standing,
  team,
  teamForm,
  teamGameStat,
  venue,
} from "@gimme/db";
import { inArray } from "drizzle-orm";
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
        isClosing: odds.isClosing,
      })
      .from(odds)
      .where(eq(odds.gameId, id))
      .orderBy(desc(odds.capturedAt)),
  ]);

  // Latest line per bookmaker/market/selection, then one bookmaker for the page:
  // the first in preference order that has any line for this game.
  const latest = new Map<string, (typeof oddsRows)[number]>();
  for (const o of oddsRows) {
    const key = `${o.bookmaker}|${o.market}|${o.selection}`;
    if (!latest.has(key)) latest.set(key, o);
  }
  const all = [...latest.values()];
  const preference = ["DraftKings", "Pinnacle", "Bet365", "consensus"];
  const books = [...new Set(all.map((o) => o.bookmaker))].sort(
    (a, b) => (preference.indexOf(a) + 99) % 99 - ((preference.indexOf(b) + 99) % 99),
  );
  const chosen = books[0];

  return {
    ...g,
    homeStats: (stats.find((s) => s.teamId === g.home.id)?.stats ?? {}) as Record<string, unknown>,
    awayStats: (stats.find((s) => s.teamId === g.away.id)?.stats ?? {}) as Record<string, unknown>,
    odds: chosen ? all.filter((o) => o.bookmaker === chosen) : [],
    otherBooks: books.slice(1),
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

// ------------------------------------------------------------ phase 3

const playerCols = {
  id: player.id,
  fullName: player.fullName,
  shortName: player.shortName,
  position: player.position,
  headshotUrl: player.headshotUrl,
};

/** Per-player box score rows for one game, with the team they played for. */
export async function gamePlayers(gameId: number) {
  return db()
    .select({ teamId: playerGameStat.teamId, stats: playerGameStat.stats, player: playerCols })
    .from(playerGameStat)
    .innerJoin(player, eq(playerGameStat.playerId, player.id))
    .where(eq(playerGameStat.gameId, gameId))
    .orderBy(asc(player.fullName));
}

/** Third-party picks (ESPN FPI today) for one game. */
export async function gamePicks(gameId: number) {
  return db()
    .select({
      author: pick.author,
      winProbability: pick.winProbability,
      spread: pick.spread,
      total: pick.total,
      publishedAt: pick.publishedAt,
      pickTeam: { id: team.id, name: team.name, shortName: team.shortName },
    })
    .from(pick)
    .leftJoin(team, eq(pick.pickTeamId, team.id))
    .where(eq(pick.gameId, gameId))
    .orderBy(desc(pick.publishedAt));
}

/** Latest form, Elo and roster for a team. */
export async function teamExtras(teamId: number) {
  const [form, elo, rosterRows] = await Promise.all([
    db()
      .select({
        form: teamForm.form,
        ppg: teamForm.ppg,
        marginPerGame: teamForm.marginPerGame,
        restDays: teamForm.restDays,
        stats: teamForm.stats,
        asOf: sql<string>`${teamForm.asOf}::text`,
        seasonLabel: season.label,
        competitionName: competition.name,
        competitionSlug: competition.slug,
      })
      .from(teamForm)
      .innerJoin(season, eq(teamForm.seasonId, season.id))
      .innerJoin(competition, eq(season.competitionId, competition.id))
      .where(eq(teamForm.teamId, teamId))
      .orderBy(desc(teamForm.asOf), desc(season.year))
      .limit(3),
    db()
      .select({ value: rating.value, asOf: sql<string>`${rating.asOf}::text` })
      .from(rating)
      .where(
        and(eq(rating.subjectType, "team"), eq(rating.subjectId, teamId), eq(rating.kind, "elo")),
      )
      .orderBy(desc(rating.asOf))
      .limit(1),
    db()
      .select({
        jersey: roster.jerseyNumber,
        position: roster.position,
        seasonId: roster.seasonId,
        player: playerCols,
      })
      .from(roster)
      .innerJoin(player, eq(roster.playerId, player.id))
      .where(eq(roster.teamId, teamId))
      .orderBy(desc(roster.seasonId), asc(roster.position), asc(player.fullName)),
  ]);
  // keep only the most recent season's roster, one row per competition for form
  const latestSeason = rosterRows[0]?.seasonId;
  const seen = new Set<string>();
  return {
    form: form.filter((f) => {
      if (seen.has(f.competitionSlug)) return false;
      seen.add(f.competitionSlug);
      return true;
    }),
    elo: elo[0] ?? null,
    roster: rosterRows.filter((r) => r.seasonId === latestSeason),
  };
}

/** Elo rank of a team among its sport, 1 = best. */
export async function eloRank(teamId: number, sportId: string) {
  const rows = await db()
    .select({ subjectId: rating.subjectId, value: rating.value })
    .from(rating)
    .innerJoin(team, eq(rating.subjectId, team.id))
    .where(
      and(
        eq(rating.subjectType, "team"),
        eq(rating.kind, "elo"),
        eq(team.sportId, sportId),
        eq(
          rating.asOf,
          sql`(select max(as_of) from rating r2 where r2.kind = 'elo' and r2.subject_type = 'team')`,
        ),
      ),
    )
    .orderBy(desc(rating.value));
  const index = rows.findIndex((r) => r.subjectId === teamId);
  return index === -1 ? null : { rank: index + 1, of: rows.length };
}

export async function playerById(id: number) {
  const rows = await db().select().from(player).where(eq(player.id, id)).limit(1);
  const p = rows[0];
  if (!p) return null;
  const [teams, log] = await Promise.all([
    db()
      .select({
        team: { id: team.id, name: team.name, shortName: team.shortName, logoUrl: team.logoUrl },
        jersey: roster.jerseyNumber,
        position: roster.position,
        seasonLabel: season.label,
        seasonId: roster.seasonId,
      })
      .from(roster)
      .innerJoin(team, eq(roster.teamId, team.id))
      .innerJoin(season, eq(roster.seasonId, season.id))
      .where(eq(roster.playerId, id))
      .orderBy(desc(season.year))
      .limit(3),
    db()
      .select({
        ...gameCols,
        teamId: playerGameStat.teamId,
        stats: playerGameStat.stats,
      })
      .from(playerGameStat)
      .innerJoin(game, eq(playerGameStat.gameId, game.id))
      .innerJoin(competition, eq(game.competitionId, competition.id))
      .innerJoin(home, eq(game.homeTeamId, home.id))
      .innerJoin(away, eq(game.awayTeamId, away.id))
      .where(eq(playerGameStat.playerId, id))
      .orderBy(desc(game.kickoff))
      .limit(25),
  ]);
  return { player: p, teams, log };
}

// ------------------------------------------------------ parlay of the day

export type ParlayLeg = {
  gameId: number;
  market: string;
  selection: string;
  subjectType: string;
  subjectId: number;
  probability: number;
  line: string | null;
  kickoff: Date;
  competitionName: string;
  competitionSlug: string;
  homeName: string;
  homeShort: string | null;
  awayName: string;
  awayShort: string | null;
  playerName: string | null;
  playerPosition: string | null;
  subjectTeamName: string | null;
  subjectTeamShort: string | null;
};

// A leg the model puts above this is not a real market: it adds nothing to a
// parlay and says more about model confidence than about the game.
const PARLAY_CEILING = 0.95;

/**
 * The most likely call in each of the day's games, best first.
 *
 * One leg per game on purpose. Two legs from the same match move together, so
 * multiplying them would overstate the parlay's chance of landing.
 */
export async function parlayLegs(day: string, limit = 20): Promise<ParlayLeg[]> {
  const rows = await db().execute(sql`
    with latest_runs as (
      select distinct on (model_name, coalesce(notes, '')) id
      from model_run
      order by model_name, coalesce(notes, ''), id desc
    ),
    legs as (
      select distinct on (p.game_id)
        p.game_id, p.market, p.selection, p.subject_type, p.subject_id,
        p.probability, p.line, g.kickoff,
        c.name as competition_name, c.slug as competition_slug,
        h.name as home_name, h.short_name as home_short,
        a.name as away_name, a.short_name as away_short,
        pl.full_name as player_name, pl.position as player_position,
        st.name as subject_team_name, st.short_name as subject_team_short
      from prediction p
      join latest_runs lr on lr.id = p.model_run_id
      join game g on g.id = p.game_id
      join competition c on c.id = g.competition_id
      join team h on h.id = g.home_team_id
      join team a on a.id = g.away_team_id
      left join player pl on p.subject_type = 'player' and pl.id = p.subject_id
      left join team st on p.subject_type = 'team' and st.id = p.subject_id
      where p.probability is not null
        and p.probability <= ${PARLAY_CEILING}
        and g.status = 'scheduled'
        and g.kickoff > now()
        and to_char(g.kickoff at time zone ${SPORTS_TZ}, 'YYYY-MM-DD') = ${day}
      order by p.game_id, p.probability desc
    )
    select * from legs order by probability desc limit ${limit}
  `);
  return (rows as unknown as Record<string, unknown>[]).map((r) => ({
    gameId: Number(r.game_id),
    market: String(r.market),
    selection: String(r.selection ?? ""),
    subjectType: String(r.subject_type),
    subjectId: Number(r.subject_id),
    probability: Number(r.probability),
    line: r.line === null || r.line === undefined ? null : String(r.line),
    kickoff: new Date(r.kickoff as string),
    competitionName: String(r.competition_name),
    competitionSlug: String(r.competition_slug),
    homeName: String(r.home_name),
    homeShort: (r.home_short as string) ?? null,
    awayName: String(r.away_name),
    awayShort: (r.away_short as string) ?? null,
    playerName: (r.player_name as string) ?? null,
    playerPosition: (r.player_position as string) ?? null,
    subjectTeamName: (r.subject_team_name as string) ?? null,
    subjectTeamShort: (r.subject_team_short as string) ?? null,
  }));
}

/**
 * Today's legs when today still has games to come, otherwise the next day that
 * does. Returns the day it settled on so the page can say which one it means.
 */
export async function parlayForToday(
  startDay: string,
  limit = 20,
): Promise<{ day: string; legs: ParlayLeg[] }> {
  let day = startDay;
  for (let i = 0; i < 4; i += 1) {
    const legs = await parlayLegs(day, limit);
    if (legs.length >= 2) return { day, legs };
    const next = new Date(`${day}T12:00:00Z`);
    next.setUTCDate(next.getUTCDate() + 1);
    day = next.toISOString().slice(0, 10);
  }
  return { day: startDay, legs: [] };
}

// ------------------------------------------------------- injury reports

export type InjuryRow = {
  playerId: number;
  playerName: string;
  position: string | null;
  headshotUrl: string | null;
  teamId: number | null;
  availability: "available" | "questionable" | "doubtful" | "out";
  status: string;
  injuryType: string | null;
  bodyLocation: string | null;
  detail: string | null;
  returnDate: string | null;
  comment: string | null;
  reportedAt: Date | null;
};

// Worst news first: a player who is out matters more than one who is a doubt.
const injurySeverity = sql`case ${playerStatus.availability}
  when 'out' then 0 when 'doubtful' then 1 when 'questionable' then 2 else 3 end`;

const injuryCols = {
  playerId: playerStatus.playerId,
  playerName: player.fullName,
  position: player.position,
  headshotUrl: player.headshotUrl,
  teamId: playerStatus.teamId,
  availability: playerStatus.availability,
  status: playerStatus.status,
  injuryType: playerStatus.injuryType,
  bodyLocation: playerStatus.bodyLocation,
  detail: playerStatus.detail,
  returnDate: sql<string | null>`${playerStatus.returnDate}::text`,
  comment: playerStatus.comment,
  reportedAt: playerStatus.reportedAt,
};

/** Everyone on either team who is carrying a report, worst news first. */
export async function gameInjuries(teamIds: number[]): Promise<InjuryRow[]> {
  if (teamIds.length === 0) return [];
  const rows = await db()
    .select(injuryCols)
    .from(playerStatus)
    .innerJoin(player, eq(playerStatus.playerId, player.id))
    .where(
      and(
        inArray(playerStatus.teamId, teamIds),
        sql`${playerStatus.availability} <> 'available'`,
      ),
    )
    .orderBy(injurySeverity, asc(player.fullName));
  return rows as InjuryRow[];
}

/** The report for one team, for the team page. */
export async function teamInjuries(teamId: number): Promise<InjuryRow[]> {
  return gameInjuries([teamId]);
}

/** The report for one player, for the player page. */
export async function playerInjury(playerId: number): Promise<InjuryRow | null> {
  const rows = await db()
    .select(injuryCols)
    .from(playerStatus)
    .innerJoin(player, eq(playerStatus.playerId, player.id))
    .where(eq(playerStatus.playerId, playerId))
    .orderBy(injurySeverity)
    .limit(1);
  return (rows[0] as InjuryRow) ?? null;
}

/** Status for a set of players, keyed by player id, for badges on market tables. */
export async function statusesForPlayers(
  playerIds: number[],
): Promise<Map<number, InjuryRow>> {
  const out = new Map<number, InjuryRow>();
  if (playerIds.length === 0) return out;
  const rows = await db()
    .select(injuryCols)
    .from(playerStatus)
    .innerJoin(player, eq(playerStatus.playerId, player.id))
    .where(inArray(playerStatus.playerId, playerIds))
    .orderBy(injurySeverity);
  for (const r of rows as InjuryRow[]) if (!out.has(r.playerId)) out.set(r.playerId, r);
  return out;
}

// ------------------------------------------------------------ phase 4

export type PredictionRow = {
  market: string;
  selection: string;
  probability: string | null;
  mean: string | null;
  line: string | null;
  quantiles: unknown;
  explanation: unknown;
  modelName: string;
  modelVersion: string;
  createdAt: Date;
};

/** Our latest model output for one game: rows from the most recent model run per market. */
export async function gamePredictions(gameId: number): Promise<PredictionRow[]> {
  const rows = await db()
    .select({
      market: prediction.market,
      selection: prediction.selection,
      probability: prediction.probability,
      mean: prediction.mean,
      line: prediction.line,
      quantiles: prediction.quantiles,
      explanation: prediction.explanation,
      modelName: modelRun.modelName,
      modelVersion: modelRun.modelVersion,
      createdAt: prediction.createdAt,
      runId: modelRun.id,
    })
    .from(prediction)
    .innerJoin(modelRun, eq(prediction.modelRunId, modelRun.id))
    // game-level markets only: the player-props runs share the game id but must
    // not be mistaken for the latest game model
    .where(and(eq(prediction.gameId, gameId), eq(prediction.subjectType, "game")))
    .orderBy(desc(modelRun.id));
  const latestRun = rows[0]?.runId;
  return rows.filter((r) => r.runId === latestRun);
}

export type PropRow = {
  market: string;
  subjectType: string;
  subjectId: number;
  selection: string;
  probability: string | null;
  mean: string | null;
  line: string | null;
  quantiles: unknown;
  explanation: unknown;
  playerName: string | null;
  playerPosition: string | null;
  teamId: number | null; // team the player row belongs to (from the run's explanation) or team subject
};

/** Player and team market rows for one game from the latest props run. */
export async function gameProps(gameId: number): Promise<PropRow[]> {
  const rows = await db()
    .select({
      market: prediction.market,
      subjectType: prediction.subjectType,
      subjectId: prediction.subjectId,
      selection: prediction.selection,
      probability: prediction.probability,
      mean: prediction.mean,
      line: prediction.line,
      quantiles: prediction.quantiles,
      explanation: prediction.explanation,
      runId: prediction.modelRunId,
      modelName: modelRun.modelName,
      playerName: player.fullName,
      playerPosition: player.position,
    })
    .from(prediction)
    .innerJoin(modelRun, eq(prediction.modelRunId, modelRun.id))
    .leftJoin(player, and(eq(prediction.subjectType, "player"), eq(prediction.subjectId, player.id)))
    .where(
      and(
        eq(prediction.gameId, gameId),
        inArray(modelRun.modelName, ["football-player-props", "soccer-props"]),
      ),
    )
    .orderBy(desc(prediction.modelRunId));
  const latestRun = rows[0]?.runId;
  const latest = rows.filter((r) => r.runId === latestRun);
  if (latest.length === 0) return [];
  // which team each player belongs to: from roster of the two teams in this game
  const playerIds = [...new Set(latest.filter((r) => r.subjectType === "player").map((r) => r.subjectId))];
  const teamOf = new Map<number, number>();
  if (playerIds.length) {
    const g = await db()
      .select({ home: game.homeTeamId, away: game.awayTeamId })
      .from(game)
      .where(eq(game.id, gameId))
      .limit(1);
    const teams = g[0] ? [g[0].home, g[0].away] : [];
    const memberships = await db()
      .select({ playerId: roster.playerId, teamId: roster.teamId, seasonId: roster.seasonId })
      .from(roster)
      .where(and(inArray(roster.playerId, playerIds), inArray(roster.teamId, teams)))
      .orderBy(desc(roster.seasonId));
    for (const m of memberships) if (!teamOf.has(m.playerId)) teamOf.set(m.playerId, m.teamId);
  }
  return latest.map((r) => ({
    market: r.market,
    subjectType: r.subjectType,
    subjectId: r.subjectId,
    selection: r.selection,
    probability: r.probability,
    mean: r.mean,
    line: r.line,
    quantiles: r.quantiles,
    explanation: r.explanation,
    playerName: r.playerName,
    playerPosition: r.playerPosition,
    teamId: r.subjectType === "team" ? r.subjectId : (teamOf.get(r.subjectId) ?? null),
  }));
}

/** Favored side per game for score cards: {gameId -> {selection, probability}}. */
export async function winProbabilities(gameIds: number[]) {
  if (gameIds.length === 0) return new Map<number, { selection: string; probability: number }>();
  const rows = await db()
    .select({
      gameId: prediction.gameId,
      market: prediction.market,
      selection: prediction.selection,
      probability: prediction.probability,
      runId: prediction.modelRunId,
    })
    .from(prediction)
    .where(
      and(
        inArray(prediction.gameId, gameIds),
        inArray(prediction.market, ["win_probability", "match_result"]),
      ),
    )
    .orderBy(desc(prediction.modelRunId));
  const out = new Map<number, { selection: string; probability: number }>();
  const runFor = new Map<number, number>();
  for (const r of rows) {
    const run = runFor.get(r.gameId) ?? r.runId;
    runFor.set(r.gameId, run);
    if (r.runId !== run || r.probability === null) continue;
    const p = Number(r.probability);
    const current = out.get(r.gameId);
    if (!current || p > current.probability) out.set(r.gameId, { selection: r.selection, probability: p });
  }
  return out;
}

/** Latest finished model runs (one per model + competition) with their metrics. */
export async function modelRuns() {
  const rows = await db()
    .select({
      id: modelRun.id,
      modelName: modelRun.modelName,
      modelVersion: modelRun.modelVersion,
      sportId: modelRun.sportId,
      startedAt: modelRun.startedAt,
      status: modelRun.status,
      snapshotCount: modelRun.snapshotCount,
      metrics: modelRun.metrics,
      notes: modelRun.notes,
    })
    .from(modelRun)
    .where(eq(modelRun.status, "succeeded"))
    .orderBy(desc(modelRun.id))
    .limit(200);
  const seen = new Set<string>();
  return rows.filter((r) => {
    const m = (r.metrics ?? {}) as { competition?: string; seasons?: unknown };
    const kind = m.seasons ? "backtest" : "run";
    const key = `${r.modelName}|${m.competition ?? r.notes ?? ""}|${kind}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ------------------------------------------------------------ phase 6

/** Latest live scorecard (predictions graded against results). */
export async function latestScorecard() {
  const rows = await db()
    .select({ id: modelRun.id, metrics: modelRun.metrics, startedAt: modelRun.startedAt })
    .from(modelRun)
    .where(and(eq(modelRun.modelName, "scorecard"), eq(modelRun.status, "succeeded")))
    .orderBy(desc(modelRun.id))
    .limit(1);
  return rows[0] ?? null;
}

export async function statusSnapshot() {
  // raw sql params must be strings for the postgres-js driver: pass ISO timestamps
  const now = new Date().toISOString();
  const week = new Date(Date.now() + 7 * 86_400_000).toISOString();
  const [collectorRuns, runs, freshness, lastGame, lastPred, gameCount, predCount] = await Promise.all([
    db().execute(sql`
      SELECT r.id, s.slug AS source, r.adapter, r.status, r.rows_written, r.started_at, r.error
      FROM collector_run r JOIN source s ON s.id = r.source_id
      ORDER BY r.id DESC LIMIT 15`),
    db()
      .select({
        id: modelRun.id,
        modelName: modelRun.modelName,
        modelVersion: modelRun.modelVersion,
        notes: modelRun.notes,
        snapshotCount: modelRun.snapshotCount,
        startedAt: modelRun.startedAt,
      })
      .from(modelRun)
      .orderBy(desc(modelRun.id))
      .limit(12),
    db().execute(sql`
      SELECT c.slug, c.name,
             count(g.id)::int AS games,
             max(g.kickoff) FILTER (WHERE g.status = 'final') AS last_final,
             count(g.id) FILTER (WHERE g.status = 'scheduled' AND g.kickoff BETWEEN ${now}::timestamptz AND ${week}::timestamptz)::int AS upcoming,
             count(g.id) FILTER (WHERE g.status = 'scheduled' AND g.kickoff BETWEEN ${now}::timestamptz AND ${week}::timestamptz
                 AND EXISTS (SELECT 1 FROM prediction p WHERE p.game_id = g.id
                             AND p.market IN ('win_probability', 'match_result')))::int AS predicted
      FROM competition c LEFT JOIN game g ON g.competition_id = c.id
      GROUP BY c.id ORDER BY games DESC`),
    db().select({ v: sql<Date | null>`max(${game.updatedAt})` }).from(game),
    db().select({ v: sql<Date | null>`max(${prediction.createdAt})` }).from(prediction),
    db().select({ v: sql<number>`count(*)::int` }).from(game),
    db().select({ v: sql<number>`count(*)::int` }).from(prediction),
  ]);
  type CR = { id: number; source: string; adapter: string; status: string; rows_written: number; started_at: Date; error: string | null };
  type FR = { slug: string; name: string; games: number; last_final: Date | null; upcoming: number; predicted: number };
  return {
    collectorRuns: (collectorRuns as unknown as CR[]).map((r) => ({
      id: r.id,
      source: r.source,
      adapter: r.adapter,
      status: r.status,
      rowsWritten: r.rows_written,
      startedAt: new Date(r.started_at),
      error: r.error,
    })),
    modelRuns: runs,
    freshness: (freshness as unknown as FR[]).map((f) => ({
      slug: f.slug,
      name: f.name,
      games: f.games,
      lastFinal: f.last_final ? new Date(f.last_final) : null,
      upcoming: f.upcoming,
      predicted: f.predicted,
    })),
    lastGameUpdate: lastGame[0]?.v ? new Date(lastGame[0].v) : null,
    lastPrediction: lastPred[0]?.v ? new Date(lastPred[0].v) : null,
    counts: { games: gameCount[0]?.v ?? 0, predictions: predCount[0]?.v ?? 0 },
  };
}

export async function searchPlayers(q: string) {
  const text = q.trim();
  if (text.length < 2) return [];
  return db()
    .select({ ...playerCols, sportId: player.sportId })
    .from(player)
    .where(ilike(player.fullName, `%${text}%`))
    .orderBy(asc(player.fullName))
    .limit(20);
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
