"""Read games and closing lines for one competition, oldest first."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row


@dataclass
class Game:
    id: int
    competition: str
    sport: str
    season_id: int
    season_label: str
    kickoff: datetime
    home_id: int
    away_id: int
    home_name: str
    away_name: str
    home_abbr: str | None
    away_abbr: str | None
    status: str
    home_score: int | None
    away_score: int | None
    neutral: bool
    week: int | None
    # market (closing where available, else latest): decimal prices and lines
    market: dict[str, float] = field(default_factory=dict)

    @property
    def final(self) -> bool:
        return (
            self.status == "final" and self.home_score is not None and self.away_score is not None
        )

    @property
    def margin(self) -> int:
        assert self.home_score is not None and self.away_score is not None
        return self.home_score - self.away_score


def load_games(conn: psycopg.Connection[Any], competition_slug: str) -> list[Game]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT g.id, c.slug AS competition, c.sport_id AS sport, g.season_id, s.label,
                   g.kickoff, g.home_team_id, g.away_team_id, ht.name AS home_name,
                   at.name AS away_name, ht.abbreviation AS home_abbr, at.abbreviation AS away_abbr,
                   g.status, g.home_score, g.away_score, g.neutral_site, g.week
            FROM game g
            JOIN competition c ON c.id = g.competition_id
            JOIN season s ON s.id = g.season_id
            JOIN team ht ON ht.id = g.home_team_id
            JOIN team at ON at.id = g.away_team_id
            WHERE c.slug = %s AND g.status IN ('final', 'scheduled', 'in_progress')
            ORDER BY g.kickoff, g.id
            """,
            (competition_slug,),
        )
        games = [
            Game(
                id=r["id"],
                competition=r["competition"],
                sport=r["sport"],
                season_id=r["season_id"],
                season_label=r["label"],
                kickoff=r["kickoff"],
                home_id=r["home_team_id"],
                away_id=r["away_team_id"],
                home_name=r["home_name"],
                away_name=r["away_name"],
                home_abbr=r["home_abbr"],
                away_abbr=r["away_abbr"],
                status=r["status"],
                home_score=r["home_score"],
                away_score=r["away_score"],
                neutral=bool(r["neutral_site"]),
                week=r["week"],
            )
            for r in cur.fetchall()
        ]
        if not games:
            return games
        by_id = {g.id: g for g in games}
        # One market row set per game: closing lines first, then the latest capture.
        cur.execute(
            """
            SELECT DISTINCT ON (o.game_id, o.market, o.selection)
                   o.game_id, o.market, o.selection, o.line, o.price
            FROM odds o
            JOIN game g ON g.id = o.game_id
            JOIN competition c ON c.id = g.competition_id
            WHERE c.slug = %s
            ORDER BY o.game_id, o.market, o.selection, o.is_closing DESC, o.captured_at DESC
            """,
            (competition_slug,),
        )
        for r in cur.fetchall():
            g = by_id.get(r["game_id"])
            if g is None:
                continue
            key = f"{r['market']}_{r['selection']}"
            if r["price"] is not None:
                g.market[f"{key}_price"] = float(r["price"])
            if r["line"] is not None:
                g.market[f"{key}_line"] = float(r["line"])
    return games


def market_probs(market: dict[str, float]) -> dict[str, float]:
    """De-vigged outcome probabilities from decimal prices (home/draw/away)."""
    raw = {}
    for side in ("home", "draw", "away"):
        price = market.get(f"h2h_{side}_price")
        if price and price > 1:
            raw[side] = 1.0 / price
    total = sum(raw.values())
    if not raw or total <= 0:
        return {}
    return {k: v / total for k, v in raw.items()}
