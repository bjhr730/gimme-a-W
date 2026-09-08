"""football-data.co.uk adapter: soccer results, shots, corners and odds since the 1990s.

    https://www.football-data.co.uk/mmz4281/{yy}{yy+1}/{div}.csv     e.g. 2526/E0.csv

One CSV per league-season. Columns (the ones we use):
    Date, Time, HomeTeam, AwayTeam, FTHG, FTAG, HTHG, HTAG,
    HS, AS, HST, AST, HC, AC, HF, AF, HY, AY, HR, AR,
    B365H, B365D, B365A (opening), PSCH, PSCD, PSCA (Pinnacle closing),
    B365>2.5, B365<2.5, B365C>2.5, B365C<2.5

Team names are the site's short forms ("Man United", "Nott'm Forest"). The writer
matches them to ESPN teams by normalized name within the competition; see
`teamnames.py`. Unmatched names are reported, never guessed.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from gimme_collectors.models import (
    CompetitionRef,
    GameRecord,
    OddsRecord,
    SeasonRef,
    TeamRef,
)
from gimme_collectors.sources.espn import LEAGUES

SOURCE_SLUG = "football-data.co.uk"
SOURCE_NAME = "football-data.co.uk"
BASE_URL = "https://www.football-data.co.uk"
RATE_LIMIT_PER_MIN = 20
UK = ZoneInfo("Europe/London")

# our competition slug -> football-data division code
DIVISIONS: dict[str, str] = {
    "eng.1": "E0",
    "eng.2": "E1",
    "esp.1": "SP1",
    "ita.1": "I1",
    "ger.1": "D1",
    "fra.1": "F1",
    "ned.1": "N1",
    "por.1": "P1",
    "sco.1": "SC0",
    "bel.1": "B1",
    "tur.1": "T1",
    "gre.1": "G1",
}


def season_code(start_year: int) -> str:
    """2025 -> '2526'."""
    return f"{start_year % 100:02d}{(start_year + 1) % 100:02d}"


def season_label(start_year: int) -> str:
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def csv_url(slug: str, start_year: int) -> str:
    div = DIVISIONS[slug]
    return f"{BASE_URL}/mmz4281/{season_code(start_year)}/{div}.csv"


def competition_for(slug: str) -> CompetitionRef:
    lg = LEAGUES.get(slug)
    if lg is not None:
        return lg.competition()
    return CompetitionRef(slug=slug, name=slug, sport="soccer")


def _f(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _i(value: Any) -> int | None:
    f = _f(value)
    return int(f) if f is not None else None


def _kickoff(date_text: str, time_text: str) -> datetime | None:
    date_text = date_text.strip()
    time_text = (time_text or "").strip() or "15:00"
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%y %H:%M"):
        try:
            local = datetime.strptime(f"{date_text} {time_text}", fmt).replace(tzinfo=UK)
            return local.astimezone(UTC)
        except ValueError:
            continue
    return None


def _norm_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


def team_ref(name: str) -> TeamRef:
    """A name-only team reference; the writer resolves it against ESPN teams."""
    clean = name.strip()
    return TeamRef(external_id=f"fdcouk:{_norm_key(clean)}", name=clean, match_by_name=True)


def _team_stats(row: dict[str, Any], side: str) -> dict[str, Any]:
    cols = {
        "S": "totalShots",
        "ST": "shotsOnTarget",
        "C": "wonCorners",
        "F": "foulsCommitted",
        "Y": "yellowCards",
        "R": "redCards",
    }
    out: dict[str, Any] = {}
    for suffix, key in cols.items():
        value = _i(row.get(f"{side}{suffix}"))
        if value is not None:
            out[key] = value
    ht = _i(row.get(f"{side}THG"))
    if ht is not None:
        out["halfTimeGoals"] = ht
    return out


def _odds(row: dict[str, Any], captured_at: datetime) -> list[OddsRecord]:
    out: list[OddsRecord] = []

    def add(
        book: str,
        market: str,
        selection: str,
        col: str,
        line: float | None = None,
        closing: bool = False,
    ) -> None:
        price = _f(row.get(col))
        if price is None or price <= 1:
            return
        out.append(
            OddsRecord(
                bookmaker=book,
                market=market,  # type: ignore[arg-type]
                selection=selection,  # type: ignore[arg-type]
                line=line,
                price=price,
                captured_at=captured_at,
                is_closing=closing,
            )
        )

    # Bet365 opening 1X2 and totals
    add("Bet365", "h2h", "home", "B365H")
    add("Bet365", "h2h", "draw", "B365D")
    add("Bet365", "h2h", "away", "B365A")
    add("Bet365", "total", "over", "B365>2.5", 2.5)
    add("Bet365", "total", "under", "B365<2.5", 2.5)
    # Pinnacle closing 1X2 (the sharpest reference line), Bet365 closing totals
    add("Pinnacle", "h2h", "home", "PSCH", closing=True)
    add("Pinnacle", "h2h", "draw", "PSCD", closing=True)
    add("Pinnacle", "h2h", "away", "PSCA", closing=True)
    add("Bet365", "total", "over", "B365C>2.5", 2.5, closing=True)
    add("Bet365", "total", "under", "B365C<2.5", 2.5, closing=True)
    return out


def parse_season(csv_text: str, slug: str, start_year: int) -> list[GameRecord]:
    competition = competition_for(slug)
    season = SeasonRef(label=season_label(start_year), year=start_year)
    div = DIVISIONS.get(slug, slug)
    games: list[GameRecord] = []
    for row in csv.DictReader(io.StringIO(csv_text.lstrip("﻿"))):
        home_name = str(row.get("HomeTeam") or "").strip()
        away_name = str(row.get("AwayTeam") or "").strip()
        if not home_name or not away_name:
            continue
        kickoff = _kickoff(str(row.get("Date") or ""), str(row.get("Time") or ""))
        if kickoff is None:
            continue
        hg, ag = _i(row.get("FTHG")), _i(row.get("FTAG"))
        final = hg is not None and ag is not None
        home = team_ref(home_name)
        away = team_ref(away_name)
        external_id = (
            f"fdcouk:{div}:{season_code(start_year)}:{kickoff.date().isoformat()}:"
            f"{_norm_key(home_name)}:{_norm_key(away_name)}"
        )
        games.append(
            GameRecord(
                external_id=external_id,
                competition=competition,
                season=season,
                kickoff=kickoff,
                home=home,
                away=away,
                home_score=hg if final else None,
                away_score=ag if final else None,
                status="final" if final else "scheduled",
                status_detail="FT" if final else None,
                home_stats=_team_stats(row, "H"),
                away_stats=_team_stats(row, "A"),
                odds=_odds(row, kickoff),
            )
        )
    return games
