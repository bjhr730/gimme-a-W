/**
 * gimme-a-W database schema. Single source of truth: the Python collectors
 * write to these tables with plain SQL, so column names here are contract.
 *
 * Conventions
 * - snake_case in the database, camelCase in TypeScript.
 * - Internal integer ids everywhere; source ids live in `external_id`.
 * - Every collected row carries provenance (`source_id`, `collector_run_id`)
 *   and every prediction carries `model_run_id`.
 * - Sport-specific numbers go in `stats` JSONB keyed by a per-sport dictionary.
 */
import { sql } from "drizzle-orm";
import {
  boolean,
  date,
  index,
  integer,
  jsonb,
  numeric,
  pgEnum,
  pgTable,
  serial,
  text,
  timestamp,
  uniqueIndex,
} from "drizzle-orm/pg-core";

// ---------------------------------------------------------------- enums

export const gameStatus = pgEnum("game_status", [
  "scheduled",
  "in_progress",
  "final",
  "postponed",
  "canceled",
  "suspended",
]);

export const subjectType = pgEnum("subject_type", ["game", "team", "player"]);

export const entityType = pgEnum("entity_type", [
  "competition",
  "season",
  "team",
  "player",
  "game",
  "venue",
]);

export const runStatus = pgEnum("run_status", ["running", "succeeded", "failed"]);

// ------------------------------------------------------------- helpers

const tz = (name: string) => timestamp(name, { withTimezone: true, mode: "date" });
const createdAt = () => tz("created_at").notNull().defaultNow();
const updatedAt = () => tz("updated_at").notNull().defaultNow();
const json = (name: string) => jsonb(name).notNull().default(sql`'{}'::jsonb`);

// ------------------------------------------------------------ reference

export const sport = pgTable("sport", {
  id: text("id").primaryKey(), // 'soccer' | 'american_football'
  name: text("name").notNull(),
});

export const source = pgTable("source", {
  id: serial("id").primaryKey(),
  slug: text("slug").notNull().unique(), // 'espn', 'fbref', 'cfbd', ...
  name: text("name").notNull(),
  baseUrl: text("base_url"),
  rateLimitPerMin: integer("rate_limit_per_min"),
  notes: text("notes"),
});

export const competition = pgTable(
  "competition",
  {
    id: serial("id").primaryKey(),
    sportId: text("sport_id")
      .notNull()
      .references(() => sport.id),
    slug: text("slug").notNull().unique(), // 'eng.1', 'nfl', 'college-football'
    name: text("name").notNull(),
    shortName: text("short_name"),
    country: text("country"),
    level: text("level"), // 'club', 'international', 'college'
    isActive: boolean("is_active").notNull().default(true),
  },
  (t) => [index("competition_sport_idx").on(t.sportId)],
);

export const season = pgTable(
  "season",
  {
    id: serial("id").primaryKey(),
    competitionId: integer("competition_id")
      .notNull()
      .references(() => competition.id),
    label: text("label").notNull(), // '2025-26' or '2026'
    year: integer("year").notNull(), // ESPN season year
    startDate: date("start_date"),
    endDate: date("end_date"),
  },
  (t) => [uniqueIndex("season_competition_label_uq").on(t.competitionId, t.label)],
);

export const venue = pgTable("venue", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  city: text("city"),
  state: text("state"),
  country: text("country"),
  indoor: boolean("indoor"),
  capacity: integer("capacity"),
});

// ---------------------------------------------------------------- teams

export const team = pgTable(
  "team",
  {
    id: serial("id").primaryKey(),
    sportId: text("sport_id")
      .notNull()
      .references(() => sport.id),
    name: text("name").notNull(), // display name: 'Seattle Seahawks', 'Arsenal'
    shortName: text("short_name"),
    abbreviation: text("abbreviation"),
    location: text("location"),
    logoUrl: text("logo_url"),
    color: text("color"),
    altColor: text("alt_color"),
    isActive: boolean("is_active").notNull().default(true),
    updatedAt: updatedAt(),
  },
  (t) => [index("team_sport_name_idx").on(t.sportId, t.name)],
);

