"""CollegeFootballData (CFBD) — college football games and betting lines.

    api.collegefootballdata.com/games?year=2026&week=3&classification=fbs
    api.collegefootballdata.com/lines?year=2026&week=3

College football is the one sport here still served entirely by ESPN's unofficial
API, and it shows: the status page has had 261 games and no predictions at all.
CFBD is the college equivalent of nflverse -- an openly documented,
key-authenticated API with a published OpenAPI schema -- so it is the source this
competition should have been on from the start.

Games land on the rows ESPN already created rather than beside them. Teams carry
`match_by_name`, so the writer resolves "Ohio State" to the team already in the
competition and binds the CFBD id to it; games are matched on season, teams and a
kickoff within 36 hours, which is what `find_game` exists for. After the first run
both are plain id lookups.

Requires a free key from collegefootballdata.com in CFBD_API_KEY.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

from gimme_collectors.models import (
    CompetitionRef,
    GameRecord,
    GameStatus,
    OddsRecord,
    SeasonRef,
    TeamRef,
)

SOURCE_SLUG = "cfbd"
SOURCE_NAME = "CollegeFootballData"
BASE_URL = "https://api.collegefootballdata.com"
RATE_LIMIT_PER_MIN = 60

COMPETITION = CompetitionRef(
    slug="college-football",
    name="NCAA Football (FBS)",
    sport="american_football",
    short_name="CFB",
    country="USA",
    level="college",
)

# A game that has kicked off but is not yet marked complete belongs to the live
# score job: CFBD carries no in-play state, so writing it from here would push a
# game that is under way back to "scheduled".
IN_FLIGHT_HOURS = 8


# ------------------------------------------------------------------- URLs


def _url(path: str, params: dict[str, Any]) -> str:
    clean = {k: v for k, v in params.items() if v is not None}
    return f"{BASE_URL}{path}?{urlencode(clean)}"


def games_url(year: int, week: int | None = None, season_type: str = "regular") -> str:
    return _url(
        "/games",
        {"year": year, "week": week, "seasonType": season_type, "classification": "fbs"},
    )


def lines_url(year: int, week: int | None = None, season_type: str = "regular") -> str:
    return _url("/lines", {"year": year, "week": week, "seasonType": season_type})


def auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


# ---------------------------------------------------------------- helpers


def game_external_id(game_id: Any) -> str:
    return f"cfbd:game:{game_id}"


def team_ref(team_id: Any, name: str) -> TeamRef:
    """Name-matched: the team already exists from ESPN, so never create a second one."""
    return TeamRef(external_id=f"cfbd:team:{team_id}", name=name, match_by_name=True)


def _kickoff(row: dict[str, Any]) -> datetime | None:
    text = str(row.get("startDate") or "").strip()
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def american_to_decimal(odds: Any) -> float | None:
    price = _float(odds)
    if price is None or price == 0:
        return None
    return round(1 + price / 100, 4) if price > 0 else round(1 + 100 / abs(price), 4)


def _status(row: dict[str, Any], kickoff: datetime, now: datetime) -> GameStatus | None:
    """None means "not this source's to write" -- see IN_FLIGHT_HOURS."""
    if row.get("completed"):
        return "final"
    if kickoff > now:
        return "scheduled"
    # Kicked off and not complete: either in play, or CFBD is behind on a result.
    # Neither is something to guess at from here.
    return None


# ---------------------------------------------------------------- parsing


def parse_games(
    payload: list[dict[str, Any]],
    *,
    now: datetime | None = None,
    odds: dict[str, list[OddsRecord]] | None = None,
) -> list[GameRecord]:
    """CFBD /games rows into GameRecords, skipping games currently in play."""
    now = now or datetime.now(UTC)
    odds = odds or {}
    out: list[GameRecord] = []
    for row in payload or []:
        kickoff = _kickoff(row)
        season = _int(row.get("season"))
        home_name = str(row.get("homeTeam") or "").strip()
        away_name = str(row.get("awayTeam") or "").strip()
        if kickoff is None or season is None or not home_name or not away_name:
            continue
        status = _status(row, kickoff, now)
        if status is None:
            continue
        final = status == "final"
        external_id = game_external_id(row.get("id"))
        conference_game = row.get("conferenceGame")
        out.append(
            GameRecord(
                external_id=external_id,
                competition=COMPETITION,
                season=SeasonRef(label=str(season), year=season),
                kickoff=kickoff,
                home=team_ref(row.get("homeId"), home_name),
                away=team_ref(row.get("awayId"), away_name),
                home_score=_int(row.get("homePoints")) if final else None,
                away_score=_int(row.get("awayPoints")) if final else None,
                status=status,
                status_detail="Final" if final else None,
                week=_int(row.get("week")),
                neutral_site=bool(row.get("neutralSite")),
                conference_game=None if conference_game is None else bool(conference_game),
                attendance=_int(row.get("attendance")),
                odds=odds.get(external_id, []),
            )
        )
    return out


def parse_lines(
    payload: list[dict[str, Any]], captured_at: datetime | None = None
) -> dict[str, list[OddsRecord]]:
    """Bookmaker lines keyed by this source's game external id.

    CFBD publishes a line per provider without the juice on spreads and totals, so
    those carry a line and no price. The spread is quoted from the home team's
    side, which is the opposite sign for the away selection.
    """
    captured_at = captured_at or datetime.now(UTC)
    out: dict[str, list[OddsRecord]] = {}
    for row in payload or []:
        key = game_external_id(row.get("id"))
        records: list[OddsRecord] = []
        for line in row.get("lines") or []:
            book = str(line.get("provider") or "").strip() or "unknown"
            for side, price in (
                ("home", line.get("homeMoneyline")),
                ("away", line.get("awayMoneyline")),
            ):
                decimal = american_to_decimal(price)
                if decimal is not None:
                    records.append(
                        OddsRecord(
                            bookmaker=book,
                            market="h2h",
                            selection=side,
                            price=decimal,
                            captured_at=captured_at,
                        )
                    )
            spread = _float(line.get("spread"))
            if spread is not None:
                for side, value in (("home", spread), ("away", -spread)):
                    records.append(
                        OddsRecord(
                            bookmaker=book,
                            market="spread",
                            selection=side,
                            line=value,
                            captured_at=captured_at,
                        )
                    )
            total = _float(line.get("overUnder"))
            if total is not None:
                for side in ("over", "under"):
                    records.append(
                        OddsRecord(
                            bookmaker=book,
                            market="total",
                            selection=side,
                            line=total,
                            captured_at=captured_at,
                        )
                    )
        if records:
            out[key] = records
    return out
