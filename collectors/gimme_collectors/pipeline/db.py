"""Postgres writer. Idempotent upserts keyed by external ids.

Column names are the contract with packages/db/src/schema.ts.
"""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gimme_collectors.models import (
    CollectResult,
    CompetitionRef,
    GameRecord,
    SeasonRef,
    StandingRecord,
    TeamRecord,
    TeamRef,
    VenueRef,
)
from gimme_collectors.pipeline.fetch import FetchResult

SPORTS = {"soccer": "Soccer", "american_football": "American football"}

Cursor = psycopg.Cursor[dict[str, Any]]


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
        self._id_cache: dict[tuple[str, str], int] = {}

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

    def begin_run(self, adapter: str, args: dict[str, Any]) -> int:
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
        """Store a fetched page unless the latest copy of that URL has the same hash."""
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
        self.conn.commit()

    def _lookup_external(self, cur: Cursor, entity_type: str, external_id: str) -> int | None:
        key = (entity_type, external_id)
        if key in self._id_cache:
            return self._id_cache[key]
        cur.execute(
            """
            SELECT entity_id FROM external_id
            WHERE entity_type = %s AND source_id = %s AND external_id = %s
            """,
            (entity_type, self.source_id, external_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        self._id_cache[key] = int(row["entity_id"])
        return self._id_cache[key]

    def _bind_external(
        self, cur: Cursor, entity_type: str, entity_id: int, external_id: str
    ) -> None:
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
        return _id(cur)

    def upsert_season(self, cur: Cursor, competition_id: int, s: SeasonRef) -> int:
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
        return _id(cur)

    def upsert_team(self, cur: Cursor, sport: str, t: TeamRef) -> int:
        team_id = self._lookup_external(cur, "team", t.external_id)
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
            self.rows_written += 1
        else:
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
        cur.execute(
            "INSERT INTO venue (name, city, state, country, indoor) "
            "VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (v.name, v.city, v.state, v.country, v.indoor),
        )
        venue_id = _id(cur)
        if v.external_id:
            self._bind_external(cur, "venue", venue_id, v.external_id)
        return venue_id

    # --------------------------------------------------------------- games

    def upsert_game(self, cur: Cursor, g: GameRecord) -> int:
        competition_id = self.upsert_competition(cur, g.competition)
        season_id = self.upsert_season(cur, competition_id, g.season)
        home_id = self.upsert_team(cur, g.competition.sport, g.home)
        away_id = self.upsert_team(cur, g.competition.sport, g.away)
        self.upsert_team_season(cur, home_id, season_id, None)
        self.upsert_team_season(cur, away_id, season_id, None)
        venue_id = self.upsert_venue(cur, g.venue) if g.venue else None

        game_id = self._lookup_external(cur, "game", g.external_id)
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
            cur.execute(
                """
                UPDATE game SET competition_id = %s, season_id = %s, kickoff = %s,
                    home_team_id = %s, away_team_id = %s, venue_id = COALESCE(%s, venue_id),
                    home_score = %s, away_score = %s, status = %s, status_detail = %s,
                    period = %s, clock = %s, week = %s, round = %s, neutral_site = %s,
                    conference_game = %s, attendance = COALESCE(%s, attendance), weather = %s,
                    updated_at = now()
                WHERE id = %s
                """,
                (*params, game_id),
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
                                  captured_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
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

    # --------------------------------------------------------------- batch

    def write(self, result: CollectResult) -> int:
        """Write a whole collect result in one transaction. Returns rows written."""
        before = self.rows_written
        try:
            with self.conn.cursor() as cur:
                for t in result.teams:
                    self.upsert_team_record(cur, t)
                for g in result.games:
                    self.upsert_game(cur, g)
                for s in result.standings:
                    self.upsert_standing(cur, s)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.rows_written - before

    def close(self) -> None:
        self.conn.close()