export const teamSeason = pgTable(
  "team_season",
  {
    id: serial("id").primaryKey(),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    seasonId: integer("season_id")
      .notNull()
      .references(() => season.id),
    groupName: text("group_name"), // conference / division / group
  },
  (t) => [uniqueIndex("team_season_uq").on(t.teamId, t.seasonId)],
);

export const player = pgTable(
  "player",
  {
    id: serial("id").primaryKey(),
    sportId: text("sport_id")
      .notNull()
      .references(() => sport.id),
    fullName: text("full_name").notNull(),
    shortName: text("short_name"),
    position: text("position"),
    birthDate: date("birth_date"),
    nationality: text("nationality"),
    heightCm: integer("height_cm"),
    weightKg: integer("weight_kg"),
    headshotUrl: text("headshot_url"),
    isActive: boolean("is_active").notNull().default(true),
    updatedAt: updatedAt(),
  },
  (t) => [index("player_sport_name_idx").on(t.sportId, t.fullName)],
);

export const roster = pgTable(
  "roster",
  {
    id: serial("id").primaryKey(),
    playerId: integer("player_id")
      .notNull()
      .references(() => player.id),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    seasonId: integer("season_id")
      .notNull()
      .references(() => season.id),
    jerseyNumber: text("jersey_number"),
    position: text("position"),
  },
  (t) => [uniqueIndex("roster_uq").on(t.playerId, t.teamId, t.seasonId)],
);

// ---------------------------------------------------------------- games

export const game = pgTable(
  "game",
  {
    id: serial("id").primaryKey(),
    competitionId: integer("competition_id")
      .notNull()
      .references(() => competition.id),
    seasonId: integer("season_id")
      .notNull()
      .references(() => season.id),
    kickoff: tz("kickoff").notNull(),
    homeTeamId: integer("home_team_id")
      .notNull()
      .references(() => team.id),
    awayTeamId: integer("away_team_id")
      .notNull()
      .references(() => team.id),
    venueId: integer("venue_id").references(() => venue.id),
    homeScore: integer("home_score"),
    awayScore: integer("away_score"),
    status: gameStatus("status").notNull().default("scheduled"),
    statusDetail: text("status_detail"),
    period: integer("period"),
    clock: text("clock"),
    week: integer("week"),
    round: text("round"),
    neutralSite: boolean("neutral_site").notNull().default(false),
    conferenceGame: boolean("conference_game"),
    attendance: integer("attendance"),
    weather: json("weather"),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("game_natural_uq").on(t.seasonId, t.kickoff, t.homeTeamId, t.awayTeamId),
    index("game_kickoff_idx").on(t.kickoff),
    index("game_season_idx").on(t.seasonId),
    index("game_home_idx").on(t.homeTeamId),
    index("game_away_idx").on(t.awayTeamId),
  ],
);

export const teamGameStat = pgTable(
  "team_game_stat",
  {
    id: serial("id").primaryKey(),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    stats: json("stats"),
    updatedAt: updatedAt(),
  },
  (t) => [uniqueIndex("team_game_stat_uq").on(t.gameId, t.teamId)],
);

export const playerGameStat = pgTable(
  "player_game_stat",
  {
    id: serial("id").primaryKey(),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    playerId: integer("player_id")
      .notNull()
      .references(() => player.id),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    stats: json("stats"),
    updatedAt: updatedAt(),
  },
  (t) => [
    uniqueIndex("player_game_stat_uq").on(t.gameId, t.playerId),
    index("player_game_stat_player_idx").on(t.playerId),
  ],
);

// ---------------------------------------------------------- derived data

export const standing = pgTable(
  "standing",
  {
    id: serial("id").primaryKey(),
    seasonId: integer("season_id")
      .notNull()
      .references(() => season.id),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    asOf: date("as_of").notNull(),
    groupName: text("group_name").notNull().default(""),
    rank: integer("rank"),
    played: integer("played"),
    wins: integer("wins"),
    draws: integer("draws"),
    losses: integer("losses"),
    points: integer("points"),
    pointsFor: integer("points_for"),
    pointsAgainst: integer("points_against"),
    stats: json("stats"),
  },
  (t) => [uniqueIndex("standing_uq").on(t.seasonId, t.teamId, t.asOf, t.groupName)],
);

