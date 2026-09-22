"""Check a second source's results against what is already stored.

Soccer runs on ESPN's unofficial API for everything: fixtures, results, lineups,
injuries, across nineteen competitions. Twice in one week that API changed shape
without warning and did it silently -- a 200 and an empty list, not an error. The
collector cannot tell the difference between "no games that day" and "the
endpoint moved".

football-data.co.uk can. It publishes the same results for twelve European
leagues as static CSVs, free, from a completely separate operation. It is not a
replacement -- no lineups, no players, no South America -- but it is an
independent witness to the scoreline, which is the one thing everything else is
built on.

The writer already merges a second source's copy of a known game, filling gaps
and never blanking out what the first source had. That is the right behaviour for
collection and exactly the wrong behaviour for detection: a disagreement gets
quietly resolved in favour of whoever wrote first. So the comparison happens
before any of that, and only reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from gimme_collectors.models import GameRecord
from gimme_collectors.pipeline.teamnames import match_team

# Sources disagree on kickoff time far more than on the day; football-data.co.uk
# publishes a local date with no timezone at all.
DAY_TOLERANCE = 1


@dataclass
class StoredGame:
    game_id: int
    kickoff: date
    home_id: int
    away_id: int
    home_score: int | None
    away_score: int | None
    status: str


@dataclass
class Finding:
    competition: str
    kind: str  # 'score' | 'not_final' | 'unknown_game' | 'unmatched_team'
    day: date
    home: str
    away: str
    ours: str
    theirs: str

    def line(self) -> str:
        return (
            f"  [{self.competition}] {self.day} {self.home} v {self.away}: "
            f"{self.kind} — ours {self.ours}, theirs {self.theirs}"
        )


@dataclass
class Report:
    checked: int = 0
    agreed: int = 0
    findings: list[Finding] = field(default_factory=list)

    @property
    def disagreements(self) -> int:
        return len(self.findings)

    def of_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]


def _score(home: Any, away: Any) -> str:
    if home is None or away is None:
        return "no score"
    return f"{home}-{away}"


def compare(
    competition: str,
    records: list[GameRecord],
    stored: list[StoredGame],
    team_names: dict[str, int],
) -> Report:
    """Compare a source's finished games against stored ones.

    `team_names` maps every known display, short and location name in the
    competition to its team id -- the same candidate set the writer resolves
    against, so a name this cannot place is one the writer could not place either.
    """
    report = Report()
    by_teams: dict[tuple[int, int], list[StoredGame]] = {}
    for game in stored:
        by_teams.setdefault((game.home_id, game.away_id), []).append(game)

    for record in records:
        if record.status != "final" or record.home_score is None:
            continue
        report.checked += 1
        day = record.kickoff.date()
        home_id = match_team(record.home.name, team_names)
        away_id = match_team(record.away.name, team_names)
        if home_id is None or away_id is None:
            unknown = record.home.name if home_id is None else record.away.name
            report.findings.append(
                Finding(
                    competition,
                    "unmatched_team",
                    day,
                    record.home.name,
                    record.away.name,
                    ours="no such team",
                    theirs=unknown,
                )
            )
            continue

        candidates = [
            g
            for g in by_teams.get((home_id, away_id), [])
            if abs((g.kickoff - day).days) <= DAY_TOLERANCE
        ]
        if not candidates:
            report.findings.append(
                Finding(
                    competition,
                    "unknown_game",
                    day,
                    record.home.name,
                    record.away.name,
                    ours="not stored",
                    theirs=_score(record.home_score, record.away_score),
                )
            )
            continue

        game = min(candidates, key=lambda g: abs((g.kickoff - day).days))
        theirs = _score(record.home_score, record.away_score)
        ours = _score(game.home_score, game.away_score)
        if game.status != "final" or game.home_score is None:
            report.findings.append(
                Finding(
                    competition,
                    "not_final",
                    day,
                    record.home.name,
                    record.away.name,
                    ours=f"{game.status} ({ours})",
                    theirs=theirs,
                )
            )
        elif (game.home_score, game.away_score) != (record.home_score, record.away_score):
            report.findings.append(
                Finding(
                    competition,
                    "score",
                    day,
                    record.home.name,
                    record.away.name,
                    ours=ours,
                    theirs=theirs,
                )
            )
        else:
            report.agreed += 1
    return report


STORED_SQL = """
    SELECT g.id, g.kickoff::date AS day, g.home_team_id, g.away_team_id,
           g.home_score, g.away_score, g.status
    FROM game g
    JOIN competition c ON c.id = g.competition_id
    WHERE c.slug = %s AND g.kickoff::date BETWEEN %s AND %s
"""

TEAM_SQL = """
    SELECT DISTINCT t.id, t.name, t.short_name, t.location
    FROM team t
    JOIN team_season ts ON ts.team_id = t.id
    JOIN season s ON s.id = ts.season_id
    JOIN competition c ON c.id = s.competition_id
    WHERE c.slug = %s
"""


def load_stored(conn: Any, slug: str, first: date, last: date) -> list[StoredGame]:
    with conn.cursor() as cur:
        cur.execute(STORED_SQL, (slug, first, last))
        return [
            StoredGame(
                game_id=r[0],
                kickoff=r[1],
                home_id=r[2],
                away_id=r[3],
                home_score=r[4],
                away_score=r[5],
                status=r[6],
            )
            for r in cur.fetchall()
        ]


def load_team_names(conn: Any, slug: str) -> dict[str, int]:
    names: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(TEAM_SQL, (slug,))
        for team_id, name, short_name, location in cur.fetchall():
            for candidate in (name, short_name, location):
                if candidate:
                    names.setdefault(str(candidate), int(team_id))
    return names


def window(records: list[GameRecord], days: int) -> tuple[date, date] | None:
    """The date range worth checking: the last `days` of the source's own data."""
    finals = [r.kickoff.date() for r in records if r.status == "final"]
    if not finals:
        return None
    last = max(finals)
    return (last - timedelta(days=days), last)
