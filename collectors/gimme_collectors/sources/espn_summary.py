"""ESPN game summary and team roster parsers.

    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/summary?event={id}
    site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{id}/roster

The summary carries what the scoreboard lacks: full team box-score stats for
football, per-player stats (passing / rushing / receiving yards, goals, shots on
target), soccer lineups with starters and substitutions, and ESPN's FPI matchup
predictor. Shapes are pinned by tests/fixtures/espn/*-summary*.json.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from gimme_collectors.models import (
    PickRecord,
    PlayerGameStatRecord,
    PlayerRef,
    RosterRecord,
    SummaryRecord,
    TeamRef,
)
from gimme_collectors.sources.espn import (
    SITE,
    League,
    _date,
    _int,
    _num,
    _team,
    game_status,
    season_from,
    team_external_id,
)

_EVENT_ID = re.compile(r"(\d+)$")


def event_id_from_external(external_id: str) -> str | None:
    """'s:20~l:23~e:401864494' -> '401864494'; 'football:401864494' -> '401864494'."""
    match = _EVENT_ID.search(external_id)
    return match.group(1) if match else None


def summary_url(lg: League, event_id: str) -> str:
    return f"{SITE}/{lg.espn_sport}/{lg.slug}/summary?event={event_id}"


def roster_url(lg: League, team_id: str) -> str:
    return f"{SITE}/{lg.espn_sport}/{lg.slug}/teams/{team_id}/roster"


def team_id_from_external(external_id: str) -> str | None:
    """'s:20~l:28~t:26' -> '26'; 'soccer:359' -> '359'."""
    match = re.search(r"~t:(\d+)|:(\d+)$", external_id)
    if not match:
        return None
    return match.group(1) or match.group(2)


# ------------------------------------------------------------- players


def _player(a: dict[str, Any], lg: League, position: str | None = None) -> PlayerRef:
    uid = a.get("uid")
    external_id = str(uid) if uid else f"{lg.uid_prefix}~a:{a['id']}"
    pos = a.get("position")
    if isinstance(pos, dict):
        pos = pos.get("abbreviation") or pos.get("name")
    headshot = a.get("headshot")
    if isinstance(headshot, dict):
        headshot = headshot.get("href")
    height_in = a.get("height")
    weight_lb = a.get("weight")
    birth_place = a.get("birthPlace") or {}
    return PlayerRef(
        external_id=external_id,
        full_name=a.get("fullName") or a.get("displayName") or str(a["id"]),
        short_name=a.get("shortName"),
        position=position or (str(pos) if pos else None),
        jersey=str(a["jersey"]) if a.get("jersey") else None,
        birth_date=_date(a.get("dateOfBirth")),
        nationality=a.get("citizenship") or birth_place.get("country"),
        height_cm=round(float(height_in) * 2.54) if height_in else None,
        weight_kg=round(float(weight_lb) * 0.45359) if weight_lb else None,
        headshot_url=str(headshot) if headshot else None,
    )


def parse_roster(payload: dict[str, Any], lg: League) -> list[RosterRecord]:
    team = _team(payload["team"], lg)
    season = season_from(payload) if payload.get("season") else None
    competition = lg.competition()
    groups = payload.get("athletes") or []
    athletes: list[dict[str, Any]] = []
    for g in groups:
        if isinstance(g, dict) and "items" in g:  # football: grouped by unit
            athletes.extend(g["items"])
        elif isinstance(g, dict):  # soccer: flat list
            athletes.append(g)
    out: list[RosterRecord] = []
    for a in athletes:
        if not a.get("id"):
            continue
        p = _player(a, lg)
        out.append(
            RosterRecord(
                competition=competition,
                team=team,
                player=p,
                season=season,
                jersey=p.jersey,
                position=p.position,
            )
        )
    return out


# -------------------------------------------------------------- summary


def _team_stats(node: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for s in node.get("statistics") or []:
        name = s.get("name") or s.get("abbreviation")
        if name:
            out[name] = _num(s.get("displayValue", s.get("value")))
    return out


def _split_pair(key: str, value: Any) -> dict[str, Any]:
    """'completions/passingAttempts' with '21/32' -> {completions: 21, passingAttempts: 32}."""
    if "/" in key and isinstance(value, str) and "/" in value:
        names = key.split("/")
        parts = value.split("/")
        if len(names) == len(parts):
            return {n: _num(v) for n, v in zip(names, parts, strict=True)}
    return {key: _num(value)}


def _football_players(boxscore: dict[str, Any], lg: League) -> list[PlayerGameStatRecord]:
    out: dict[str, PlayerGameStatRecord] = {}
    for block in boxscore.get("players") or []:
        team = _team(block["team"], lg)
        for cat in block.get("statistics") or []:
            keys = cat.get("keys") or cat.get("labels") or []
            for entry in cat.get("athletes") or []:
                athlete = entry.get("athlete") or {}
                if not athlete.get("id"):
                    continue
                player = _player(athlete, lg)
                stats: dict[str, Any] = {}
                for key, value in zip(keys, entry.get("stats") or [], strict=False):
                    stats.update(_split_pair(key, value))
                rec = out.get(player.external_id)
                if rec is None:
                    rec = PlayerGameStatRecord(team=team, player=player, stats={})
                    out[player.external_id] = rec
                rec.stats.update(stats)
                rec.stats.setdefault("categories", [])
                if cat.get("name") not in rec.stats["categories"]:
                    rec.stats["categories"].append(cat.get("name"))
    return list(out.values())


def _soccer_lineups(
    rosters: list[dict[str, Any]], lg: League, competition: Any
) -> tuple[list[PlayerGameStatRecord], list[RosterRecord]]:
    players: list[PlayerGameStatRecord] = []
    lineups: list[RosterRecord] = []
    for block in rosters or []:
        team = _team(block["team"], lg)
        formation = block.get("formation")
        for entry in block.get("roster") or []:
            athlete = entry.get("athlete") or {}
            if not athlete.get("id"):
                continue
            pos = entry.get("position")
            position = pos.get("abbreviation") if isinstance(pos, dict) else None
            player = _player(athlete, lg, position=position)
            if entry.get("jersey"):
                player.jersey = str(entry["jersey"])
            stats: dict[str, Any] = {
                "starter": bool(entry.get("starter")),
                "subbedIn": bool(entry.get("subbedIn")),
                "subbedOut": bool(entry.get("subbedOut")),
            }
            if entry.get("formationPlace") is not None:
                stats["formationPlace"] = _int(entry.get("formationPlace"))
            if formation:
                stats["formation"] = formation
            for s in entry.get("stats") or []:
                name = s.get("name")
                if name:
                    stats[name] = _num(s.get("value", s.get("displayValue")))
            players.append(PlayerGameStatRecord(team=team, player=player, stats=stats))
            lineups.append(
                RosterRecord(
                    competition=competition,
                    team=team,
                    player=player,
                    jersey=player.jersey,
                    position=position,
                )
            )
    return players, lineups


def _predictor(
    payload: dict[str, Any], home: TeamRef, away: TeamRef, lg: League, captured_at: datetime
) -> list[PickRecord]:
    pred = payload.get("predictor") or {}
    ht = pred.get("homeTeam") or {}
    at = pred.get("awayTeam") or {}
    hp = _num(ht.get("gameProjection"))
    ap = _num(at.get("gameProjection"))
    if not isinstance(hp, int | float) or not isinstance(ap, int | float):
        return []
    home_wins = hp >= ap
    prob = (hp if home_wins else ap) / 100.0
    return [
        PickRecord(
            author="ESPN FPI",
            pick_team=home if home_wins else away,
            win_probability=round(prob, 4),
            published_at=captured_at,
        )
    ]


def parse_summary(
    payload: dict[str, Any], lg: League, captured_at: datetime | None = None
) -> SummaryRecord | None:
    captured_at = captured_at or datetime.now(UTC)
    header = payload.get("header") or {}
    competitions = header.get("competitions") or []
    if not competitions:
        return None
    comp = competitions[0]
    competitors = comp.get("competitors") or []
    home_node = next((c for c in competitors if c.get("homeAway") == "home"), None)
    away_node = next((c for c in competitors if c.get("homeAway") == "away"), None)
    if not home_node or not away_node:
        return None

    uid = str(header.get("uid") or comp.get("uid") or "")
    external_id = uid.split("~c:")[0] if uid else f"{lg.espn_sport}:{header.get('id')}"
    home = _team(home_node["team"], lg)
    away = _team(away_node["team"], lg)
    status_node = comp.get("status") or {}
    status = game_status(status_node) if status_node else None
    scored = status in {"final", "in_progress"}

    boxscore = payload.get("boxscore") or {}
    home_stats: dict[str, Any] = {}
    away_stats: dict[str, Any] = {}
    for t in boxscore.get("teams") or []:
        ext = team_external_id(t.get("team") or {}, lg)
        stats = _team_stats(t)
        if ext == home.external_id or t.get("homeAway") == "home":
            home_stats = stats
        elif ext == away.external_id or t.get("homeAway") == "away":
            away_stats = stats

    competition = lg.competition()
    if lg.sport == "soccer":
        players, lineups = _soccer_lineups(payload.get("rosters") or [], lg, competition)
    else:
        players, lineups = _football_players(boxscore, lg), []

    return SummaryRecord(
        game_external_id=external_id,
        competition=competition,
        home=home,
        away=away,
        status=status,
        home_score=_int(home_node.get("score")) if scored else None,
        away_score=_int(away_node.get("score")) if scored else None,
        home_stats=home_stats,
        away_stats=away_stats,
        players=players,
        lineups=lineups,
        picks=_predictor(payload, home, away, lg, captured_at),
    )