export const teamForm = pgTable(
  "team_form",
  {
    id: serial("id").primaryKey(),
    teamId: integer("team_id")
      .notNull()
      .references(() => team.id),
    seasonId: integer("season_id")
      .notNull()
      .references(() => season.id),
    asOf: date("as_of").notNull(),
    lastN: integer("last_n").notNull().default(5),
    form: text("form"), // 'WWDLW'
    ppg: numeric("ppg", { precision: 5, scale: 3 }),
    marginPerGame: numeric("margin_per_game", { precision: 7, scale: 3 }),
    xgDiffPerGame: numeric("xg_diff_per_game", { precision: 7, scale: 3 }),
    restDays: integer("rest_days"),
    stats: json("stats"),
  },
  (t) => [uniqueIndex("team_form_uq").on(t.teamId, t.seasonId, t.asOf, t.lastN)],
);

export const rating = pgTable(
  "rating",
  {
    id: serial("id").primaryKey(),
    subjectType: subjectType("subject_type").notNull(),
    subjectId: integer("subject_id").notNull(),
    seasonId: integer("season_id").references(() => season.id),
    asOf: date("as_of").notNull(),
    kind: text("kind").notNull(), // 'elo', 'attack', 'defense', 'xg90'
    value: numeric("value", { precision: 12, scale: 4 }).notNull(),
    modelVersion: text("model_version").notNull().default(""),
  },
  (t) => [
    uniqueIndex("rating_uq").on(t.subjectType, t.subjectId, t.asOf, t.kind, t.modelVersion),
    index("rating_subject_idx").on(t.subjectType, t.subjectId, t.kind),
  ],
);

export const odds = pgTable(
  "odds",
  {
    id: serial("id").primaryKey(),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    sourceId: integer("source_id")
      .notNull()
      .references(() => source.id),
    bookmaker: text("bookmaker").notNull(),
    market: text("market").notNull(), // 'h2h', 'spread', 'total', ...
    selection: text("selection").notNull(), // 'home', 'away', 'draw', 'over', 'under'
    line: numeric("line", { precision: 8, scale: 2 }),
    price: numeric("price", { precision: 9, scale: 4 }), // decimal odds
    capturedAt: tz("captured_at").notNull(),
    isClosing: boolean("is_closing").notNull().default(false),
  },
  (t) => [
    uniqueIndex("odds_uq").on(t.gameId, t.bookmaker, t.market, t.selection, t.capturedAt),
    index("odds_game_market_idx").on(t.gameId, t.market),
  ],
);

// ----------------------------------------------------------- predictions

export const featureSnapshot = pgTable(
  "feature_snapshot",
  {
    id: serial("id").primaryKey(),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    subjectType: subjectType("subject_type").notNull(),
    subjectId: integer("subject_id").notNull(),
    asOf: tz("as_of").notNull(), // point in time the features were valid
    features: json("features"),
    createdAt: createdAt(),
  },
  (t) => [uniqueIndex("feature_snapshot_uq").on(t.gameId, t.subjectType, t.subjectId, t.asOf)],
);

export const modelRun = pgTable("model_run", {
  id: serial("id").primaryKey(),
  modelName: text("model_name").notNull(),
  modelVersion: text("model_version").notNull(),
  sportId: text("sport_id").references(() => sport.id),
  startedAt: tz("started_at").notNull().defaultNow(),
  finishedAt: tz("finished_at"),
  status: runStatus("status").notNull().default("running"),
  snapshotCount: integer("snapshot_count"),
  metrics: json("metrics"),
  notes: text("notes"),
});

