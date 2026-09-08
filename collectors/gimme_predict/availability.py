"""Player availability, read by the prop models before they publish a projection.

A row in `player_status` says what a source last reported about a player: the
source's own wording ("Injured Reserve", "Questionable"), a normalized verdict,
and the share of games a player carrying that verdict has historically been
active for.

Two rules, applied in `gimme_predict.props`:

* `out` (out, injured reserve, suspended) removes the player from the markets
  entirely. Publishing 68 rushing yards for a player on injured reserve is worse
  than publishing nothing.
* `questionable` and `doubtful` keep the projection, which is conditional on
  playing, but scale the probability markets (anytime touchdown, anytime scorer)
  by the play probability, because those ask whether the event happens at all.

A player with no row is "no report", never "fit": nothing is scaled and nothing
is removed. That matters because ESPN publishes a full report for the NFL, a
thin one for college football and none for soccer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import psycopg

# The verdicts that stop a projection from being published at all.
UNAVAILABLE = {"out"}


@dataclass(frozen=True)
class Status:
    availability: str
    status: str  # the source's own wording, for display
    play_probability: float
    injury_type: str | None = None
    detail: str | None = None
    return_date: date | None = None

    @property
    def out(self) -> bool:
        return self.availability in UNAVAILABLE

    @property
    def doubt(self) -> bool:
        """A report that lowers, but does not eliminate, the chance of playing."""
        return self.availability in {"questionable", "doubtful"}

    def summary(self) -> dict[str, Any]:
        """The part of the report worth storing alongside a prediction."""
        out: dict[str, Any] = {"status": self.status, "availability": self.availability}
        if self.play_probability < 1:
            out["play_probability"] = round(self.play_probability, 2)
        if self.injury_type:
            out["injury"] = self.injury_type
        return out


SEVERITY = {"out": 0, "doubtful": 1, "questionable": 2, "available": 3}


def load(conn: psycopg.Connection[Any], team_ids: list[int] | None = None) -> dict[int, Status]:
    """Current status per player. When two sources disagree, the gloomier wins."""
    where = ""
    params: list[Any] = []
    if team_ids:
        where = "WHERE ps.team_id = ANY(%s)"
        params.append(list(team_ids))
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT ON (ps.player_id)
                   ps.player_id, ps.availability, ps.status, ps.play_probability,
                   ps.injury_type, ps.detail, ps.return_date
            FROM player_status ps
            {where}
            ORDER BY ps.player_id,
                     CASE ps.availability WHEN 'out' THEN 0 WHEN 'doubtful' THEN 1
                          WHEN 'questionable' THEN 2 ELSE 3 END,
                     ps.reported_at DESC NULLS LAST
            """,
            params,
        )
        rows = cur.fetchall()
        # the column names have to be read before the cursor closes
        columns = [c[0] for c in cur.description or []]
    out: dict[int, Status] = {}
    for r in rows:
        row = r if isinstance(r, dict) else dict(zip(columns, r, strict=False))
        probability = row["play_probability"]
        out[int(row["player_id"])] = Status(
            availability=str(row["availability"]),
            status=str(row["status"]),
            play_probability=1.0 if probability is None else float(probability),
            injury_type=row["injury_type"],
            detail=row["detail"],
            return_date=row["return_date"],
        )
    return out
