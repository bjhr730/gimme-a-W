CREATE TYPE "public"."entity_type" AS ENUM('competition', 'season', 'team', 'player', 'game', 'venue');--> statement-breakpoint
CREATE TYPE "public"."game_status" AS ENUM('scheduled', 'in_progress', 'final', 'postponed', 'canceled', 'suspended');--> statement-breakpoint
CREATE TYPE "public"."run_status" AS ENUM('running', 'succeeded', 'failed');--> statement-breakpoint
CREATE TYPE "public"."subject_type" AS ENUM('game', 'team', 'player');--> statement-breakpoint
CREATE TABLE "article" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"url" text NOT NULL,
	"title" text NOT NULL,
	"summary" text,
	"author" text,
	"published_at" timestamp with time zone,
	"team_ids" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"game_ids" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "article_url_unique" UNIQUE("url")
);
--> statement-breakpoint
CREATE TABLE "collector_run" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"adapter" text NOT NULL,
	"args" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"status" "run_status" DEFAULT 'running' NOT NULL,
	"rows_written" integer DEFAULT 0 NOT NULL,
	"error" text
);
--> statement-breakpoint
CREATE TABLE "competition" (
	"id" serial PRIMARY KEY NOT NULL,
	"sport_id" text NOT NULL,
	"slug" text NOT NULL,
	"name" text NOT NULL,
	"short_name" text,
	"country" text,
	"level" text,
	"is_active" boolean DEFAULT true NOT NULL,
	CONSTRAINT "competition_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "external_id" (
	"id" serial PRIMARY KEY NOT NULL,
	"entity_type" "entity_type" NOT NULL,
	"entity_id" integer NOT NULL,
	"source_id" integer NOT NULL,
	"external_id" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "feature_snapshot" (
	"id" serial PRIMARY KEY NOT NULL,
	"game_id" integer NOT NULL,
	"subject_type" "subject_type" NOT NULL,
	"subject_id" integer NOT NULL,
	"as_of" timestamp with time zone NOT NULL,
	"features" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "game" (
	"id" serial PRIMARY KEY NOT NULL,
	"competition_id" integer NOT NULL,
	"season_id" integer NOT NULL,
	"kickoff" timestamp with time zone NOT NULL,
	"home_team_id" integer NOT NULL,
	"away_team_id" integer NOT NULL,
	"venue_id" integer,
	"home_score" integer,
	"away_score" integer,
	"status" "game_status" DEFAULT 'scheduled' NOT NULL,
	"status_detail" text,
	"period" integer,
	"clock" text,
	"week" integer,
	"round" text,
	"neutral_site" boolean DEFAULT false NOT NULL,
	"conference_game" boolean,
	"attendance" integer,
	"weather" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "model_run" (
	"id" serial PRIMARY KEY NOT NULL,
	"model_name" text NOT NULL,
	"model_version" text NOT NULL,
	"sport_id" text,
	"started_at" timestamp with time zone DEFAULT now() NOT NULL,
	"finished_at" timestamp with time zone,
	"status" "run_status" DEFAULT 'running' NOT NULL,
	"snapshot_count" integer,
	"metrics" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"notes" text
);
--> statement-breakpoint
CREATE TABLE "odds" (
	"id" serial PRIMARY KEY NOT NULL,
	"game_id" integer NOT NULL,
	"source_id" integer NOT NULL,
	"bookmaker" text NOT NULL,
	"market" text NOT NULL,
	"selection" text NOT NULL,
	"line" numeric(8, 2),
	"price" numeric(9, 4),
	"captured_at" timestamp with time zone NOT NULL,
	"is_closing" boolean DEFAULT false NOT NULL
);
--> statement-breakpoint
CREATE TABLE "pick" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"game_id" integer NOT NULL,
	"pick_team_id" integer,
	"win_probability" numeric(6, 5),
	"spread" numeric(6, 2),
	"total" numeric(6, 2),
	"author" text DEFAULT '' NOT NULL,
	"url" text,
	"published_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "player" (
	"id" serial PRIMARY KEY NOT NULL,
	"sport_id" text NOT NULL,
	"full_name" text NOT NULL,
	"short_name" text,
	"position" text,
	"birth_date" date,
	"nationality" text,
	"height_cm" integer,
	"weight_kg" integer,
	"is_active" boolean DEFAULT true NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "player_game_stat" (
	"id" serial PRIMARY KEY NOT NULL,
	"game_id" integer NOT NULL,
	"player_id" integer NOT NULL,
	"team_id" integer NOT NULL,
	"stats" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "prediction" (
	"id" serial PRIMARY KEY NOT NULL,
	"model_run_id" integer NOT NULL,
	"game_id" integer NOT NULL,
	"market" text NOT NULL,
	"subject_type" "subject_type" NOT NULL,
	"subject_id" integer NOT NULL,
	"selection" text DEFAULT '' NOT NULL,
	"probability" numeric(6, 5),
	"mean" numeric(10, 3),
	"line" numeric(8, 2),
	"quantiles" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"explanation" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "rating" (
	"id" serial PRIMARY KEY NOT NULL,
	"subject_type" "subject_type" NOT NULL,
	"subject_id" integer NOT NULL,
	"season_id" integer,
	"as_of" date NOT NULL,
	"kind" text NOT NULL,
	"value" numeric(12, 4) NOT NULL,
	"model_version" text DEFAULT '' NOT NULL
);
--> statement-breakpoint
CREATE TABLE "raw_page" (
	"id" serial PRIMARY KEY NOT NULL,
	"source_id" integer NOT NULL,
	"url" text NOT NULL,
	"fetched_at" timestamp with time zone DEFAULT now() NOT NULL,
	"status_code" integer,
	"content_type" text,
	"content_hash" text NOT NULL,
	"body" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "roster" (
	"id" serial PRIMARY KEY NOT NULL,
	"player_id" integer NOT NULL,
	"team_id" integer NOT NULL,
	"season_id" integer NOT NULL,
	"jersey_number" text,
	"position" text
);
--> statement-breakpoint
CREATE TABLE "season" (
	"id" serial PRIMARY KEY NOT NULL,
	"competition_id" integer NOT NULL,
	"label" text NOT NULL,
	"year" integer NOT NULL,
	"start_date" date,
	"end_date" date
);
--> statement-breakpoint
CREATE TABLE "source" (
	"id" serial PRIMARY KEY NOT NULL,
	"slug" text NOT NULL,
	"name" text NOT NULL,
	"base_url" text,
	"rate_limit_per_min" integer,
	"notes" text,
	CONSTRAINT "source_slug_unique" UNIQUE("slug")
);
--> statement-breakpoint
CREATE TABLE "sport" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL
);
--> statement-breakpoint
CREATE TABLE "standing" (
	"id" serial PRIMARY KEY NOT NULL,
	"season_id" integer NOT NULL,
	"team_id" integer NOT NULL,
	"as_of" date NOT NULL,
	"group_name" text DEFAULT '' NOT NULL,
	"rank" integer,
	"played" integer,
	"wins" integer,
	"draws" integer,
	"losses" integer,
	"points" integer,
	"points_for" integer,
	"points_against" integer,
	"stats" jsonb DEFAULT '{}'::jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "team" (
	"id" serial PRIMARY KEY NOT NULL,
	"sport_id" text NOT NULL,
	"name" text NOT NULL,
	"short_name" text,
	"abbreviation" text,
	"location" text,
	"logo_url" text,
	"color" text,
	"alt_color" text,
	"is_active" boolean DEFAULT true NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "team_form" (
	"id" serial PRIMARY KEY NOT NULL,
	"team_id" integer NOT NULL,
	"season_id" integer NOT NULL,
	"as_of" date NOT NULL,
	"last_n" integer DEFAULT 5 NOT NULL,
	"form" text,
	"ppg" numeric(5, 3),
	"margin_per_game" numeric(7, 3),
	"xg_diff_per_game" numeric(7, 3),
	"rest_days" integer,
	"stats" jsonb DEFAULT '{}'::jsonb NOT NULL
);
--> statement-breakpoint
CREATE TABLE "team_game_stat" (
	"id" serial PRIMARY KEY NOT NULL,
	"game_id" integer NOT NULL,
	"team_id" integer NOT NULL,
	"stats" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "team_season" (
	"id" serial PRIMARY KEY NOT NULL,
	"team_id" integer NOT NULL,
	"season_id" integer NOT NULL,
	"group_name" text
);
--> statement-breakpoint
CREATE TABLE "venue" (
	"id" serial PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"city" text,
	"state" text,
	"country" text,
	"indoor" boolean,
	"capacity" integer
);
--> statement-breakpoint
ALTER TABLE "article" ADD CONSTRAINT "article_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "collector_run" ADD CONSTRAINT "collector_run_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "competition" ADD CONSTRAINT "competition_sport_id_sport_id_fk" FOREIGN KEY ("sport_id") REFERENCES "public"."sport"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "external_id" ADD CONSTRAINT "external_id_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "feature_snapshot" ADD CONSTRAINT "feature_snapshot_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game" ADD CONSTRAINT "game_competition_id_competition_id_fk" FOREIGN KEY ("competition_id") REFERENCES "public"."competition"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game" ADD CONSTRAINT "game_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game" ADD CONSTRAINT "game_home_team_id_team_id_fk" FOREIGN KEY ("home_team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game" ADD CONSTRAINT "game_away_team_id_team_id_fk" FOREIGN KEY ("away_team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "game" ADD CONSTRAINT "game_venue_id_venue_id_fk" FOREIGN KEY ("venue_id") REFERENCES "public"."venue"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_run" ADD CONSTRAINT "model_run_sport_id_sport_id_fk" FOREIGN KEY ("sport_id") REFERENCES "public"."sport"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "odds" ADD CONSTRAINT "odds_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "odds" ADD CONSTRAINT "odds_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pick" ADD CONSTRAINT "pick_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pick" ADD CONSTRAINT "pick_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "pick" ADD CONSTRAINT "pick_pick_team_id_team_id_fk" FOREIGN KEY ("pick_team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player" ADD CONSTRAINT "player_sport_id_sport_id_fk" FOREIGN KEY ("sport_id") REFERENCES "public"."sport"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_game_stat" ADD CONSTRAINT "player_game_stat_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_game_stat" ADD CONSTRAINT "player_game_stat_player_id_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."player"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_game_stat" ADD CONSTRAINT "player_game_stat_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "prediction" ADD CONSTRAINT "prediction_model_run_id_model_run_id_fk" FOREIGN KEY ("model_run_id") REFERENCES "public"."model_run"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "prediction" ADD CONSTRAINT "prediction_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "rating" ADD CONSTRAINT "rating_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "raw_page" ADD CONSTRAINT "raw_page_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "roster" ADD CONSTRAINT "roster_player_id_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."player"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "roster" ADD CONSTRAINT "roster_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "roster" ADD CONSTRAINT "roster_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "season" ADD CONSTRAINT "season_competition_id_competition_id_fk" FOREIGN KEY ("competition_id") REFERENCES "public"."competition"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "standing" ADD CONSTRAINT "standing_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "standing" ADD CONSTRAINT "standing_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team" ADD CONSTRAINT "team_sport_id_sport_id_fk" FOREIGN KEY ("sport_id") REFERENCES "public"."sport"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_form" ADD CONSTRAINT "team_form_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_form" ADD CONSTRAINT "team_form_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_game_stat" ADD CONSTRAINT "team_game_stat_game_id_game_id_fk" FOREIGN KEY ("game_id") REFERENCES "public"."game"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_game_stat" ADD CONSTRAINT "team_game_stat_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_season" ADD CONSTRAINT "team_season_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "team_season" ADD CONSTRAINT "team_season_season_id_season_id_fk" FOREIGN KEY ("season_id") REFERENCES "public"."season"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "article_published_idx" ON "article" USING btree ("published_at");--> statement-breakpoint
CREATE INDEX "competition_sport_idx" ON "competition" USING btree ("sport_id");--> statement-breakpoint
CREATE UNIQUE INDEX "external_id_lookup_uq" ON "external_id" USING btree ("entity_type","source_id","external_id");--> statement-breakpoint
CREATE UNIQUE INDEX "external_id_entity_uq" ON "external_id" USING btree ("entity_type","entity_id","source_id");--> statement-breakpoint
CREATE UNIQUE INDEX "feature_snapshot_uq" ON "feature_snapshot" USING btree ("game_id","subject_type","subject_id","as_of");--> statement-breakpoint
CREATE UNIQUE INDEX "game_natural_uq" ON "game" USING btree ("season_id","kickoff","home_team_id","away_team_id");--> statement-breakpoint
CREATE INDEX "game_kickoff_idx" ON "game" USING btree ("kickoff");--> statement-breakpoint
CREATE INDEX "game_season_idx" ON "game" USING btree ("season_id");--> statement-breakpoint
CREATE INDEX "game_home_idx" ON "game" USING btree ("home_team_id");--> statement-breakpoint
CREATE INDEX "game_away_idx" ON "game" USING btree ("away_team_id");--> statement-breakpoint
CREATE UNIQUE INDEX "odds_uq" ON "odds" USING btree ("game_id","bookmaker","market","selection","captured_at");--> statement-breakpoint
CREATE INDEX "odds_game_market_idx" ON "odds" USING btree ("game_id","market");--> statement-breakpoint
CREATE UNIQUE INDEX "pick_uq" ON "pick" USING btree ("source_id","game_id","author");--> statement-breakpoint
CREATE INDEX "player_sport_name_idx" ON "player" USING btree ("sport_id","full_name");--> statement-breakpoint
CREATE UNIQUE INDEX "player_game_stat_uq" ON "player_game_stat" USING btree ("game_id","player_id");--> statement-breakpoint
CREATE INDEX "player_game_stat_player_idx" ON "player_game_stat" USING btree ("player_id");--> statement-breakpoint
CREATE UNIQUE INDEX "prediction_uq" ON "prediction" USING btree ("model_run_id","game_id","market","subject_type","subject_id","selection");--> statement-breakpoint
CREATE INDEX "prediction_game_idx" ON "prediction" USING btree ("game_id","market");--> statement-breakpoint
CREATE UNIQUE INDEX "rating_uq" ON "rating" USING btree ("subject_type","subject_id","as_of","kind","model_version");--> statement-breakpoint
CREATE INDEX "rating_subject_idx" ON "rating" USING btree ("subject_type","subject_id","kind");--> statement-breakpoint
CREATE INDEX "raw_page_url_idx" ON "raw_page" USING btree ("url","fetched_at");--> statement-breakpoint
CREATE INDEX "raw_page_hash_idx" ON "raw_page" USING btree ("content_hash");--> statement-breakpoint
CREATE UNIQUE INDEX "roster_uq" ON "roster" USING btree ("player_id","team_id","season_id");--> statement-breakpoint
CREATE UNIQUE INDEX "season_competition_label_uq" ON "season" USING btree ("competition_id","label");--> statement-breakpoint
CREATE UNIQUE INDEX "standing_uq" ON "standing" USING btree ("season_id","team_id","as_of","group_name");--> statement-breakpoint
CREATE INDEX "team_sport_name_idx" ON "team" USING btree ("sport_id","name");--> statement-breakpoint
CREATE UNIQUE INDEX "team_form_uq" ON "team_form" USING btree ("team_id","season_id","as_of","last_n");--> statement-breakpoint
CREATE UNIQUE INDEX "team_game_stat_uq" ON "team_game_stat" USING btree ("game_id","team_id");--> statement-breakpoint
CREATE UNIQUE INDEX "team_season_uq" ON "team_season" USING btree ("team_id","season_id");