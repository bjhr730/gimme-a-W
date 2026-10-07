"""football-data.org — soccer fixtures, results and tables, under an actual licence.

    api.football-data.org/v4/competitions/PL/matches?season=2026
    api.football-data.org/v4/competitions/PL/standings

This replaces ESPN for soccer. ESPN's endpoint was undocumented and
unversioned, nothing granted permission to use it, and in one month it changed
shape twice without saying so -- first dropping date ranges, then quietly
answering single future dates with an empty list. football-data.org is
documented, versioned, issues a personal token, and says what the free tier may
be used for.

It is also far cheaper to read: one request returns a competition's whole
season, fixtures and results together, where ESPN needed a request per month and
could not be asked about the future at all.

What it does not give on the free tier: betting odds, and any box score beyond
the scoreline -- no shots, no corners, no lineups. Those come from
football-data.co.uk for the eight domestic leagues it covers. The Champions
League therefore has results and tables but no team-count markets.

Slugs are unchanged from the ESPN era on purpose, so everything already stored
-- teams, games, predictions -- stays attached to the same competitions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from gimme_collectors.models import (
    CompetitionRef,
    GameRecord,
    GameStatus,
    SeasonRef,
    StandingRecord,
    TeamRef,
)

SOURCE_SLUG = "football-data"
SOURCE_NAME = "football-data.org"
BASE_URL = "https://api.football-data.org/v4"
# The free tier allows ten calls a minute and says so in the response headers.
RATE_LIMIT_PER_MIN = 10

# our slug -> (their code, name, country). Names match what is already stored.
COMPETITIONS: dict[str, tuple[str, str, str | None]] = {
    "eng.1": ("PL", "English Premier League", "England"),
    "eng.2": ("ELC", "English Championship", "England"),
    "esp.1": ("PD", "Spanish LALIGA", "Spain"),
    "ita.1": ("SA", "Italian Serie A", "Italy"),
    "ger.1": ("BL1", "German Bundesliga", "Germany"),
    "fra.1": ("FL1", "French Ligue 1", "France"),
    "ned.1": ("DED", "Dutch Eredivisie", "Netherlands"),
    "por.1": ("PPL", "Portuguese Primeira Liga", "Portugal"),
    "uefa.champions": ("CL", "UEFA Champions League", None),
}

STATUS: dict[str, GameStatus] = {
    "FINISHED": "final",
    "AWARDED": "final",
    "IN_PLAY": "in_progress",
    "PAUSED": "in_progress",
    "POSTPONED": "postponed",
    "SUSPENDED": "suspended",
    "CANCELLED": "canceled",
    "CANCELED": "canceled",
    "SCHEDULED": "scheduled",
    "TIMED": "scheduled",
}


def active_slugs() -> list[str]:
    return sorted(COMPETITIONS)


def competition(slug: str) -> CompetitionRef:
    code, name, country = COMPETITIONS[slug]
    del code
    return CompetitionRef(slug=slug, name=name, sport="soccer", country=country, level="club")


# ------------------------------------------------------------------- URLs


def matches_url(slug: str, season: int | None = None) -> str:
    code = COMPETITIONS[slug][0]
    url = f"{BASE_URL}/competitions/{code}/matches"
    return f"{url}?season={season}" if season else url


def standings_url(slug: str, season: int | None = None) -> str:
    code = COMPETITIONS[slug][0]
    url = f"{BASE_URL}/competitions/{code}/standings"
    return f"{url}?season={season}" if season else url


def auth_headers(token: str) -> dict[str, str]:
    return {"X-Auth-Token": token}


# ---------------------------------------------------------------- helpers


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _kickoff(text: Any) -> datetime | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def season_ref(node: dict[str, Any]) -> SeasonRef | None:
    """'2026-08-21'..'2027-05-30' -> 2026-27; a season inside one year -> 2026."""
    start = str((node or {}).get("startDate") or "")[:10]
    end = str((node or {}).get("endDate") or "")[:10]
    if len(start) != 10:
        return None
    year = int(start[:4])
    label = str(year)
    if len(end) == 10 and int(end[:4]) > year:
        label = f"{year}-{int(end[:4]) % 100:02d}"
    return SeasonRef(label=label, year=year)


def team_ref(node: dict[str, Any]) -> TeamRef | None:
    """Name-matched onto the team already stored, never a second copy of it."""
    name = str((node or {}).get("name") or "").strip()
    team_id = (node or {}).get("id")
    if not name or team_id is None:
        return None
    short = str(node.get("shortName") or "").strip() or None
    return TeamRef(
        external_id=f"football-data:team:{team_id}",
        name=name,
        short_name=short,
        abbreviation=str(node.get("tla") or "").strip() or None,
        match_by_name=True,
    )


def game_external_id(match_id: Any) -> str:
    return f"football-data:match:{match_id}"


# ---------------------------------------------------------------- parsing


def parse_matches(payload: dict[str, Any], slug: str) -> list[GameRecord]:
    comp = competition(slug)
    out: list[GameRecord] = []
    for match in (payload or {}).get("matches") or []:
        kickoff = _kickoff(match.get("utcDate"))
        season = season_ref(match.get("season") or {})
        home = team_ref(match.get("homeTeam") or {})
        away = team_ref(match.get("awayTeam") or {})
        if kickoff is None or season is None or home is None or away is None:
            continue
        status = STATUS.get(str(match.get("status") or "").upper(), "scheduled")
        full = ((match.get("score") or {}).get("fullTime")) or {}
        final = status == "final"
        stage = str(match.get("stage") or "").strip()
        group = str(match.get("group") or "").strip()
        out.append(
            GameRecord(
                external_id=game_external_id(match.get("id")),
                competition=comp,
                season=season,
                kickoff=kickoff,
                home=home,
                away=away,
                home_score=_int(full.get("home")) if final else None,
                away_score=_int(full.get("away")) if final else None,
                status=status,
                status_detail="Final" if final else None,
                week=_int(match.get("matchday")),
                # REGULAR_SEASON says nothing; a cup round does
                round=group or (stage if stage and stage != "REGULAR_SEASON" else None),
            )
        )
    return out


def parse_standings(
    payload: dict[str, Any], slug: str, as_of: date | None = None
) -> list[StandingRecord]:
    comp = competition(slug)
    season = season_ref((payload or {}).get("season") or {})
    if season is None:
        return []
    as_of = as_of or datetime.now(UTC).date()
    out: list[StandingRecord] = []
    for table in (payload or {}).get("standings") or []:
        # the same table is published as TOTAL, HOME and AWAY splits
        if str(table.get("type") or "").upper() != "TOTAL":
            continue
        group = str(table.get("group") or "").strip()
        for row in table.get("table") or []:
            team = team_ref(row.get("team") or {})
            if team is None:
                continue
            out.append(
                StandingRecord(
                    competition=comp,
                    season=season,
                    team=team,
                    as_of=as_of,
                    group_name=group,
                    rank=_int(row.get("position")),
                    played=_int(row.get("playedGames")),
                    wins=_int(row.get("won")),
                    draws=_int(row.get("draw")),
                    losses=_int(row.get("lost")),
                    points=_int(row.get("points")),
                    points_for=_int(row.get("goalsFor")),
                    points_against=_int(row.get("goalsAgainst")),
                )
            )
    return out
