"""Player and team box-score history, walked in kickoff order into rolling features.

Football rows come from player_game_stat (nflverse weekly stats and ESPN box scores share
the same keys: passingYards, rushingAttempts, targets, receivingYards, ...). Soccer
team rows come from team_game_stat (shotsOnTarget, wonCorners) and player rows from
lineups (totalGoals, totalShots, starter).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

from gimme_predict.data import Game

ROLL_N = 8


@dataclass
class PlayerGame:
    game_id: int
    kickoff: datetime
    season_id: int
    team_id: int
    opp_id: int
    home: bool
    player_id: int
    name: str
    position: str | None
    stats: dict[str, Any]


def load_player_games(conn: psycopg.Connection[Any], competition_slug: str) -> list[PlayerGame]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT s.game_id, g.kickoff, g.season_id, s.team_id,
                   CASE WHEN s.team_id = g.home_team_id THEN g.away_team_id
                        ELSE g.home_team_id END AS opp_id,
                   (s.team_id = g.home_team_id) AS home,
                   s.player_id, p.full_name, p.position, s.stats
            FROM player_game_stat s
            JOIN game g ON g.id = s.game_id
            JOIN competition c ON c.id = g.competition_id
            JOIN player p ON p.id = s.player_id
            WHERE c.slug = %s AND g.status = 'final'
            ORDER BY g.kickoff, g.id, s.player_id
            """,
            (competition_slug,),
        )
        return [
            PlayerGame(
                game_id=r["game_id"],
                kickoff=r["kickoff"],
                season_id=r["season_id"],
                team_id=r["team_id"],
                opp_id=r["opp_id"],
                home=bool(r["home"]),
                player_id=r["player_id"],
                name=r["full_name"],
                position=r["position"],
                stats=r["stats"] or {},
            )
            for r in cur.fetchall()
        ]


def load_team_games(conn: psycopg.Connection[Any], competition_slug: str) -> list[dict[str, Any]]:
    """One row per (game, team) with the team's box-score stats, final games only."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT s.game_id, g.kickoff, g.season_id, s.team_id,
                   CASE WHEN s.team_id = g.home_team_id THEN g.away_team_id
                        ELSE g.home_team_id END AS opp_id,
                   (s.team_id = g.home_team_id) AS home, s.stats
            FROM team_game_stat s
            JOIN game g ON g.id = s.game_id
            JOIN competition c ON c.id = g.competition_id
            WHERE c.slug = %s AND g.status = 'final'
            ORDER BY g.kickoff, g.id
            """,
            (competition_slug,),
        )
        return [dict(r) for r in cur.fetchall()]


def load_rosters(
    conn: psycopg.Connection[Any], team_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    """Latest-season roster per team: player id, name, position."""
    if not team_ids:
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (r.team_id, r.player_id)
                   r.team_id, r.player_id, p.full_name, COALESCE(r.position, p.position) AS position
            FROM roster r
            JOIN player p ON p.id = r.player_id
            JOIN season s ON s.id = r.season_id
            WHERE r.team_id = ANY(%s)
            ORDER BY r.team_id, r.player_id, s.year DESC
            """,
            (team_ids,),
        )
        out: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for r in cur.fetchall():
            out[r["team_id"]].append(dict(r))
    return out


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------- rolling state


@dataclass
class Rolling:
    """Rolling sums per key over the last N games."""

    n: int = ROLL_N
    window: deque[dict[str, float]] = field(default_factory=deque)

    def push(self, values: dict[str, float]) -> None:
        self.window.append(values)
        while len(self.window) > self.n:
            self.window.popleft()

    def mean(self, key: str, default: float = 0.0) -> float:
        if not self.window:
            return default
        return sum(v.get(key, 0.0) for v in self.window) / len(self.window)

    @property
    def games(self) -> int:
        return len(self.window)


FOOTBALL_KEYS = {
    "passingAttempts": "attempts",
    "passingYards": "passYds",
    "passingTouchdowns": "passTd",
    "rushingAttempts": "carries",
    "rushingYards": "rushYds",
    "rushingTouchdowns": "rushTd",
    "targets": "targets",
    "receptions": "receptions",
    "receivingYards": "recYds",
    "receivingTouchdowns": "recTd",
}


def football_values(stats: dict[str, Any]) -> dict[str, float]:
    out = {short: _num(stats.get(key)) for key, short in FOOTBALL_KEYS.items()}
    out["td"] = out["rushTd"] + out["recTd"]
    out["touches"] = out["carries"] + out["targets"]
    return out


def soccer_values(stats: dict[str, Any]) -> dict[str, float]:
    return {
        "goals": _num(stats.get("totalGoals")),
        "shots": _num(stats.get("totalShots")),
        "sot": _num(stats.get("shotsOnTarget")),
        "app": 1.0
        if (stats.get("starter") or stats.get("subbedIn") or _num(stats.get("appearances")) > 0)
        else 0.0,
        "start": 1.0 if stats.get("starter") else 0.0,
    }


@dataclass
class PlayerRow:
    """Pre-game rolling features for one player in one game, plus the outcome."""

    pg: PlayerGame
    player: Rolling
    team: Rolling  # team totals of the same keys
    opp_allowed: Rolling  # what opponents' defences allowed, per game
    game: Game | None = None

    def share(self, key: str) -> float:
        team = self.team.mean(key)
        return self.player.mean(key) / team if team > 0 else 0.0


def walk_football(
    rows: list[PlayerGame], games_by_id: dict[int, Game]
) -> tuple[list[PlayerRow], dict[int, Rolling], dict[int, Rolling], dict[int, Rolling]]:
    """Walk player rows in kickoff order and emit pre-game feature rows.

    Returns the rows plus the final rolling state for players, teams and defences,
    which the live predictor uses for upcoming games.
    """
    players: dict[int, Rolling] = defaultdict(Rolling)
    teams: dict[int, Rolling] = defaultdict(Rolling)
    allowed: dict[int, Rolling] = defaultdict(Rolling)
    out: list[PlayerRow] = []
    # group by game so team totals update once per game, after all players are emitted
    by_game: dict[int, list[PlayerGame]] = defaultdict(list)
    order: list[int] = []
    for pg in rows:
        if pg.game_id not in by_game:
            order.append(pg.game_id)
        by_game[pg.game_id].append(pg)
    for game_id in order:
        pgs = by_game[game_id]
        for pg in pgs:
            out.append(
                PlayerRow(
                    pg=pg,
                    player=_snapshot(players[pg.player_id]),
                    team=_snapshot(teams[pg.team_id]),
                    opp_allowed=_snapshot(allowed[pg.opp_id]),
                    game=games_by_id.get(game_id),
                )
            )
        totals: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        for pg in pgs:
            values = football_values(pg.stats)
            players[pg.player_id].push(values)
            for k, v in values.items():
                totals[pg.team_id][k] += v
        for team_id, values in totals.items():
            teams[team_id].push(dict(values))
        # what each defence allowed = the other team's totals
        team_ids = list(totals)
        for team_id in team_ids:
            for other in team_ids:
                if other != team_id:
                    allowed[team_id].push(dict(totals[other]))
    return out, players, teams, allowed


def _snapshot(r: Rolling) -> Rolling:
    s = Rolling(n=r.n)
    s.window = deque(r.window)
    return s
