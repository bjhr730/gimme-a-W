"""ESPN adapter: scoreboard, teams and standings for soccer, NFL and college football.

ESPN's site API is unofficial. The response shapes are pinned by the fixtures under
tests/fixtures/espn; when ESPN changes something, those tests fail first.

Endpoints
    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/scoreboard?dates=YYYYMMDD
    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams
    site.api.espn.com/apis/v2/sports/{sport}/{league}/standings
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from gimme_collectors.models import (
    CollectResult,
    CompetitionRef,
    GameRecord,
    GameStatus,
    OddsRecord,
    SeasonRef,
    Sport,
    StandingRecord,
    TeamRecord,
    TeamRef,
    VenueRef,
)
from gimme_collectors.pipeline.fetch import Fetcher

SOURCE_SLUG = "espn"
SOURCE_NAME = "ESPN"
BASE_URL = "https://site.api.espn.com"
RATE_LIMIT_PER_MIN = 60

SITE = f"{BASE_URL}/apis/site/v2/sports"
SITE_V2 = f"{BASE_URL}/apis/v2/sports"


@dataclass(frozen=True)
class League:
    slug: str  # our competition slug == ESPN league slug
    espn_sport: str  # 'soccer' | 'football'
    name: str
    sport: Sport
    country: str | None = None
    level: str = "club"
    short_name: str | None = None
    scoreboard_params: dict[str, str] = field(default_factory=dict)
    teams_params: dict[str, str] = field(default_factory=dict)
    standings_params: dict[str, str] = field(default_factory=dict)
    # ESPN uid prefix for entities in this league: "s:20~l:28" (NFL), "s:600" (soccer).
    # Used to rebuild a uid when a payload only carries the numeric id.
    uid_prefix: str = "s:600"

    def competition(self) -> CompetitionRef:
        return CompetitionRef(
            slug=self.slug,
            name=self.name,
            sport=self.sport,
            short_name=self.short_name,
            country=self.country,
            level=self.level,
        )


def _soccer(slug: str, name: str, country: str | None, level: str = "club") -> League:
    return League(
        slug=slug, espn_sport="soccer", name=name, sport="soccer", country=country, level=level
    )


LEAGUES: dict[str, League] = {
    lg.slug: lg
    for lg in [
        League(
            slug="nfl",
            espn_sport="football",
            name="NFL",
            short_name="NFL",
            sport="american_football",
            country="USA",
            level="pro",
            uid_prefix="s:20~l:28",
        ),
        League(
            slug="college-football",
            espn_sport="football",
            name="NCAA Football (FBS)",
            short_name="CFB",
            sport="american_football",
            country="USA",
            level="college",
            scoreboard_params={"groups": "80", "limit": "400"},
            teams_params={"groups": "80", "limit": "400"},
            standings_params={"group": "80"},
            uid_prefix="s:20~l:23",
        ),
        _soccer("eng.1", "English Premier League", "England"),
        _soccer("eng.2", "English Championship", "England"),
        _soccer("esp.1", "Spanish LALIGA", "Spain"),
        _soccer("ita.1", "Italian Serie A", "Italy"),
        _soccer("ger.1", "German Bundesliga", "Germany"),
        _soccer("fra.1", "French Ligue 1", "France"),
        _soccer("ned.1", "Dutch Eredivisie", "Netherlands"),
        _soccer("por.1", "Portuguese Primeira Liga", "Portugal"),
        _soccer("usa.1", "MLS", "USA"),
        _soccer("mex.1", "Liga MX", "Mexico"),
        _soccer("arg.1", "Argentine Liga Profesional", "Argentina"),
        _soccer("bra.1", "Brazilian Serie A", "Brazil"),
        _soccer("uefa.champions", "UEFA Champions League", None),
        _soccer("uefa.europa", "UEFA Europa League", None),
        _soccer("uefa.europa.conf", "UEFA Conference League", None),
        _soccer("conmebol.libertadores", "Copa Libertadores", None),
        _soccer("fifa.world", "FIFA World Cup", None, level="international"),
        _soccer("uefa.euro", "UEFA European Championship", None, level="international"),
        _soccer("conmebol.america", "Copa America", None, level="international"),
    ]
}


def league(slug: str) -> League:
    """Known league, or an ad-hoc soccer league for any ESPN slug like 'tur.1'."""
    if slug in LEAGUES:
        return LEAGUES[slug]
    if "." in slug:
        return _soccer(slug, slug, None)
    known = ", ".join(sorted(LEAGUES))
    raise KeyError(f"Unknown league '{slug}'. Known: {known}. Soccer slugs like 'tur.1' also work.")


# ------------------------------------------------------------------ URLs


def _url(base: str, lg: League, path: str, params: dict[str, str]) -> str:
    url = f"{base}/{lg.espn_sport}/{lg.slug}/{path}"
    return f"{url}?{urlencode(params)}" if params else url


def scoreboard_url(lg: League, day: date | None = None) -> str:
    params = dict(lg.scoreboard_params)
    if day is not None:
        params["dates"] = day.strftime("%Y%m%d")
    return _url(SITE, lg, "scoreboard", params)


def teams_url(lg: League) -> str:
    return _url(SITE, lg, "teams", lg.teams_params)


def standings_url(lg: League) -> str:
    return _url(SITE_V2, lg, "standings", lg.standings_params)


# --------------------------------------------------------------- helpers

_SEASON_LABEL = re.compile(r"(\d{4})-(\d{2})")


def _num(value: Any) -> Any:
    """'45.4' -> 45.4, '7' -> 7, 'DDWWL' stays a string, None stays None."""
    if value is None or isinstance(value, bool | int | float):
        return value
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        try:
            return float(text)
        except ValueError:
            return text


def _int(value: Any) -> int | None:
    n = _num(value)
    if isinstance(n, bool) or not isinstance(n, int | float):
        return None
    return int(n)


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _date(value: Any) -> date | None:
    parsed = _dt(value)
    return parsed.date() if parsed else None


def season_from(node: dict[str, Any], fallback_year: int | None = None) -> SeasonRef:
    """Build a SeasonRef from any ESPN node carrying a `season` object.

    Soccer seasons are labelled '2026-27' (from displayName); US seasons '2026'.
    """
    s = node.get("season") or {}
    if isinstance(s, int):
        s = {"year": s}
    year = int(s.get("year") or fallback_year or datetime.now(UTC).year)
    display = str(s.get("displayName") or node.get("seasonDisplayName") or "")
    match = _SEASON_LABEL.search(display)
    label = match.group(0) if match else str(year)
    return SeasonRef(
        label=label,
        year=year,
        start_date=_date(s.get("startDate")),
        end_date=_date(s.get("endDate")),
    )


def team_external_id(t: dict[str, Any], lg: League) -> str:
    """ESPN numeric team ids repeat across sports (soccer 359 is Arsenal, football 359 is
    a college). The `uid` ("s:600~t:359", "s:20~l:28~t:17") is unique across everything,
    so it is the external id. Fall back to a sport-scoped id if uid is missing."""
    uid = t.get("uid")
    return str(uid) if uid else f"{lg.uid_prefix}~t:{t['id']}"


def _team(t: dict[str, Any], lg: League) -> TeamRef:
    logo = t.get("logo")
    if not logo:
        logos = t.get("logos") or []
        logo = logos[0].get("href") if logos else None
    name = t.get("displayName") or t.get("name") or t.get("location") or str(t["id"])
    return TeamRef(
        external_id=team_external_id(t, lg),
        name=name,
        short_name=t.get("shortDisplayName") or t.get("name"),
        abbreviation=t.get("abbreviation"),
        location=t.get("location"),
        logo_url=logo,
        color=t.get("color"),
        alt_color=t.get("alternateColor"),
    )


def _venue(v: dict[str, Any] | None, lg: League) -> VenueRef | None:
    if not v or not (v.get("fullName") or v.get("displayName")):
        return None
    address = v.get("address") or {}
    return VenueRef(
        external_id=f"{lg.espn_sport}:{v['id']}" if v.get("id") else None,
        name=v.get("fullName") or v.get("displayName"),
        city=address.get("city"),
        state=address.get("state"),
        country=address.get("country"),
        indoor=v.get("indoor"),
    )


_STATUS_BY_NAME: dict[str, GameStatus] = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "canceled",
    "STATUS_SUSPENDED": "suspended",
    "STATUS_ABANDONED": "suspended",
    "STATUS_FORFEIT": "final",
}
_STATUS_BY_STATE: dict[str, GameStatus] = {
    "pre": "scheduled",
    "in": "in_progress",
    "post": "final",
}


def game_status(status: dict[str, Any]) -> GameStatus:
    kind = status.get("type") or {}
    name = str(kind.get("name") or "")
    state = str(kind.get("state") or "")
    if name in _STATUS_BY_NAME:
        return _STATUS_BY_NAME[name]
    if name == "STATUS_DELAYED":
        return "in_progress" if (status.get("period") or 0) > 0 else "scheduled"
    return _STATUS_BY_STATE.get(state, "scheduled")


def _competitor_stats(comp: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for s in comp.get("statistics") or []:
        name = s.get("name") or s.get("abbreviation")
        if name:
            out[name] = _num(s.get("displayValue", s.get("value")))
    if comp.get("form"):
        out["form"] = comp["form"]
    for r in comp.get("records") or []:
        if r.get("type") == "total" and r.get("summary"):
            out["record"] = r["summary"]
    rank = (comp.get("curatedRank") or {}).get("current")
    if isinstance(rank, int) and 0 < rank < 99:
        out["rank"] = rank
    return out


def american_to_decimal(odds: Any) -> float | None:
    """'+142' -> 2.42, '-170' -> 1.588, 'EVEN' -> 2.0."""
    if odds is None:
        return None
    text = str(odds).strip().upper()
    if text in {"EVEN", "PK", "EV"}:
        return 2.0
    try:
        american = float(text)
    except ValueError:
        return None
    if american == 0:
        return None
    if american > 0:
        return round(1 + american / 100, 4)
    return round(1 + 100 / abs(american), 4)


def _close(side: dict[str, Any] | None) -> dict[str, Any]:
    if not side:
        return {}
    return side.get("close") or side.get("current") or {}


def parse_odds(comp: dict[str, Any], captured_at: datetime) -> list[OddsRecord]:
    records: list[OddsRecord] = []
    for o in comp.get("odds") or []:
        if not o:
            continue
        book = (o.get("provider") or {}).get("name") or "unknown"

        moneyline = o.get("moneyline") or {}
        for side in ("home", "away", "draw"):
            price = american_to_decimal(_close(moneyline.get(side)).get("odds"))
            if price is not None:
                records.append(
                    OddsRecord(
                        bookmaker=book,
                        market="h2h",
                        selection=side,  # type: ignore[arg-type]
                        price=price,
                        captured_at=captured_at,
                    )
                )

        spread = o.get("pointSpread") or {}
        for side in ("home", "away"):
            close = _close(spread.get(side))
            line = _num(close.get("line"))
            if isinstance(line, int | float):
                records.append(
                    OddsRecord(
                        bookmaker=book,
                        market="spread",
                        selection=side,  # type: ignore[arg-type]
                        line=float(line),
                        price=american_to_decimal(close.get("odds")),
                        captured_at=captured_at,
                    )
                )

        total = o.get("total") or {}
        for side in ("over", "under"):
            close = _close(total.get(side))
            # ESPN prefixes total lines with the side: "o44.5" / "u44.5"
            raw_line = str(close.get("line") or "").lstrip("ouOU")
            line = _num(raw_line or o.get("overUnder"))
            if isinstance(line, int | float):
                records.append(
                    OddsRecord(
                        bookmaker=book,
                        market="total",
                        selection=side,  # type: ignore[arg-type]
                        line=float(line),
                        price=american_to_decimal(close.get("odds")),
                        captured_at=captured_at,
                    )
                )
        if not total and isinstance(_num(o.get("overUnder")), int | float):
            line = float(_num(o.get("overUnder")))
            for side in ("over", "under"):
                records.append(
                    OddsRecord(
                        bookmaker=book,
                        market="total",
                        selection=side,  # type: ignore[arg-type]
                        line=line,
                        captured_at=captured_at,
                    )
                )
    return records


# --------------------------------------------------------------- parsers


def parse_scoreboard(
    payload: dict[str, Any], lg: League, captured_at: datetime | None = None
) -> list[GameRecord]:
    captured_at = captured_at or datetime.now(UTC)
    leagues = payload.get("leagues") or [{}]
    season = season_from(leagues[0], fallback_year=(payload.get("season") or {}).get("year"))
    competition = lg.competition()
    games: list[GameRecord] = []

    for ev in payload.get("events") or []:
        competitions = ev.get("competitions") or []
        if not competitions:
            continue
        c = competitions[0]
        competitors = c.get("competitors") or []
        home = next((x for x in competitors if x.get("homeAway") == "home"), None)
        away = next((x for x in competitors if x.get("homeAway") == "away"), None)
        if not home or not away:
            continue
        kickoff = _dt(c.get("date") or ev.get("date"))
        if kickoff is None:
            continue
        status_node = c.get("status") or ev.get("status") or {}
        status = game_status(status_node)
        kind = status_node.get("type") or {}
        weather_node = ev.get("weather") or {}
        weather = {
            k: v
            for k, v in {
                "summary": weather_node.get("displayValue"),
                "temperature_f": weather_node.get("temperature"),
                "condition_id": weather_node.get("conditionId"),
            }.items()
            if v is not None
        }
        scored = status != "scheduled"
        games.append(
            GameRecord(
                external_id=str(ev.get("uid") or f"{lg.espn_sport}:{ev['id']}"),
                competition=competition,
                season=season,
                kickoff=kickoff,
                home=_team(home["team"], lg),
                away=_team(away["team"], lg),
                home_score=_int(home.get("score")) if scored else None,
                away_score=_int(away.get("score")) if scored else None,
                status=status,
                status_detail=kind.get("shortDetail") or kind.get("detail"),
                period=_int(status_node.get("period")),
                clock=status_node.get("displayClock"),
                week=_int((ev.get("week") or {}).get("number")),
                neutral_site=bool(c.get("neutralSite")),
                conference_game=c.get("conferenceCompetition"),
                attendance=_int(c.get("attendance")) or None,
                weather=weather,
                venue=_venue(c.get("venue"), lg),
                home_stats=_competitor_stats(home),
                away_stats=_competitor_stats(away),
                odds=parse_odds(c, captured_at),
            )
        )
    return games


def parse_teams(payload: dict[str, Any], lg: League) -> list[TeamRecord]:
    node = ((payload.get("sports") or [{}])[0].get("leagues") or [{}])[0]
    season = season_from(node, fallback_year=_int(node.get("year")))
    competition = lg.competition()
    out: list[TeamRecord] = []
    for entry in node.get("teams") or []:
        t = entry.get("team") or entry
        if not t.get("id"):
            continue
        out.append(TeamRecord(competition=competition, season=season, team=_team(t, lg)))
    return out


def _standing_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """Flatten ESPN's stat list. First occurrence wins: CFB repeats names per split."""
    stats: dict[str, Any] = {}
    for s in entry.get("stats") or []:
        name = s.get("name")
        if not name or name in stats:
            continue
        value = s.get("value")
        if value is None:
            value = s.get("displayValue")
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        stats[name] = value
    return stats


