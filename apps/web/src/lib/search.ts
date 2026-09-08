/**
 * One search box that understands the domain.
 *
 *   "arsenal chelsea"        -> games between the two clubs (recent and upcoming)
 *   "seahawks"               -> the team, its next and last games
 *   "premier league table"   -> the standings page
 *   "nfl sunday"             -> NFL games this Sunday
 *   "tomorrow"               -> everything kicking off tomorrow
 *   "mahomes"                -> the player
 *   "elo" / "models"         -> the models page
 *   "parlay"                 -> the parlay of the day
 *   "status"                 -> data freshness and run history
 *
 * Pure functions over the same queries the pages use; no LLM involved.
 */

import type { AnyColumn } from "drizzle-orm";
import { and, asc, desc, eq, gte, ilike, inArray, lt, or, sql } from "drizzle-orm";
import { alias } from "drizzle-orm/pg-core";
import { competition, game, player, team } from "@gimme/db";
import { db } from "./db";
import { SPORTS_TZ, addDays, todayIso } from "./format";

const home = alias(team, "sh");
const away = alias(team, "sa");


/**
 * Case- and accent-insensitive contains, so "almiron" finds "Almirón" and
 * "sao paulo" finds "São Paulo". Names across these leagues carry accents that
 * nobody types, and a plain ILIKE misses every one of them.
 */
function loose(column: AnyColumn, text: string, position: "anywhere" | "start" = "anywhere") {
  const pattern = position === "start" ? `${text}%` : `%${text}%`;
  return sql`unaccent(${column}) ilike unaccent(${pattern})`;
}

export type SearchGame = {
  id: number;
  kickoff: string;
  status: string;
  statusDetail: string | null;
  homeScore: number | null;
  awayScore: number | null;
  competitionName: string;
  home: { id: number; name: string; shortName: string | null; abbreviation: string | null; logoUrl: string | null };
  away: { id: number; name: string; shortName: string | null; abbreviation: string | null; logoUrl: string | null };
};

export type SearchResult = {
  query: string;
  interpretation: string;
  games: SearchGame[];
  teams: { id: number; name: string; abbreviation: string | null; logoUrl: string | null; sportId: string }[];
  players: { id: number; fullName: string; position: string | null; headshotUrl: string | null; sportId: string }[];
  leagues: { slug: string; name: string; sportId: string }[];
  pages: { href: string; label: string; hint: string }[];
};

const LEAGUE_ALIASES: [RegExp, string][] = [
  [/\b(premier league|epl|prem)\b/, "eng.1"],
  [/\b(championship)\b/, "eng.2"],
  [/\b(la ?liga|laliga)\b/, "esp.1"],
  [/\b(serie a)\b/, "ita.1"],
  [/\b(bundesliga)\b/, "ger.1"],
  [/\b(ligue 1|ligue1)\b/, "fra.1"],
  [/\b(eredivisie)\b/, "ned.1"],
  [/\b(primeira liga|liga portugal)\b/, "por.1"],
  [/\b(mls|major league soccer)\b/, "usa.1"],
  [/\b(liga mx)\b/, "mex.1"],
  [/\b(champions league|ucl)\b/, "uefa.champions"],
  [/\b(europa league)\b/, "uefa.europa"],
  [/\b(libertadores)\b/, "conmebol.libertadores"],
  [/\b(world cup)\b/, "fifa.world"],
  [/\b(nfl)\b/, "nfl"],
  [/\b(college football|ncaa|ncaaf|cfb)\b/, "college-football"],
];

const WEEKDAYS = ["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"];

