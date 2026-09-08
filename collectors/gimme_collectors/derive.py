"""Derived tables computed from our own `game` rows: team form and Elo ratings.

Run after collecting:  gimme-collect derive --what form,elo
Both are idempotent (upsert on natural keys) and cheap: a few thousand games.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

MODEL_VERSION = "elo-v1"

# Elo parameters per sport: K factor, home advantage in Elo points, whether to
# scale K by margin of victory (football, where blowouts carry information).
ELO = {
    "soccer": {"k": 20.0, "home": 60.0, "mov": False},
    "american_football": {"k": 20.0, "home": 55.0, "mov": True},
}


@dataclass
class GameRow:
    id: int
    sport: str
    competition_id: int
    season_id: int
    kickoff: datetime
    home_id: int
    away_id: int
    home_score: int
    away_score: int


def _final_games(conn: psycopg.Connection[Any]) -> list[GameRow]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT g.id, c.sport_id AS sport, g.competition_id, g.season_id, g.kickoff,
                   g.home_team_id, g.away_team_id, g.home_score, g.away_score
            FROM game g JOIN competition c ON c.id = g.competition_id
            WHERE g.status = 'final' AND g.home_score IS NOT NULL AND g.away_score IS NOT NULL
            ORDER BY g.kickoff, g.id
            """
        )
        return [
            GameRow(
                id=r["id"],
                sport=r["sport"],
                competition_id=r["competition_id"],
                season_id=r["season_id"],
                kickoff=r["kickoff"],
                home_id=r["home_team_id"],
                away_id=r["away_team_id"],
                home_score=r["home_score"],
                away_score=r["away_score"],
            )
            for r in cur.fetchall()
        ]


# ---------------------------------------------------------------- form


def compute_form(
    conn: psycopg.Connection[Any], *, last_n: int = 5, as_of: date | None = None
) -> int:
    """Last-N form per (team, season): 'WWDLW', points per game, margin, rest days."""
    as_of = as_of or datetime.now(UTC).date()
    games = _final_games(conn)
    history: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for g in games:
        for team_id, gf, ga in (
            (g.home_id, g.home_score, g.away_score),
            (g.away_id, g.away_score, g.home_score),
        ):
            result = "W" if gf > ga else "L" if gf < ga else "D"
            history[(team_id, g.season_id)].append(
                {"date": g.kickoff, "gf": gf, "ga": ga, "result": result, "sport": g.sport}
            )

    written = 0
    with conn.cursor() as cur:
        for (team_id, season_id), rows in history.items():
            recent = rows[-last_n:]
            wins = sum(r["result"] == "W" for r in recent)
            draws = sum(r["result"] == "D" for r in recent)
            losses = len(recent) - wins - draws
            points = 3 * wins + draws
            gf = sum(r["gf"] for r in recent)
            ga = sum(r["ga"] for r in recent)
            last_game = rows[-1]["date"]
            rest_days = (datetime.now(UTC) - last_game).days
            stats = {
                "games": len(recent),
                "wins": wins,
                "draws": draws,
                "losses": losses,
                "for": gf,
                "against": ga,
                "avg_for": round(gf / len(recent), 2),
                "avg_against": round(ga / len(recent), 2),
                "win_pct": round(wins / len(recent), 3),
                "season_games": len(rows),
                "last_game": last_game.isoformat(),
            }
            cur.execute(
                """
                INSERT INTO team_form (team_id, season_id, as_of, last_n, form, ppg,
                                       margin_per_game, rest_days, stats)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (team_id, season_id, as_of, last_n) DO UPDATE SET
                    form = EXCLUDED.form, ppg = EXCLUDED.ppg,
                    margin_per_game = EXCLUDED.margin_per_game, rest_days = EXCLUDED.rest_days,
                    stats = EXCLUDED.stats
                """,
                (
                    team_id,
                    season_id,
                    as_of,
                    last_n,
                    "".join(r["result"] for r in recent),
                    round(points / len(recent), 3),
                    round((gf - ga) / len(recent), 3),
                    rest_days,
                    Jsonb(stats),
                ),
            )
            written += 1
    conn.commit()
    return written


# ----------------------------------------------------------------- elo


def _expected(diff: float) -> float:
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def _mov_multiplier(margin: int, elo_diff_winner: float) -> float:
    """FiveThirtyEight-style margin-of-victory multiplier for football."""
    import math

    return math.log(abs(margin) + 1) * (2.2 / ((elo_diff_winner * 0.001) + 2.2))


def compute_elo(conn: psycopg.Connection[Any], *, as_of: date | None = None) -> int:
    """One Elo pool per sport, walked chronologically over every final game.

    Cross-competition games (Champions League, bowl games) connect the pools, which is
    what makes a league-vs-league comparison meaningful. Ratings start at 1500.
    """
    as_of = as_of or datetime.now(UTC).date()
    games = _final_games(conn)
    rating: dict[int, float] = defaultdict(lambda: 1500.0)
    games_played: dict[int, int] = defaultdict(int)
    sport_of: dict[int, str] = {}
    last_season: dict[int, int] = {}

    for g in games:
        params = ELO[g.sport]
        # New season: regress a third of the way back to the mean, so last year's
        # strength carries over without locking it in (rosters and coaches change).
        for team_id in (g.home_id, g.away_id):
            previous = last_season.get(team_id)
            if previous is not None and previous != g.season_id:
                rating[team_id] = rating[team_id] * (2 / 3) + 1500.0 / 3
            last_season[team_id] = g.season_id
        home, away = rating[g.home_id], rating[g.away_id]
        diff = home + params["home"] - away
        exp_home = _expected(diff)
        margin = g.home_score - g.away_score
        actual_home = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        k = params["k"]
        if params["mov"] and margin != 0:
            winner_diff = diff if margin > 0 else -diff
            k *= _mov_multiplier(margin, winner_diff)
        delta = k * (actual_home - exp_home)
        rating[g.home_id] = home + delta
        rating[g.away_id] = away - delta
        games_played[g.home_id] += 1
        games_played[g.away_id] += 1
        sport_of[g.home_id] = g.sport
        sport_of[g.away_id] = g.sport

    written = 0
    with conn.cursor() as cur:
        for team_id, value in rating.items():
            cur.execute(
                """
                INSERT INTO rating (subject_type, subject_id, as_of, kind, value, model_version)
                VALUES ('team', %s, %s, 'elo', %s, %s)
                ON CONFLICT (subject_type, subject_id, as_of, kind, model_version)
                    DO UPDATE SET value = EXCLUDED.value
                """,
                (team_id, as_of, round(value, 2), MODEL_VERSION),
            )
            written += 1
    conn.commit()
    return written


def run(database_url: str, what: set[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    with psycopg.connect(database_url) as conn:
        if "form" in what:
            out["form"] = compute_form(conn)
        if "elo" in what:
            out["elo"] = compute_elo(conn)
    return out