def parse_standings(payload: dict[str, Any], lg: League, as_of: date) -> list[StandingRecord]:
    competition = lg.competition()
    top_year = payload.get("season")
    fallback_year = top_year if isinstance(top_year, int) else None
    found: list[tuple[str, SeasonRef, list[dict[str, Any]]]] = []

    def walk(node: dict[str, Any], group: str) -> None:
        standings = node.get("standings")
        if standings and standings.get("entries"):
            season = season_from(standings, fallback_year=fallback_year)
            found.append((group, season, standings["entries"]))
        for child in node.get("children") or []:
            walk(child, child.get("name") or group)

    walk(payload, "")
    single_group = len(found) <= 1
    out: list[StandingRecord] = []
    for group, season, entries in found:
        for position, entry in enumerate(entries, start=1):
            stats = _standing_entry(entry)
            wins, losses, draws = (
                _int(stats.get("wins")),
                _int(stats.get("losses")),
                _int(stats.get("ties")),
            )
            played = _int(stats.get("gamesPlayed"))
            if played is None and wins is not None:
                played = wins + (losses or 0) + (draws or 0)
            out.append(
                StandingRecord(
                    competition=competition,
                    season=season,
                    team=_team(entry["team"], lg),
                    as_of=as_of,
                    group_name="" if single_group else group,
                    rank=_int(stats.get("rank")) or position,
                    played=played,
                    wins=wins,
                    draws=draws,
                    losses=losses,
                    points=_int(stats.get("points")),
                    points_for=_int(stats.get("pointsFor")),
                    points_against=_int(stats.get("pointsAgainst")),
                    stats=stats,
                )
            )
    return out


