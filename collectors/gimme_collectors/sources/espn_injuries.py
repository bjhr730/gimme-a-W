"""ESPN injury and availability reports.

    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/injuries
    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={id}

The league feed is one request for every team in the league and is the cheapest
way to keep a whole competition current; the game summary carries the same shape
under `injuries` for the two teams involved.

Coverage is a property of ESPN, not of this code: the NFL feed is complete
(roughly 800 entries in season), college football publishes only a handful, and
soccer publishes none at all. `gimme_predict.availability` treats a missing row
as "no report", never as "fit".
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from gimme_collectors.models import PlayerRef, PlayerStatusRecord, TeamRef
from gimme_collectors.sources.espn import SITE, League, _date, _team

# ESPN's own wording -> the verdict the models read, and the share of games a
# player in that bucket has historically been active for. `available` covers the
# rows ESPN keeps listing after a player is cleared.
AVAILABILITY = {
    "active": ("available", 1.0),
    "probable": ("available", 0.95),
    "day-to-day": ("questionable", 0.75),
    "questionable": ("questionable", 0.65),
    "doubtful": ("doubtful", 0.25),
    "out": ("out", 0.0),
    "injured reserve": ("out", 0.0),
    "ir": ("out", 0.0),
    "physically unable to perform": ("out", 0.0),
    "non football injury": ("out", 0.0),
    "suspension": ("out", 0.0),
    "suspended": ("out", 0.0),
}


def injuries_url(lg: League) -> str:
    return f"{SITE}/{lg.espn_sport}/{lg.slug}/injuries"


def classify(status: str) -> tuple[str, float]:
    """Map a source's status wording onto (availability, play probability)."""
    key = (status or "").strip().lower()
    if key in AVAILABILITY:
        return AVAILABILITY[key]
    for wording, verdict in AVAILABILITY.items():
        if wording in key:
            return verdict
    # An unknown status is a report of *something*, so treat it as a doubt rather
    # than silently clearing the player.
    return ("questionable", 0.65)


def _dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass
    try:
        return datetime.strptime(str(value), "%Y-%m-%dT%H:%MZ").replace(tzinfo=UTC)
    except ValueError:
        return None


_UID_LINK = re.compile(r"uid=([^&\s]+)")
_ID_LINK = re.compile(r"/id/(\d+)/")


def athlete_ref(a: dict[str, Any], lg: League) -> PlayerRef | None:
    """Build a PlayerRef from an injury-feed athlete.

    The league feed omits `id` and `uid` on the athlete and exposes them only
    through its links, so recover the same external id the roster collector
    writes ("s:20~l:28~a:4870808") instead of creating a second player row.
    """
    external_id = str(a.get("uid") or "")
    if not external_id:
        for link in a.get("links") or []:
            match = _UID_LINK.search(str(link.get("href") or ""))
            if match:
                external_id = match.group(1)
                break
    if not external_id:
        for link in a.get("links") or []:
            match = _ID_LINK.search(str(link.get("href") or ""))
            if match:
                external_id = f"{lg.uid_prefix}~a:{match.group(1)}"
                break
    if not external_id and a.get("id"):
        external_id = f"{lg.uid_prefix}~a:{a['id']}"
    if not external_id:
        return None
    position = a.get("position")
    if isinstance(position, dict):
        position = position.get("abbreviation") or position.get("name")
    headshot = a.get("headshot")
    if isinstance(headshot, dict):
        headshot = headshot.get("href")
    name = a.get("fullName") or a.get("displayName")
    if not name:
        name = f"{a.get('firstName') or ''} {a.get('lastName') or ''}".strip()
    if not name:
        return None
    return PlayerRef(
        external_id=external_id,
        full_name=name,
        short_name=a.get("shortName"),
        position=position,
        headshot_url=headshot,
    )


def _entry(
    node: dict[str, Any], lg: League, team: TeamRef | None, captured_at: datetime
) -> PlayerStatusRecord | None:
    athlete = node.get("athlete") or {}
    player = athlete_ref(athlete, lg)
    if player is None:
        return None
    if team is None:
        team_src = athlete.get("team") or {}
        if not team_src.get("id"):
            return None
        team = _team(team_src, lg)
    status = str(node.get("status") or (node.get("type") or {}).get("description") or "").strip()
    if not status:
        return None
    verdict, play_probability = classify(status)
    details = node.get("details") or {}
    side = details.get("side")
    return PlayerStatusRecord(
        competition=lg.competition(),
        team=team,
        player=player,
        status=status,
        availability=verdict,
        play_probability=play_probability,
        injury_type=details.get("type"),
        body_location=details.get("location"),
        detail=details.get("detail"),
        side=None if side in (None, "", "Not Specified") else side,
        return_date=_date(details.get("returnDate")),
        comment=node.get("shortComment") or node.get("longComment"),
        reported_at=_dt(node.get("date")) or captured_at,
    )


def parse_league_injuries(
    payload: dict[str, Any], lg: League, captured_at: datetime | None = None
) -> list[PlayerStatusRecord]:
    """The league-wide feed: a list of teams, each with a list of injuries."""
    captured_at = captured_at or datetime.now(UTC)
    out: list[PlayerStatusRecord] = []
    for team_node in payload.get("injuries") or []:
        for node in team_node.get("injuries") or []:
            record = _entry(node, lg, None, captured_at)
            if record is not None:
                out.append(record)
    return out


def parse_summary_injuries(
    payload: dict[str, Any], lg: League, captured_at: datetime | None = None
) -> list[PlayerStatusRecord]:
    """The `injuries` block of a game summary: one entry per team in the game."""
    captured_at = captured_at or datetime.now(UTC)
    out: list[PlayerStatusRecord] = []
    for team_node in payload.get("injuries") or []:
        team_src = team_node.get("team") or {}
        if not team_src.get("id"):
            continue
        team = _team(team_src, lg)
        for node in team_node.get("injuries") or []:
            record = _entry(node, lg, team, captured_at)
            if record is not None:
                out.append(record)
    return out
