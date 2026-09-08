"""nflverse adapter: NFL games since 1999 and weekly player stats.

    https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv
    https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv

games.csv carries the ESPN event id for every game, so historical rows land on the
same `game` records the ESPN collector creates. It also has closing spread, total
and moneylines, stadium, roof, surface, temperature, wind and rest days.
Player weekly stats are keyed by nflverse game_id, which games.csv maps to ESPN.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from gimme_collectors.models import (
    CompetitionRef,
    GameRecord,
    OddsRecord,
    PlayerGameStatRecord,
    PlayerRef,
    SeasonRef,
    SummaryRecord,
    TeamRef,
    VenueRef,
)

SOURCE_SLUG = "nflverse"
SOURCE_NAME = "nflverse"
BASE_URL = "https://github.com/nflverse/nflverse-data"
RATE_LIMIT_PER_MIN = 30

GAMES_URL = f"{BASE_URL}/releases/download/schedules/games.csv"


def player_stats_url(season: int) -> str:
    return f"{BASE_URL}/releases/download/stats_player/stats_player_week_{season}.csv"


COMPETITION = CompetitionRef(
    slug="nfl", name="NFL", sport="american_football", short_name="NFL", country="USA", level="pro"
)
UID_PREFIX = "s:20~l:28"
ET = ZoneInfo("America/New_York")

# nflverse abbreviation -> (ESPN team id, display name). Relocated franchises map to
# the current club so a team's history stays on one row.
TEAMS: dict[str, tuple[int, str]] = {
    "ARI": (22, "Arizona Cardinals"),
    "ATL": (1, "Atlanta Falcons"),
    "BAL": (33, "Baltimore Ravens"),
    "BUF": (2, "Buffalo Bills"),
    "CAR": (29, "Carolina Panthers"),
    "CHI": (3, "Chicago Bears"),
    "CIN": (4, "Cincinnati Bengals"),
    "CLE": (5, "Cleveland Browns"),
    "DAL": (6, "Dallas Cowboys"),
    "DEN": (7, "Denver Broncos"),
    "DET": (8, "Detroit Lions"),
    "GB": (9, "Green Bay Packers"),
    "HOU": (34, "Houston Texans"),
    "IND": (11, "Indianapolis Colts"),
    "JAX": (30, "Jacksonville Jaguars"),
    "KC": (12, "Kansas City Chiefs"),
    "LV": (13, "Las Vegas Raiders"),
    "OAK": (13, "Las Vegas Raiders"),
    "LAC": (24, "Los Angeles Chargers"),
    "SD": (24, "Los Angeles Chargers"),
    "LA": (14, "Los Angeles Rams"),
    "LAR": (14, "Los Angeles Rams"),
    "STL": (14, "Los Angeles Rams"),
    "MIA": (15, "Miami Dolphins"),
    "MIN": (16, "Minnesota Vikings"),
    "NE": (17, "New England Patriots"),
    "NO": (18, "New Orleans Saints"),
    "NYG": (19, "New York Giants"),
    "NYJ": (20, "New York Jets"),
    "PHI": (21, "Philadelphia Eagles"),
    "PIT": (23, "Pittsburgh Steelers"),
    "SF": (25, "San Francisco 49ers"),
    "SEA": (26, "Seattle Seahawks"),
    "TB": (27, "Tampa Bay Buccaneers"),
    "TEN": (10, "Tennessee Titans"),
    "WAS": (28, "Washington Commanders"),
    "WSH": (28, "Washington Commanders"),
}

ESPN_ABBR = {"LA": "LAR", "WAS": "WSH", "OAK": "LV", "SD": "LAC", "STL": "LAR"}


def team_ref(abbr: str) -> TeamRef | None:
    entry = TEAMS.get(abbr)
    if not entry:
        return None
    espn_id, name = entry
    return TeamRef(
        external_id=f"{UID_PREFIX}~t:{espn_id}",
        name=name,
        short_name=name.split(" ")[-1],
        abbreviation=ESPN_ABBR.get(abbr, abbr),
    )


def _f(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in {"", "NA", "NaN"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _i(value: Any) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def american_to_decimal(odds: float | None) -> float | None:
    if odds is None or odds == 0:
        return None
    return round(1 + odds / 100, 4) if odds > 0 else round(1 + 100 / abs(odds), 4)


def game_external_id(row: dict[str, Any]) -> str:
    espn = str(row.get("espn") or "").strip()
    return f"{UID_PREFIX}~e:{espn}" if espn else f"nflverse:{row['game_id']}"


def _kickoff(row: dict[str, Any]) -> datetime | None:
    day = str(row.get("gameday") or "").strip()
    time = str(row.get("gametime") or "").strip() or "13:00"
    if not day:
        return None
    try:
        local = datetime.strptime(f"{day} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
    except ValueError:
        return None
    return local.astimezone(UTC)


def parse_games(csv_text: str, seasons: Iterable[int] | None = None) -> list[GameRecord]:
    wanted = set(seasons) if seasons is not None else None
    games: list[GameRecord] = []
    for row in csv.DictReader(io.StringIO(csv_text)):
        season_year = _i(row.get("season"))
        if season_year is None or (wanted is not None and season_year not in wanted):
            continue
        home = team_ref(str(row.get("home_team") or ""))
        away = team_ref(str(row.get("away_team") or ""))
        kickoff = _kickoff(row)
        if not home or not away or kickoff is None:
            continue
        home_score, away_score = _i(row.get("home_score")), _i(row.get("away_score"))
        final = home_score is not None and away_score is not None
        game_type = str(row.get("game_type") or "REG")
        week = _i(row.get("week"))

        odds: list[OddsRecord] = []
        spread = _f(row.get("spread_line"))  # positive = home favored
        if spread is not None:
            for side, line, price in (
                ("home", -spread, american_to_decimal(_f(row.get("home_spread_odds")))),
                ("away", spread, american_to_decimal(_f(row.get("away_spread_odds")))),
            ):
                odds.append(
                    OddsRecord(
                        bookmaker="consensus",
                        market="spread",
                        selection=side,  # type: ignore[arg-type]
                        line=round(line, 2),
                        price=price,
                        captured_at=kickoff,
                        is_closing=True,
                    )
                )
        total = _f(row.get("total_line"))
        if total is not None:
            for side, col in (("over", "over_odds"), ("under", "under_odds")):
                odds.append(
                    OddsRecord(
                        bookmaker="consensus",
                        market="total",
                        selection=side,  # type: ignore[arg-type]
                        line=total,
                        price=american_to_decimal(_f(row.get(col))),
                        captured_at=kickoff,
                        is_closing=True,
                    )
                )
        for side, col in (("home", "home_moneyline"), ("away", "away_moneyline")):
            price = american_to_decimal(_f(row.get(col)))
            if price is not None:
                odds.append(
                    OddsRecord(
                        bookmaker="consensus",
                        market="h2h",
                        selection=side,  # type: ignore[arg-type]
                        price=price,
                        captured_at=kickoff,
                        is_closing=True,
                    )
                )

        weather = {
            k: v
            for k, v in {
                "temperature_f": _i(row.get("temp")),
                "wind_mph": _i(row.get("wind")),
                "roof": (row.get("roof") or "").strip() or None,
                "surface": (row.get("surface") or "").strip() or None,
            }.items()
            if v is not None
        }
        home_stats: dict[str, Any] = {}
        away_stats: dict[str, Any] = {}
        if _i(row.get("home_rest")) is not None:
            home_stats["restDays"] = _i(row.get("home_rest"))
        if _i(row.get("away_rest")) is not None:
            away_stats["restDays"] = _i(row.get("away_rest"))
        if row.get("home_qb_name"):
            home_stats["startingQb"] = row["home_qb_name"]
        if row.get("away_qb_name"):
            away_stats["startingQb"] = row["away_qb_name"]

        stadium = (row.get("stadium") or "").strip()
        games.append(
            GameRecord(
                external_id=game_external_id(row),
                competition=COMPETITION,
                season=SeasonRef(label=str(season_year), year=season_year),
                kickoff=kickoff,
                home=home,
                away=away,
                home_score=home_score if final else None,
                away_score=away_score if final else None,
                status="final" if final else "scheduled",
                status_detail="Final" if final else None,
                week=week,
                round=None if game_type == "REG" else game_type,
                neutral_site=str(row.get("location") or "").strip().lower() == "neutral",
                weather=weather,
                venue=VenueRef(name=stadium) if stadium else None,
                home_stats=home_stats,
                away_stats=away_stats,
                odds=odds,
            )
        )
    return games


# ------------------------------------------------------------ players

STAT_MAP = {
    "completions": "completions",
    "attempts": "passingAttempts",
    "passing_yards": "passingYards",
    "passing_tds": "passingTouchdowns",
    "passing_interceptions": "interceptions",
    "sacks_suffered": "sacksTaken",
    "passing_epa": "passingEpa",
    "passing_cpoe": "cpoe",
    "carries": "rushingAttempts",
    "rushing_yards": "rushingYards",
    "rushing_tds": "rushingTouchdowns",
    "rushing_epa": "rushingEpa",
    "receptions": "receptions",
    "targets": "targets",
    "receiving_yards": "receivingYards",
    "receiving_tds": "receivingTouchdowns",
    "receiving_epa": "receivingEpa",
    "target_share": "targetShare",
    "air_yards_share": "airYardsShare",
    "fumbles_lost_total": "fumblesLost",
    "fantasy_points_ppr": "fantasyPointsPpr",
}
CATEGORY_KEYS = {"passing": "passingAttempts", "rushing": "rushingAttempts", "receiving": "targets"}


def parse_player_stats(
    csv_text: str, game_ids: dict[str, str], *, season_types: set[str] | None = None
) -> list[SummaryRecord]:
    """Weekly rows grouped into one SummaryRecord per game.

    `game_ids` maps the nflverse game_id ('2025_09_CIN_CHI') to our external game id
    (built from games.csv). Rows for games not in the map are skipped.
    """
    by_game: dict[str, SummaryRecord] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        if season_types and str(row.get("season_type")) not in season_types:
            continue
        nfl_game = str(row.get("game_id") or "")
        external = game_ids.get(nfl_game)
        if not external:
            continue
        team = team_ref(str(row.get("team") or ""))
        if not team:
            continue
        stats: dict[str, Any] = {}
        for col, key in STAT_MAP.items():
            value = _f(row.get(col))
            if value is None:
                continue
            stats[key] = int(value) if value.is_integer() else round(value, 3)
        categories = [cat for cat, key in CATEGORY_KEYS.items() if stats.get(key)]
        if not categories:
            continue
        stats["categories"] = categories
        player = PlayerRef(
            external_id=f"nflverse:{row['player_id']}",
            full_name=str(row.get("player_display_name") or row.get("player_name") or ""),
            short_name=str(row.get("player_name") or "") or None,
            position=str(row.get("position") or "") or None,
            headshot_url=str(row.get("headshot_url") or "") or None,
        )
        record = by_game.get(external)
        if record is None:
            # home/away are unknown from this file; the writer resolves the game by id.
            record = SummaryRecord(
                game_external_id=external, competition=COMPETITION, home=team, away=team
            )
            by_game[external] = record
        record.players.append(PlayerGameStatRecord(team=team, player=player, stats=stats))
    return list(by_game.values())


def game_id_map(csv_text: str, seasons: Iterable[int] | None = None) -> dict[str, str]:
    """nflverse game_id -> our external game id, from games.csv."""
    wanted = set(seasons) if seasons is not None else None
    out: dict[str, str] = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        season_year = _i(row.get("season"))
        if season_year is None or (wanted is not None and season_year not in wanted):
            continue
        out[str(row["game_id"])] = game_external_id(row)
    return out
