"""Postgres writer. Idempotent upserts keyed by external ids.

Column names are the contract with packages/db/src/schema.ts.
"""

from __future__ import annotations

import os
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gimme_collectors.models import (
    CollectResult,
    CompetitionRef,
    GameRecord,
    PickRecord,
    PlayerRef,
    PlayerStatusRecord,
    RosterRecord,
    SeasonRef,
    StandingRecord,
    SummaryRecord,
    TeamRecord,
    TeamRef,
    VenueRef,
)
from gimme_collectors.pipeline.fetch import FetchResult
from gimme_collectors.pipeline.teamnames import match_team

SPORTS = {"soccer": "Soccer", "american_football": "American football"}

# `raw_page` exists so a parser bug does not force a re-scrape, which makes it a
# cache with a short useful life, not a record to keep. Left unbounded it grew to
# 292 MB in a single day of backfilling and filled the database, so three limits
# apply: skip bodies too big to be worth keeping, store only so many per run, and
# drop anything older than the window. All three are env-tunable for a run that
# genuinely needs deeper history.
RAW_PAGE_MAX_BYTES = int(os.getenv("RAW_PAGE_MAX_BYTES", "262144"))  # 256 KB
RAW_PAGE_PER_RUN = int(os.getenv("RAW_PAGE_PER_RUN", "200"))
RAW_PAGE_RETENTION_DAYS = int(os.getenv("RAW_PAGE_RETENTION_DAYS", "2"))

Cursor = psycopg.Cursor[dict[str, Any]]


class UnmatchedTeam(Exception):
    """A name-only team reference could not be matched to an existing team."""


def _id(cur: Cursor) -> int:
    row = cur.fetchone()
    assert row is not None
    return int(row["id"])


