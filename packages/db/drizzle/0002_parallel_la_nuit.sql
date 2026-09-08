CREATE TYPE "public"."availability" AS ENUM('available', 'questionable', 'doubtful', 'out');--> statement-breakpoint
CREATE TABLE "player_status" (
	"id" serial PRIMARY KEY NOT NULL,
	"player_id" integer NOT NULL,
	"team_id" integer,
	"source_id" integer NOT NULL,
	"status" text NOT NULL,
	"availability" "availability" NOT NULL,
	"play_probability" numeric(4, 3),
	"injury_type" text,
	"body_location" text,
	"detail" text,
	"side" text,
	"return_date" date,
	"comment" text,
	"reported_at" timestamp with time zone,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "player_status" ADD CONSTRAINT "player_status_player_id_player_id_fk" FOREIGN KEY ("player_id") REFERENCES "public"."player"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_status" ADD CONSTRAINT "player_status_team_id_team_id_fk" FOREIGN KEY ("team_id") REFERENCES "public"."team"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "player_status" ADD CONSTRAINT "player_status_source_id_source_id_fk" FOREIGN KEY ("source_id") REFERENCES "public"."source"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "player_status_uq" ON "player_status" USING btree ("player_id","source_id");--> statement-breakpoint
CREATE INDEX "player_status_team_idx" ON "player_status" USING btree ("team_id","availability");