export const prediction = pgTable(
  "prediction",
  {
    id: serial("id").primaryKey(),
    modelRunId: integer("model_run_id")
      .notNull()
      .references(() => modelRun.id),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    market: text("market").notNull(), // 'match_result', 'total_goals', 'anytime_scorer', 'rushing_yards', ...
    subjectType: subjectType("subject_type").notNull(),
    subjectId: integer("subject_id").notNull(),
    selection: text("selection").notNull().default(""), // 'home' | 'draw' | 'over 2.5' | ''
    probability: numeric("probability", { precision: 6, scale: 5 }),
    mean: numeric("mean", { precision: 10, scale: 3 }),
    line: numeric("line", { precision: 8, scale: 2 }),
    quantiles: json("quantiles"), // {"p25": 41.0, "p50": 58.5, "p75": 77.0}
    explanation: json("explanation"), // top feature contributions
    createdAt: createdAt(),
  },
  (t) => [
    uniqueIndex("prediction_uq").on(
      t.modelRunId,
      t.gameId,
      t.market,
      t.subjectType,
      t.subjectId,
      t.selection,
    ),
    index("prediction_game_idx").on(t.gameId, t.market),
  ],
);

// -------------------------------------------------- editorial and picks

export const pick = pgTable(
  "pick",
  {
    id: serial("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => source.id),
    gameId: integer("game_id")
      .notNull()
      .references(() => game.id),
    pickTeamId: integer("pick_team_id").references(() => team.id),
    winProbability: numeric("win_probability", { precision: 6, scale: 5 }),
    spread: numeric("spread", { precision: 6, scale: 2 }),
    total: numeric("total", { precision: 6, scale: 2 }),
    author: text("author").notNull().default(""),
    url: text("url"),
    publishedAt: tz("published_at"),
  },
  (t) => [uniqueIndex("pick_uq").on(t.sourceId, t.gameId, t.author)],
);

export const article = pgTable(
  "article",
  {
    id: serial("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => source.id),
    url: text("url").notNull().unique(),
    title: text("title").notNull(),
    summary: text("summary"),
    author: text("author"),
    publishedAt: tz("published_at"),
    teamIds: jsonb("team_ids").notNull().default(sql`'[]'::jsonb`),
    gameIds: jsonb("game_ids").notNull().default(sql`'[]'::jsonb`),
    fetchedAt: tz("fetched_at").notNull().defaultNow(),
  },
  (t) => [index("article_published_idx").on(t.publishedAt)],
);

// ------------------------------------------------------------ plumbing

export const externalId = pgTable(
  "external_id",
  {
    id: serial("id").primaryKey(),
    entityType: entityType("entity_type").notNull(),
    entityId: integer("entity_id").notNull(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => source.id),
    externalId: text("external_id").notNull(),
  },
  (t) => [
    uniqueIndex("external_id_lookup_uq").on(t.entityType, t.sourceId, t.externalId),
    uniqueIndex("external_id_entity_uq").on(t.entityType, t.entityId, t.sourceId),
  ],
);

export const rawPage = pgTable(
  "raw_page",
  {
    id: serial("id").primaryKey(),
    sourceId: integer("source_id")
      .notNull()
      .references(() => source.id),
    url: text("url").notNull(),
    fetchedAt: tz("fetched_at").notNull().defaultNow(),
    statusCode: integer("status_code"),
    contentType: text("content_type"),
    contentHash: text("content_hash").notNull(),
    body: text("body").notNull(),
  },
  (t) => [
    index("raw_page_url_idx").on(t.url, t.fetchedAt),
    index("raw_page_hash_idx").on(t.contentHash),
  ],
);

export const collectorRun = pgTable("collector_run", {
  id: serial("id").primaryKey(),
  sourceId: integer("source_id")
    .notNull()
    .references(() => source.id),
  adapter: text("adapter").notNull(),
  args: json("args"),
  startedAt: tz("started_at").notNull().defaultNow(),
  finishedAt: tz("finished_at"),
  status: runStatus("status").notNull().default("running"),
  rowsWritten: integer("rows_written").notNull().default(0),
  error: text("error"),
});