class Writer:
    def __init__(
        self,
        database_url: str,
        *,
        source_slug: str,
        source_name: str,
        base_url: str | None = None,
        rate_limit_per_min: int | None = None,
    ) -> None:
        self.conn = psycopg.connect(database_url, row_factory=dict_row)
        self.source_slug = source_slug
        self.source_id = self._ensure_reference(
            source_slug, source_name, base_url, rate_limit_per_min
        )
        self.rows_written = 0
        self.raw_pages_stored = 0
        self.raw_pages_skipped = 0
        self.unmatched: dict[str, int] = {}  # team name -> times skipped
        self._id_cache: dict[tuple[str, str], int] = {}
        # Per-run memo so bulk loads (thousands of rows naming the same teams, players,
        # seasons and rosters) touch each reference row once.
        self._competitions: dict[str, int] = {}
        self._seasons: dict[tuple[int, str], int] = {}
        self._teams_refreshed: set[int] = set()
        self._players_refreshed: set[int] = set()
        self._rosters_seen: set[tuple[int, int, int]] = set()
        self._venues: dict[str, int] = {}

    # ------------------------------------------------------------ plumbing

    def _ensure_reference(
        self, slug: str, name: str, base_url: str | None, rate_limit: int | None
    ) -> int:
        with self.conn.cursor() as cur:
            for sport_id, sport_name in SPORTS.items():
                cur.execute(
                    "INSERT INTO sport (id, name) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING",
                    (sport_id, sport_name),
                )
            cur.execute(
                """
                INSERT INTO source (slug, name, base_url, rate_limit_per_min)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name,
                    base_url = COALESCE(EXCLUDED.base_url, source.base_url),
                    rate_limit_per_min = COALESCE(EXCLUDED.rate_limit_per_min,
                                                  source.rate_limit_per_min)
                RETURNING id
                """,
                (slug, name, base_url, rate_limit),
            )
            source_id = _id(cur)
        self.conn.commit()
        return source_id

    def prune_raw_pages(self) -> int:
        """Drop cached pages past the retention window. Returns rows removed."""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM raw_page WHERE fetched_at < now() - make_interval(days => %s)",
                (RAW_PAGE_RETENTION_DAYS,),
            )
            removed = cur.rowcount
        self.conn.commit()
        return max(removed, 0)

    def begin_run(self, adapter: str, args: dict[str, Any]) -> int:
        self.prune_raw_pages()
        with self.conn.cursor() as cur:
            cur.execute(
                "INSERT INTO collector_run (source_id, adapter, args) VALUES (%s, %s, %s) "
                "RETURNING id",
                (self.source_id, adapter, Jsonb(args)),
            )
            run_id = _id(cur)
        self.conn.commit()
        return run_id

    def finish_run(self, run_id: int, *, status: str, error: str | None = None) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE collector_run SET finished_at = now(), status = %s,
                    rows_written = %s, error = %s WHERE id = %s
                """,
                (status, self.rows_written, error, run_id),
            )
        self.conn.commit()

    def save_raw(self, result: FetchResult) -> None:
        """Store a fetched page unless the latest copy of that URL has the same hash.

        Bodies over the size limit and anything past this run's budget are skipped:
        the cache is there to save a re-fetch while debugging a parser, and a
        backfill's thousands of pages are neither cheap to keep nor worth keeping.
        """
        if self.raw_pages_stored >= RAW_PAGE_PER_RUN:
            self.raw_pages_skipped += 1
            return
        if len(result.body) > RAW_PAGE_MAX_BYTES:
            self.raw_pages_skipped += 1
            return
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM raw_page WHERE url = %s ORDER BY fetched_at DESC LIMIT 1",
                (result.url,),
            )
            row = cur.fetchone()
            if row is not None and row["content_hash"] == result.content_hash:
                return
            cur.execute(
                """
                INSERT INTO raw_page (source_id, url, fetched_at, status_code, content_type,
                                      content_hash, body)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    self.source_id,
                    result.url,
                    result.fetched_at,
                    result.status_code,
                    result.content_type,
                    result.content_hash,
                    result.body,
                ),
            )
        self.raw_pages_stored += 1
        self.conn.commit()

    def _lookup_external(self, cur: Cursor, entity_type: str, external_id: str) -> int | None:
        """Resolve an external id to our entity id.

        Ids are globally unambiguous strings (ESPN uids like "s:20~l:28~t:17", or
        source-prefixed ids like "nflverse:00-0026158"), so a binding made by any
        source counts. nflverse reuses ESPN uids on purpose: its games and teams must
        land on the rows the ESPN collector created. Own-source bindings win ties.
        """
        key = (entity_type, external_id)
        if key in self._id_cache:
            return self._id_cache[key]
        cur.execute(
            """
            SELECT entity_id FROM external_id
            WHERE entity_type = %s AND external_id = %s
            ORDER BY (source_id = %s) DESC, id
            LIMIT 1
            """,
            (entity_type, external_id, self.source_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        self._id_cache[key] = int(row["entity_id"])
        return self._id_cache[key]

    def _bind_external(
        self, cur: Cursor, entity_type: str, entity_id: int, external_id: str
    ) -> None:
        # An entity resolved by name may already carry a different id from this
        # source: a stadium renamed, or a player ESPN lists under two ids across
        # feeds. One binding per (entity, source) is enforced by the schema, so
        # keep the one already stored and remember the alias for this run only.
        cur.execute(
            "SELECT external_id FROM external_id "
            "WHERE entity_type = %s AND entity_id = %s AND source_id = %s",
            (entity_type, entity_id, self.source_id),
        )
        existing = cur.fetchone()
        if existing is not None and existing["external_id"] != external_id:
            self._id_cache[(entity_type, external_id)] = entity_id
            return
        if entity_type == "venue":
            cur.execute(
                """
                INSERT INTO external_id (entity_type, entity_id, source_id, external_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (entity_type, entity_id, self.source_id, external_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO external_id (entity_type, entity_id, source_id, external_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (entity_type, source_id, external_id)
                    DO UPDATE SET entity_id = EXCLUDED.entity_id
                """,
                (entity_type, entity_id, self.source_id, external_id),
            )
        self._id_cache[(entity_type, external_id)] = entity_id

    # ----------------------------------------------------------- reference

    def upsert_competition(self, cur: Cursor, c: CompetitionRef) -> int:
        cached = self._competitions.get(c.slug)
        if cached is not None:
            return cached
        cur.execute(
            """
            INSERT INTO competition (sport_id, slug, name, short_name, country, level)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name,
                short_name = COALESCE(EXCLUDED.short_name, competition.short_name),
                country = COALESCE(EXCLUDED.country, competition.country),
                level = COALESCE(EXCLUDED.level, competition.level)
            RETURNING id
            """,
            (c.sport, c.slug, c.name, c.short_name, c.country, c.level),
        )
        self._competitions[c.slug] = _id(cur)
        return self._competitions[c.slug]

    def upsert_season(self, cur: Cursor, competition_id: int, s: SeasonRef) -> int:
        cached = self._seasons.get((competition_id, s.label))
        if cached is not None:
            return cached
        cur.execute(
            """
            INSERT INTO season (competition_id, label, year, start_date, end_date)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (competition_id, label) DO UPDATE SET year = EXCLUDED.year,
                start_date = COALESCE(EXCLUDED.start_date, season.start_date),
                end_date = COALESCE(EXCLUDED.end_date, season.end_date)
            RETURNING id
            """,
            (competition_id, s.label, s.year, s.start_date, s.end_date),
        )
        self._seasons[(competition_id, s.label)] = _id(cur)
        return self._seasons[(competition_id, s.label)]

    def resolve_team_by_name(self, cur: Cursor, competition_id: int, t: TeamRef) -> int:
        """Match a name-only TeamRef to a team already in the competition, then bind
        the source id to it so the next run is a plain lookup."""
        team_id = self._lookup_external(cur, "team", t.external_id)
        if team_id is not None:
            return team_id
        cur.execute(
            """
            SELECT DISTINCT t.id, t.name, t.short_name, t.location
            FROM team t
            JOIN team_season ts ON ts.team_id = t.id
            JOIN season s ON s.id = ts.season_id
            WHERE s.competition_id = %s
            """,
            (competition_id,),
        )
        candidates: dict[str, int] = {}
        for row in cur.fetchall():
            for name in (row["name"], row["short_name"], row["location"]):
                if name:
                    candidates.setdefault(str(name), int(row["id"]))
        team_id = match_team(t.name, candidates)
        if team_id is None:
            self.unmatched[t.name] = self.unmatched.get(t.name, 0) + 1
            raise UnmatchedTeam(t.name)
        self._bind_external(cur, "team", team_id, t.external_id)
        return team_id

    def upsert_team(self, cur: Cursor, sport: str, t: TeamRef) -> int:
        team_id = self._lookup_external(cur, "team", t.external_id)
        if team_id is None and t.match_by_name:
            raise UnmatchedTeam(t.name)  # must go through resolve_team_by_name
        if team_id is None:
            cur.execute(
                """
                INSERT INTO team (sport_id, name, short_name, abbreviation, location, logo_url,
                                  color, alt_color)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    sport,
                    t.name,
                    t.short_name,
                    t.abbreviation,
                    t.location,
                    t.logo_url,
                    t.color,
                    t.alt_color,
                ),
            )
            team_id = _id(cur)
            self._bind_external(cur, "team", team_id, t.external_id)
            self._teams_refreshed.add(team_id)
            self.rows_written += 1
        elif team_id not in self._teams_refreshed:
            self._teams_refreshed.add(team_id)
            cur.execute(
                """
                UPDATE team SET name = %s, short_name = COALESCE(%s, short_name),
                    abbreviation = COALESCE(%s, abbreviation), location = COALESCE(%s, location),
                    logo_url = COALESCE(%s, logo_url), color = COALESCE(%s, color),
                    alt_color = COALESCE(%s, alt_color), updated_at = now()
                WHERE id = %s
                """,
                (
                    t.name,
                    t.short_name,
                    t.abbreviation,
                    t.location,
                    t.logo_url,
                    t.color,
                    t.alt_color,
                    team_id,
                ),
            )
        return team_id

    def upsert_team_season(
        self, cur: Cursor, team_id: int, season_id: int, group_name: str | None
    ) -> None:
        key = (team_id, season_id, 0)
        if key in self._rosters_seen and group_name is None:
            return
        self._rosters_seen.add(key)
        cur.execute(
            """
            INSERT INTO team_season (team_id, season_id, group_name) VALUES (%s, %s, %s)
            ON CONFLICT (team_id, season_id) DO UPDATE
                SET group_name = COALESCE(EXCLUDED.group_name, team_season.group_name)
            """,
            (team_id, season_id, group_name),
        )

    def upsert_venue(self, cur: Cursor, v: VenueRef) -> int:
        if v.external_id:
            venue_id = self._lookup_external(cur, "venue", v.external_id)
            if venue_id is not None:
                return venue_id
        # Sources without venue ids (nflverse) name the stadium: reuse by name.
        cached = self._venues.get(v.name.lower())
        if cached is not None:
            if v.external_id:
                self._bind_external(cur, "venue", cached, v.external_id)
            return cached
        cur.execute("SELECT id FROM venue WHERE lower(name) = lower(%s) LIMIT 1", (v.name,))
        row = cur.fetchone()
        if row is not None:
            venue_id = int(row["id"])
        else:
            cur.execute(
                "INSERT INTO venue (name, city, state, country, indoor) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (v.name, v.city, v.state, v.country, v.indoor),
            )
            venue_id = _id(cur)
        self._venues[v.name.lower()] = venue_id
        if v.external_id:
            self._bind_external(cur, "venue", venue_id, v.external_id)
        return venue_id

    # --------------------------------------------------------------- games

    def find_game(
        self, cur: Cursor, season_id: int, home_id: int, away_id: int, kickoff: Any
    ) -> int | None:
        """The same fixture from another source: same season and teams, kickoff within
        36 hours (sources disagree on time zones and TBD kickoffs)."""
        cur.execute(
            """
            SELECT id FROM game
            WHERE season_id = %s AND home_team_id = %s AND away_team_id = %s
              AND kickoff BETWEEN %s::timestamptz - interval '36 hours'
                              AND %s::timestamptz + interval '36 hours'
            ORDER BY abs(extract(epoch FROM (kickoff - %s::timestamptz))) LIMIT 1
            """,
            (season_id, home_id, away_id, kickoff, kickoff, kickoff),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None

    def _team_for_game(self, cur: Cursor, competition_id: int, sport: str, t: TeamRef) -> int:
        if t.match_by_name:
            return self.resolve_team_by_name(cur, competition_id, t)
        return self.upsert_team(cur, sport, t)

    def upsert_game(self, cur: Cursor, g: GameRecord) -> int:
        competition_id = self.upsert_competition(cur, g.competition)
        season_id = self.upsert_season(cur, competition_id, g.season)
        home_id = self._team_for_game(cur, competition_id, g.competition.sport, g.home)
        away_id = self._team_for_game(cur, competition_id, g.competition.sport, g.away)
        self.upsert_team_season(cur, home_id, season_id, None)
        self.upsert_team_season(cur, away_id, season_id, None)
        venue_id = self.upsert_venue(cur, g.venue) if g.venue else None

        game_id = self._lookup_external(cur, "game", g.external_id)
        if game_id is None:
            game_id = self.find_game(cur, season_id, home_id, away_id, g.kickoff)
            if game_id is not None:
                self._bind_external(cur, "game", game_id, g.external_id)
        params = (
            competition_id,
            season_id,
            g.kickoff,
            home_id,
            away_id,
            venue_id,
            g.home_score,
            g.away_score,
            g.status,
            g.status_detail,
            g.period,
            g.clock,
            g.week,
            g.round,
            g.neutral_site,
            g.conference_game,
            g.attendance,
            Jsonb(g.weather),
        )
        if game_id is None:
            cur.execute(
                """
                INSERT INTO game (competition_id, season_id, kickoff, home_team_id, away_team_id,
                    venue_id, home_score, away_score, status, status_detail, period, clock, week,
                    round, neutral_site, conference_game, attendance, weather)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (season_id, kickoff, home_team_id, away_team_id) DO UPDATE SET
                    home_score = EXCLUDED.home_score, away_score = EXCLUDED.away_score,
                    status = EXCLUDED.status, status_detail = EXCLUDED.status_detail,
                    period = EXCLUDED.period, clock = EXCLUDED.clock, week = EXCLUDED.week,
                    round = EXCLUDED.round, venue_id = COALESCE(EXCLUDED.venue_id, game.venue_id),
                    attendance = COALESCE(EXCLUDED.attendance, game.attendance),
                    weather = EXCLUDED.weather, updated_at = now()
                RETURNING id
                """,
                params,
            )
            game_id = _id(cur)
            self._bind_external(cur, "game", game_id, g.external_id)
        else:
            # Another source's copy of a known game: fill gaps, never blank out
            # details the first source had (scores, venue, weather, week).
            cur.execute(
                """
                UPDATE game SET
                    venue_id = COALESCE(venue_id, %s),
                    home_score = COALESCE(%s, home_score), away_score = COALESCE(%s, away_score),
                    status = CASE WHEN status IN ('scheduled', 'in_progress') THEN %s
                                  ELSE status END,
                    status_detail = COALESCE(status_detail, %s),
                    period = COALESCE(%s, period), clock = COALESCE(%s, clock),
                    week = COALESCE(week, %s), round = COALESCE(round, %s),
                    neutral_site = neutral_site OR %s,
                    conference_game = COALESCE(conference_game, %s),
                    attendance = COALESCE(attendance, %s), weather = weather || %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (
                    venue_id,
                    g.home_score,
                    g.away_score,
                    g.status,
                    g.status_detail,
                    g.period,
                    g.clock,
                    g.week,
                    g.round,
                    g.neutral_site,
                    g.conference_game,
                    g.attendance,
                    Jsonb(g.weather),
                    game_id,
                ),
            )
        self.rows_written += 1

        for team_id, stats in ((home_id, g.home_stats), (away_id, g.away_stats)):
            if stats:
                cur.execute(
                    """
                    INSERT INTO team_game_stat (game_id, team_id, stats) VALUES (%s, %s, %s)
                    ON CONFLICT (game_id, team_id) DO UPDATE
                        SET stats = team_game_stat.stats || EXCLUDED.stats, updated_at = now()
                    """,
                    (game_id, team_id, Jsonb(stats)),
                )
                self.rows_written += 1

        for o in g.odds:
            cur.execute(
                """
                INSERT INTO odds (game_id, source_id, bookmaker, market, selection, line, price,
                                  captured_at, is_closing)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (game_id, bookmaker, market, selection, captured_at) DO NOTHING
                """,
                (
                    game_id,
                    self.source_id,
                    o.bookmaker,
                    o.market,
                    o.selection,
                    o.line,
                    o.price,
                    o.captured_at,
                    o.is_closing,
                ),
            )
            self.rows_written += cur.rowcount
        return game_id

    def upsert_team_record(self, cur: Cursor, r: TeamRecord) -> int:
        competition_id = self.upsert_competition(cur, r.competition)
        season_id = self.upsert_season(cur, competition_id, r.season)
        team_id = self.upsert_team(cur, r.competition.sport, r.team)
        self.upsert_team_season(cur, team_id, season_id, r.group_name)
        return team_id

    def upsert_standing(self, cur: Cursor, s: StandingRecord) -> None:
        competition_id = self.upsert_competition(cur, s.competition)
        season_id = self.upsert_season(cur, competition_id, s.season)
        team_id = self.upsert_team(cur, s.competition.sport, s.team)
        self.upsert_team_season(cur, team_id, season_id, s.group_name or None)
        cur.execute(
            """
            INSERT INTO standing (season_id, team_id, as_of, group_name, rank, played, wins, draws,
                                  losses, points, points_for, points_against, stats)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (season_id, team_id, as_of, group_name) DO UPDATE SET
                rank = EXCLUDED.rank, played = EXCLUDED.played, wins = EXCLUDED.wins,
                draws = EXCLUDED.draws, losses = EXCLUDED.losses, points = EXCLUDED.points,
                points_for = EXCLUDED.points_for, points_against = EXCLUDED.points_against,
                stats = EXCLUDED.stats
            """,
            (
                season_id,
                team_id,
                s.as_of,
                s.group_name,
                s.rank,
                s.played,
                s.wins,
                s.draws,
                s.losses,
                s.points,
                s.points_for,
                s.points_against,
                Jsonb(s.stats),
            ),
        )
        self.rows_written += 1

    # ------------------------------------------------------------- players

    def _player_by_name(
        self, cur: Cursor, sport: str, p: PlayerRef, team_id: int | None
    ) -> int | None:
        """Second source for a player we already know: same full name on the same
        team's roster (or, failing that, unique in the sport)."""
        if team_id is not None:
            cur.execute(
                """
                SELECT p.id FROM player p JOIN roster r ON r.player_id = p.id
                WHERE r.team_id = %s AND lower(p.full_name) = lower(%s) AND p.sport_id = %s
                LIMIT 2
                """,
                (team_id, p.full_name, sport),
            )
            rows = cur.fetchall()
            if len(rows) == 1:
                return int(rows[0]["id"])
        cur.execute(
            "SELECT id FROM player WHERE sport_id = %s AND lower(full_name) = lower(%s) LIMIT 2",
            (sport, p.full_name),
        )
        rows = cur.fetchall()
        return int(rows[0]["id"]) if len(rows) == 1 else None

    def upsert_player(
        self, cur: Cursor, sport: str, p: PlayerRef, team_id: int | None = None
    ) -> int:
        player_id = self._lookup_external(cur, "player", p.external_id)
        if player_id is None:
            player_id = self._player_by_name(cur, sport, p, team_id)
            if player_id is not None:
                self._bind_external(cur, "player", player_id, p.external_id)
        if player_id is None:
            cur.execute(
                """
                INSERT INTO player (sport_id, full_name, short_name, position, birth_date,
                                    nationality, height_cm, weight_kg, headshot_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                """,
                (
                    sport,
                    p.full_name,
                    p.short_name,
                    p.position,
                    p.birth_date,
                    p.nationality,
                    p.height_cm,
                    p.weight_kg,
                    p.headshot_url,
                ),
            )
            player_id = _id(cur)
            self._bind_external(cur, "player", player_id, p.external_id)
            self._players_refreshed.add(player_id)
            self.rows_written += 1
        elif player_id not in self._players_refreshed:
            self._players_refreshed.add(player_id)
            cur.execute(
                """
                UPDATE player SET full_name = %s, short_name = COALESCE(%s, short_name),
                    position = COALESCE(%s, position), birth_date = COALESCE(%s, birth_date),
                    nationality = COALESCE(%s, nationality), height_cm = COALESCE(%s, height_cm),
                    weight_kg = COALESCE(%s, weight_kg),
                    headshot_url = COALESCE(%s, headshot_url), updated_at = now()
                WHERE id = %s
                """,
                (
                    p.full_name,
                    p.short_name,
                    p.position,
                    p.birth_date,
                    p.nationality,
                    p.height_cm,
                    p.weight_kg,
                    p.headshot_url,
                    player_id,
                ),
            )
        return player_id

    def upsert_roster(
        self,
        cur: Cursor,
        player_id: int,
        team_id: int,
        season_id: int,
        jersey: str | None,
        position: str | None,
    ) -> None:
        key = (player_id, team_id, season_id)
        if key in self._rosters_seen:
            return
        self._rosters_seen.add(key)
        cur.execute(
            """
            INSERT INTO roster (player_id, team_id, season_id, jersey_number, position)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (player_id, team_id, season_id) DO UPDATE SET
                jersey_number = COALESCE(EXCLUDED.jersey_number, roster.jersey_number),
                position = COALESCE(EXCLUDED.position, roster.position)
            """,
            (player_id, team_id, season_id, jersey, position),
        )

    def latest_season(self, cur: Cursor, competition_id: int) -> int | None:
        cur.execute(
            "SELECT id FROM season WHERE competition_id = %s "
            "ORDER BY year DESC, label DESC LIMIT 1",
            (competition_id,),
        )
        row = cur.fetchone()
        return int(row["id"]) if row else None

    def upsert_roster_record(self, cur: Cursor, r: RosterRecord) -> None:
        competition_id = self.upsert_competition(cur, r.competition)
        season_id = (
            self.upsert_season(cur, competition_id, r.season)
            if r.season
            else self.latest_season(cur, competition_id)
        )
        if season_id is None:
            return
        team_id = self.upsert_team(cur, r.competition.sport, r.team)
        self.upsert_team_season(cur, team_id, season_id, None)
        player_id = self.upsert_player(cur, r.competition.sport, r.player)
        self.upsert_roster(cur, player_id, team_id, season_id, r.jersey, r.position)
        self.rows_written += 1

    def upsert_player_status(self, cur: Cursor, r: PlayerStatusRecord) -> None:
        """One current report per player per source; a later report replaces it."""
        competition_id = self.upsert_competition(cur, r.competition)
        sport = r.competition.sport
        try:
            team_id = self._team_for_game(cur, competition_id, sport, r.team)
        except UnmatchedTeam:
            return
        player_id = self.upsert_player(cur, sport, r.player, team_id)
        cur.execute(
            """
            INSERT INTO player_status (player_id, team_id, source_id, status, availability,
                                       play_probability, injury_type, body_location, detail,
                                       side, return_date, comment, reported_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, source_id) DO UPDATE SET
                team_id = EXCLUDED.team_id, status = EXCLUDED.status,
                availability = EXCLUDED.availability,
                play_probability = EXCLUDED.play_probability,
                injury_type = EXCLUDED.injury_type, body_location = EXCLUDED.body_location,
                detail = EXCLUDED.detail, side = EXCLUDED.side,
                return_date = EXCLUDED.return_date, comment = EXCLUDED.comment,
                reported_at = EXCLUDED.reported_at, updated_at = now()
            """,
            (
                player_id,
                team_id,
                self.source_id,
                r.status,
                r.availability,
                r.play_probability,
                r.injury_type,
                r.body_location,
                r.detail,
                r.side,
                r.return_date,
                r.comment,
                r.reported_at,
            ),
        )
        self.rows_written += 1

    def upsert_pick(
        self, cur: Cursor, game_id: int, pick_team_id: int | None, p: PickRecord
    ) -> None:
        cur.execute(
            """
            INSERT INTO pick (source_id, game_id, pick_team_id, win_probability, spread, total,
                              author, url, published_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id, game_id, author) DO UPDATE SET
                pick_team_id = EXCLUDED.pick_team_id, win_probability = EXCLUDED.win_probability,
                spread = COALESCE(EXCLUDED.spread, pick.spread),
                total = COALESCE(EXCLUDED.total, pick.total),
                url = COALESCE(EXCLUDED.url, pick.url), published_at = EXCLUDED.published_at
            """,
            (
                self.source_id,
                game_id,
                pick_team_id,
                p.win_probability,
                p.spread,
                p.total,
                p.author,
                p.url,
                p.published_at,
            ),
        )
        self.rows_written += 1

    def write_summary(self, cur: Cursor, s: SummaryRecord) -> bool:
        """Attach box score, player stats, lineups and picks to an existing game."""
        game_id = self._lookup_external(cur, "game", s.game_external_id)
        if game_id is None:
            return False
        cur.execute("SELECT season_id FROM game WHERE id = %s", (game_id,))
        row = cur.fetchone()
        season_id = int(row["season_id"]) if row else None
        sport = s.competition.sport
        home_id = self.upsert_team(cur, sport, s.home)
        away_id = self.upsert_team(cur, sport, s.away)

        if s.status is not None:
            cur.execute(
                """
                UPDATE game SET status = %s,
                    home_score = COALESCE(%s, home_score), away_score = COALESCE(%s, away_score),
                    updated_at = now()
                WHERE id = %s
                """,
                (s.status, s.home_score, s.away_score, game_id),
            )

        for team_id, stats in ((home_id, s.home_stats), (away_id, s.away_stats)):
            if stats:
                cur.execute(
                    """
                    INSERT INTO team_game_stat (game_id, team_id, stats) VALUES (%s, %s, %s)
                    ON CONFLICT (game_id, team_id) DO UPDATE
                        SET stats = team_game_stat.stats || EXCLUDED.stats, updated_at = now()
                    """,
                    (game_id, team_id, Jsonb(stats)),
                )
                self.rows_written += 1

        for ps in s.players:
            team_id = self.upsert_team(cur, sport, ps.team)
            player_id = self.upsert_player(cur, sport, ps.player, team_id)
            cur.execute(
                """
                INSERT INTO player_game_stat (game_id, player_id, team_id, stats)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (game_id, player_id) DO UPDATE
                    SET team_id = EXCLUDED.team_id,
                        stats = player_game_stat.stats || EXCLUDED.stats, updated_at = now()
                """,
                (game_id, player_id, team_id, Jsonb(ps.stats)),
            )
            self.rows_written += 1
            if season_id is not None:
                self.upsert_roster(
                    cur, player_id, team_id, season_id, ps.player.jersey, ps.player.position
                )

        for p in s.picks:
            pick_team_id = self.upsert_team(cur, sport, p.pick_team) if p.pick_team else None
            self.upsert_pick(cur, game_id, pick_team_id, p)
        return True

    # --------------------------------------------------------------- batch

    def write(self, result: CollectResult) -> int:
        """Write a whole collect result in one transaction. Returns rows written."""
        before = self.rows_written
        try:
            with self.conn.cursor() as cur:
                for t in result.teams:
                    self.upsert_team_record(cur, t)
                for g in result.games:
                    cur.execute("SAVEPOINT game")
                    try:
                        self.upsert_game(cur, g)
                    except UnmatchedTeam:
                        cur.execute("ROLLBACK TO SAVEPOINT game")
                    else:
                        cur.execute("RELEASE SAVEPOINT game")
                for s in result.standings:
                    self.upsert_standing(cur, s)
                for r in result.rosters:
                    self.upsert_roster_record(cur, r)
                for summary in result.summaries:
                    self.write_summary(cur, summary)
                for status in result.statuses:
                    cur.execute("SAVEPOINT status")
                    try:
                        self.upsert_player_status(cur, status)
                    except UnmatchedTeam:
                        cur.execute("ROLLBACK TO SAVEPOINT status")
                    else:
                        cur.execute("RELEASE SAVEPOINT status")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.rows_written - before

    def close(self) -> None:
        self.conn.close()
