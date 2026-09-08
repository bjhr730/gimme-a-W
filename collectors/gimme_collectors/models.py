"""Normalized records every source adapter emits.

These are the contract between adapters (parse) and the writer (upsert).
Names mirror the Drizzle schema in packages/db/src/schema.ts.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Sport = Literal["soccer", "american_football"]
GameStatus = Literal["scheduled", "in_progress", "final", "postponed", "canceled", "suspended"]


class CompetitionRef(BaseModel):
    slug: str  # 'eng.1', 'nfl', 'college-football'
    name: str
    sport: Sport
    short_name: str | None = None
    country: str | None = None
    level: str | None = None  # 'club' | 'international' | 'college' | 'pro'


class SeasonRef(BaseModel):
    label: str  # '2026-27' or '2026'
    year: int
    start_date: date | None = None
    end_date: date | None = None


class TeamRef(BaseModel):
    external_id: str
    name: str
    short_name: str | None = None
    abbreviation: str | None = None
    location: str | None = None
    logo_url: str | None = None
    color: str | None = None
    alt_color: str | None = None


class VenueRef(BaseModel):
    external_id: str | None = None
    name: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    indoor: bool | None = None


class OddsRecord(BaseModel):
    bookmaker: str
    market: Literal["h2h", "spread", "total"]
    selection: Literal["home", "away", "draw", "over", "under"]
    line: float | None = None
    price: float | None = None  # decimal odds
    captured_at: datetime


class GameRecord(BaseModel):
    external_id: str
    competition: CompetitionRef
    season: SeasonRef
    kickoff: datetime
    home: TeamRef
    away: TeamRef
    home_score: int | None = None
    away_score: int | None = None
    status: GameStatus = "scheduled"
    status_detail: str | None = None
    period: int | None = None
    clock: str | None = None
    week: int | None = None
    round: str | None = None
    neutral_site: bool = False
    conference_game: bool | None = None
    attendance: int | None = None
    weather: dict[str, Any] = Field(default_factory=dict)
    venue: VenueRef | None = None
    home_stats: dict[str, Any] = Field(default_factory=dict)
    away_stats: dict[str, Any] = Field(default_factory=dict)
    odds: list[OddsRecord] = Field(default_factory=list)


class TeamRecord(BaseModel):
    competition: CompetitionRef
    season: SeasonRef
    team: TeamRef
    group_name: str | None = None


class StandingRecord(BaseModel):
    competition: CompetitionRef
    season: SeasonRef
    team: TeamRef
    as_of: date
    group_name: str = ""
    rank: int | None = None
    played: int | None = None
    wins: int | None = None
    draws: int | None = None
    losses: int | None = None
    points: int | None = None
    points_for: int | None = None
    points_against: int | None = None
    stats: dict[str, Any] = Field(default_factory=dict)


class CollectResult(BaseModel):
    games: list[GameRecord] = Field(default_factory=list)
    teams: list[TeamRecord] = Field(default_factory=list)
    standings: list[StandingRecord] = Field(default_factory=list)
    fetched_urls: list[str] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "games": len(self.games),
            "teams": len(self.teams),
            "standings": len(self.standings),
            "requests": len(self.fetched_urls),
        }