function normalize(q: string): string {
  return q
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9./\s-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function dateIntent(text: string): { day: string; label: string } | null {
  const today = todayIso();
  if (/\btoday\b|\btonight\b/.test(text)) return { day: today, label: "today" };
  if (/\btomorrow\b/.test(text)) return { day: addDays(today, 1), label: "tomorrow" };
  if (/\byesterday\b/.test(text)) return { day: addDays(today, -1), label: "yesterday" };
  const iso = text.match(/\b(\d{4}-\d{2}-\d{2})\b/);
  if (iso) return { day: iso[1], label: iso[1] };
  for (let i = 0; i < 7; i++) {
    if (new RegExp(`\\b${WEEKDAYS[i]}\\b`).test(text)) {
      const todayDow = new Date(`${today}T12:00:00Z`).getUTCDay();
      let delta = (i - todayDow + 7) % 7;
      if (/\blast\b/.test(text) && delta > 0) delta -= 7;
      if (/\blast\b/.test(text) && delta === 0) delta = -7;
      return { day: addDays(today, delta), label: WEEKDAYS[i] };
    }
  }
  if (/\bweekend\b/.test(text)) {
    const todayDow = new Date(`${today}T12:00:00Z`).getUTCDay();
    const delta = (6 - todayDow + 7) % 7;
    return { day: addDays(today, delta), label: "this weekend" };
  }
  return null;
}

const STOP = new Set([
  "vs", "v", "at", "and", "the", "game", "games", "match", "matches", "fixture", "fixtures", "score",
  "scores", "result", "results", "today", "tonight", "tomorrow", "yesterday", "this", "last", "next",
  "weekend", "week", "table", "standings", "standing", "league", "elo", "ratings", "rating", "models",
  "model", "prediction", "predictions", "odds", "line", "lines", "who", "wins", "win", "will", "beat",
  "parlay", "parlays", "acca", "accas", "accumulator", "multi", "leg", "legs", "status", "health",
  ...WEEKDAYS,
]);

type TeamLike = { id: unknown; name: unknown; shortName: unknown; abbreviation: unknown; logoUrl: unknown };
function teamCols<T extends TeamLike>(
  t: T,
): { id: T["id"]; name: T["name"]; shortName: T["shortName"]; abbreviation: T["abbreviation"]; logoUrl: T["logoUrl"] } {
  return { id: t.id, name: t.name, shortName: t.shortName, abbreviation: t.abbreviation, logoUrl: t.logoUrl };
}

function gameSelect() {
  return db()
    .select({
      id: game.id,
      kickoff: game.kickoff,
      status: game.status,
      statusDetail: game.statusDetail,
      homeScore: game.homeScore,
      awayScore: game.awayScore,
      competitionName: competition.name,
      home: teamCols(home),
      away: teamCols(away),
    })
    .from(game)
    .innerJoin(competition, eq(game.competitionId, competition.id))
    .innerJoin(home, eq(game.homeTeamId, home.id))
    .innerJoin(away, eq(game.awayTeamId, away.id));
}

type RawGame = Awaited<ReturnType<ReturnType<typeof gameSelect>["limit"]>>[number];

function toSearchGame(g: RawGame): SearchGame {
  return { ...g, kickoff: g.kickoff.toISOString() };
}

const kickoffDay = sql<string>`to_char(${game.kickoff} at time zone ${SPORTS_TZ}, 'YYYY-MM-DD')`;

export async function runSearch(rawQuery: string): Promise<SearchResult> {
  const query = rawQuery.trim();
  const text = normalize(query);
  const empty: SearchResult = { query, interpretation: "", games: [], teams: [], players: [], leagues: [], pages: [] };
  if (text.length < 2) return empty;

  const pages: SearchResult["pages"] = [];
  if (/\b(elo|ratings?|models?|back-?tests?)\b/.test(text)) {
    pages.push({ href: "/models", label: "Models", hint: "Back-tests and Elo ratings" });
  }
  if (/\b(parlays?|accas?|accumulators?|multis?|legs?)\b/.test(text)) {
    pages.push({
      href: "/parlay",
      label: "Parlay of the day",
      hint: "The likeliest call in each of today's games",
    });
  }
  if (/\b(status|health|uptime|freshness|stale|collector)\b/.test(text)) {
    pages.push({
      href: "/status",
      label: "System status",
      hint: "Data freshness and run history",
    });
  }

  // leagues: aliases first, then competition names
  const leagueSlugs = new Set<string>();
  for (const [re, slug] of LEAGUE_ALIASES) if (re.test(text)) leagueSlugs.add(slug);
  const allLeagues = await db()
    .select({ slug: competition.slug, name: competition.name, sportId: competition.sportId })
    .from(competition);
  const tokens = text.split(" ").filter((t) => t.length >= 2 && !STOP.has(t));
  for (const l of allLeagues) {
    const n = normalize(l.name);
    if (leagueSlugs.has(l.slug)) continue;
    if (text.includes(n) || (tokens.length && tokens.every((t) => n.includes(t)) && tokens.join(" ").length >= 5)) {
      leagueSlugs.add(l.slug);
    }
  }
  const leagues = allLeagues.filter((l) => leagueSlugs.has(l.slug));
  const wantsTable = /\b(table|standings?)\b/.test(text);
  for (const l of leagues) {
    pages.push({ href: `/standings/${l.slug}`, label: `${l.name} table`, hint: "Standings" });
  }

  // strip league words from team search tokens
  const leagueWords = new Set<string>();
  for (const l of leagues) for (const w of normalize(l.name).split(" ")) leagueWords.add(w);
  for (const [re] of LEAGUE_ALIASES) {
    const m = text.match(re);
    if (m) for (const w of m[0].split(" ")) leagueWords.add(w);
  }
  const teamTokens = tokens.filter((t) => !leagueWords.has(t));

  // teams: each token may name one team ("arsenal chelsea"), or all tokens one team ("man united")
  let teams: SearchResult["teams"] = [];
  const teamHits = new Map<number, SearchResult["teams"][number]>();
  if (teamTokens.length) {
    const whole = teamTokens.join(" ");
    const rows = await db()
      .select({ id: team.id, name: team.name, shortName: team.shortName, location: team.location, abbreviation: team.abbreviation, logoUrl: team.logoUrl, sportId: team.sportId })
      .from(team)
      .where(
        or(
          loose(team.name, whole),
          loose(team.location, whole),
          ...teamTokens.flatMap((t) => [
            loose(team.name, t),
            loose(team.shortName, t),
            loose(team.location, t, "start"),
            ilike(team.abbreviation, t),
          ]),
        ),
      )
      .limit(60);
    // popularity tie-break: how many games we hold for each candidate (Seattle Seahawks
    // over Wagner Seahawks)
    const counts = new Map<number, number>();
    if (rows.length) {
      const ids = rows.map((r) => r.id);
      const [asHome, asAway] = await Promise.all([
        db()
          .select({ id: game.homeTeamId, n: sql<number>`count(*)::int` })
          .from(game)
          .where(inArray(game.homeTeamId, ids))
          .groupBy(game.homeTeamId),
        db()
          .select({ id: game.awayTeamId, n: sql<number>`count(*)::int` })
          .from(game)
          .where(inArray(game.awayTeamId, ids))
          .groupBy(game.awayTeamId),
      ]);
      for (const p of [...asHome, ...asAway]) counts.set(p.id, (counts.get(p.id) ?? 0) + Number(p.n));
    }
    // rank: whole-phrase matches, then token matches by how much of the name they cover
    const scored = rows
      .map((r) => {
        const n = normalize(`${r.name} ${r.shortName ?? ""} ${r.location ?? ""} ${r.abbreviation ?? ""}`);
        let score = Math.log10(1 + (counts.get(r.id) ?? 0));
        if (normalize(r.name).includes(whole) || normalize(r.location ?? "").includes(whole)) score += 10;
        for (const t of teamTokens) {
          if (normalize(r.abbreviation ?? "") === t) score += 6;
          else if (normalize(r.name).split(" ").includes(t) || normalize(r.shortName ?? "").split(" ").includes(t)) score += 4;
          else if (n.includes(t)) score += 1;
        }
        if (leagues.length && !leagues.some((l) => l.sportId === r.sportId)) score -= 3;
        return { r, score };
      })
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score);
    for (const { r } of scored.slice(0, 8)) teamHits.set(r.id, { id: r.id, name: r.name, abbreviation: r.abbreviation, logoUrl: r.logoUrl, sportId: r.sportId });
    teams = [...teamHits.values()];
  }

  // players
  let players: SearchResult["players"] = [];
  if (teamTokens.length && teamTokens.join(" ").length >= 3) {
    const whole = teamTokens.join(" ");
    players = await db()
      .select({ id: player.id, fullName: player.fullName, position: player.position, headshotUrl: player.headshotUrl, sportId: player.sportId })
      .from(player)
      .where(or(loose(player.fullName, whole), ...(teamTokens.length === 1 ? [] : teamTokens.map((t) => loose(player.fullName, ` ${t}`)))))
      .orderBy(asc(player.fullName))
      .limit(6);
  }

  // games
  const date = dateIntent(text);
  let games: SearchGame[] = [];
  let interpretation = "";
  const now = new Date();
  // two distinct teams named by different tokens -> head to head
  const distinctByToken: number[] = [];
  for (const t of teamTokens) {
    const hit = teams.find((tm) => normalize(`${tm.name} ${tm.abbreviation ?? ""}`).split(" ").includes(t) || normalize(tm.name).includes(t));
    if (hit && !distinctByToken.includes(hit.id)) distinctByToken.push(hit.id);
  }
  if (distinctByToken.length >= 2) {
    const [a, b] = distinctByToken;
    const rows = await gameSelect()
      .where(or(and(eq(game.homeTeamId, a), eq(game.awayTeamId, b)), and(eq(game.homeTeamId, b), eq(game.awayTeamId, a))))
      .orderBy(desc(game.kickoff))
      .limit(8);
    games = rows.map(toSearchGame).sort((x, y) => Math.abs(Date.parse(x.kickoff) - now.getTime()) - Math.abs(Date.parse(y.kickoff) - now.getTime()));
    const na = teams.find((t) => t.id === a)?.name;
    const nb = teams.find((t) => t.id === b)?.name;
    interpretation = `Games between ${na} and ${nb}`;
  } else if (teams.length >= 1 && (teamTokens.length > 0)) {
    const id = teams[0].id;
    const filters = [or(eq(game.homeTeamId, id), eq(game.awayTeamId, id))];
    if (date) filters.push(eq(kickoffDay, date.day));
    const upcoming = await gameSelect().where(and(...filters, gte(game.kickoff, now))).orderBy(asc(game.kickoff)).limit(date ? 6 : 3);
    const recent = date ? [] : await gameSelect().where(and(...filters, lt(game.kickoff, now))).orderBy(desc(game.kickoff)).limit(3);
    games = [...upcoming.map(toSearchGame), ...recent.map(toSearchGame)];
    interpretation = date ? `${teams[0].name} ${date.label}` : `${teams[0].name}: next and recent games`;
  } else if (date) {
    const filters = [eq(kickoffDay, date.day)];
    if (leagues.length) filters.push(inArray(competition.slug, leagues.map((l) => l.slug)));
    const rows = await gameSelect().where(and(...filters)).orderBy(asc(game.kickoff)).limit(14);
    games = rows.map(toSearchGame);
    interpretation = `${leagues.length ? leagues.map((l) => l.name).join(", ") : "All games"} ${date.label}`;
    pages.unshift({ href: `${leagues.length === 1 && leagues[0].slug === "nfl" ? "/nfl" : leagues.length === 1 && leagues[0].slug === "college-football" ? "/cfb" : leagues.length && leagues[0].sportId === "soccer" ? "/soccer" : "/"}?date=${date.day}`, label: `All games ${date.label}`, hint: date.day });
  } else if (leagues.length && !wantsTable) {
    const rows = await gameSelect()
      .where(and(inArray(competition.slug, leagues.map((l) => l.slug)), gte(game.kickoff, new Date(now.getTime() - 86_400_000 * 2))))
      .orderBy(asc(game.kickoff))
      .limit(10);
    games = rows.map(toSearchGame);
    interpretation = `${leagues.map((l) => l.name).join(", ")}: recent and upcoming`;
  } else if (wantsTable && leagues.length) {
    interpretation = `${leagues[0].name} standings`;
  } else if (teams.length === 0 && players.length) {
    interpretation = "Players";
  }

  return { query, interpretation, games, teams, players, leagues, pages };
}
