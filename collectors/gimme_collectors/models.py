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


class PlayerRef(BaseModel):
    external_id: str
    full_name: str
    short_name: str | None = None
    position: str | None = None
    jersey: str | None = None
    birth_date: date | None = None
    nationality: str | None = None
    height_cm: int | None = None
    weight_kg: int | None = None
    headshot_url: str | None = None


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


class RosterRecord(BaseModel):
    """A player on a team's roster. `season` may be None when the source does not
    say; the writer then uses the competition's latest season."""

    competition: CompetitionRef
    team: TeamRef
    player: PlayerRef
    season: SeasonRef | None = None
    jersey: str | None = None
    position: str | None = None


class PlayerGameStatRecord(BaseModel):
    team: TeamRef
    player: PlayerRef
    stats: dict[str, Any] = Field(default_factory=dict)


class PickRecord(BaseModel):
    """A third-party prediction for one game (ESPN FPI, an SI expert, ...)."""

    author: str
    pick_team: TeamRef | None = None
    win_probability: float | None = None  # for pick_team
    spread: float | None = None
    total: float | None = None
    url: str | None = None
    published_at: datetime | None = None


class SummaryRecord(BaseModel):
    """Everything a game-summary endpoint adds on top of the scoreboard row.
    The game must already exist (matched by `game_external_id`)."""

    game_external_id: str
    competition: CompetitionRef
    home: TeamRef
    away: TeamRef
    status: GameStatus | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_stats: dict[str, Any] = Field(default_factory=dict)
    away_stats: dict[str, Any] = Field(default_factory=dict)
    players: list[PlayerGameStatRecord] = Field(default_factory=list)
    lineups: list[RosterRecord] = Field(default_factory=list)
    picks: list[PickRecord] = Field(default_factory=list)


class CollectResult(BaseModel):
    games: list[GameRecord] = Field(default_factory=list)
    teams: list[TeamRecord] = Field(default_factory=list)
    standings: list[StandingRecord] = Field(default_factory=list)
    rosters: list[RosterRecord] = Field(default_factory=list)
    summaries: list[SummaryRecord] = Field(default_factory=list)
    fetched_urls: list[str] = Field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "games": len(self.games),
            "teams": len(self.teams),
            "standings": len(self.standings),
            "rosters": len(self.rosters),
            "summaries": len(self.summaries),
            "player_stats": sum(len(s.players) for s in self.summaries),
            "requests": len(self.fetched_urls),
        }
