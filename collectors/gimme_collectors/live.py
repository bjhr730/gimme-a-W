"""Which competitions have a game on right now.

The full collection runs four times a day, which is fine for fixtures, lines and
results but leaves a match played between passes frozen at its pre-kickoff state:
a tie that kicked off at 16:45 still read 0-0 with no clock at 18:16.

Polling every league every few minutes would fix that and burn the Actions
budget, so this asks the database which competitions could plausibly have a ball
in play and returns only those. On a quiet hour it returns nothing and the caller
exits in seconds having made no requests at all.
"""

from __future__ import annotations

from typing import Any

import psycopg

# A game is worth refreshing from shortly before kickoff until long enough after
# that even a delayed finish has been recorded. Soccer runs about two hours with
# stoppages; American football closer to three and a half.
BEFORE_KICKOFF_MINUTES = 15
AFTER_KICKOFF_HOURS = 4


def active_competitions(database_url: str) -> list[str]:
    """Competition slugs with a game under way, about to start, or just finished."""
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT c.slug
            FROM game g
            JOIN competition c ON c.id = g.competition_id
            WHERE g.status IN ('scheduled', 'in_progress')
              AND g.kickoff <= now() + make_interval(mins => %s)
              AND g.kickoff >= now() - make_interval(hours => %s)
            ORDER BY c.slug
            """,
            (BEFORE_KICKOFF_MINUTES, AFTER_KICKOFF_HOURS),
        )
        return [str(r[0]) for r in cur.fetchall()]


def summary(slugs: list[str]) -> dict[str, Any]:
    return {"active": len(slugs), "competitions": ",".join(slugs) if slugs else "none"}