# --------------------------------------------------------------- adapter


class EspnAdapter:
    def __init__(self, fetcher: Fetcher) -> None:
        self.fetcher = fetcher

    def scoreboard(self, lg: League, day: date | None, result: CollectResult) -> None:
        url = scoreboard_url(lg, day)
        payload, fetched = self.fetcher.get_json(url)
        result.fetched_urls.append(url)
        result.games.extend(parse_scoreboard(payload, lg, captured_at=fetched.fetched_at))

    def teams(self, lg: League, result: CollectResult) -> None:
        url = teams_url(lg)
        payload, _ = self.fetcher.get_json(url)
        result.fetched_urls.append(url)
        result.teams.extend(parse_teams(payload, lg))

    def standings(self, lg: League, as_of: date, result: CollectResult) -> None:
        url = standings_url(lg)
        payload, _ = self.fetcher.get_json(url)
        result.fetched_urls.append(url)
        result.standings.extend(parse_standings(payload, lg, as_of))

    def summaries(self, lg: League, days: list[date], result: CollectResult) -> None:
        """Game summaries for every event on the given days (box scores, lineups, FPI)."""
        from gimme_collectors.sources import espn_summary

        seen: set[str] = set()
        for day in days:
            url = scoreboard_url(lg, day)
            payload, _ = self.fetcher.get_json(url)
            if url not in result.fetched_urls:
                result.fetched_urls.append(url)
            for ev in payload.get("events") or []:
                event_id = str(ev.get("id") or "")
                if not event_id or event_id in seen:
                    continue
                seen.add(event_id)
                surl = espn_summary.summary_url(lg, event_id)
                body, fetched = self.fetcher.get_json(surl)
                result.fetched_urls.append(surl)
                summary = espn_summary.parse_summary(body, lg, captured_at=fetched.fetched_at)
                if summary is not None:
                    result.summaries.append(summary)

    def rosters(self, lg: League, result: CollectResult) -> None:
        """Current roster of every team in the league (one request per team)."""
        from gimme_collectors.sources import espn_summary

        url = teams_url(lg)
        payload, _ = self.fetcher.get_json(url)
        result.fetched_urls.append(url)
        for record in parse_teams(payload, lg):
            team_id = espn_summary.team_id_from_external(record.team.external_id)
            if not team_id:
                continue
            rurl = espn_summary.roster_url(lg, team_id)
            try:
                body, _ = self.fetcher.get_json(rurl)
            except httpx.HTTPStatusError as exc:
                # ESPN 404s a few rosters (relocated or inactive teams). Keep going.
                print(f"[{lg.slug}] roster skipped for team {team_id}: {exc.response.status_code}")
                continue
            result.fetched_urls.append(rurl)
            result.rosters.extend(espn_summary.parse_roster(body, lg))

    def collect(self, lg: League, *, kinds: set[str], days: list[date]) -> CollectResult:
        result = CollectResult()
        if "teams" in kinds:
            self.teams(lg, result)
        if "scoreboard" in kinds:
            for day in days:
                self.scoreboard(lg, day, result)
        if "standings" in kinds:
            self.standings(lg, max(days) if days else date.today(), result)
        if "summary" in kinds:
            self.summaries(lg, days, result)
        if "roster" in kinds:
            self.rosters(lg, result)
        return result
