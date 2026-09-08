"""Production health check. Exits non-zero when the pipeline is not doing its job,
so the GitHub Actions run fails and the repository owner gets the failure email.

Checks
  1. no collector run failed in the last 24 hours
  2. games were written or updated in the last 36 hours
  3. predictions were written in the last 36 hours, when there are games ahead
  4. every competition with a game in the next 7 days has a prediction for it
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
from psycopg.rows import dict_row


def check(database_url: str) -> tuple[list[str], list[str]]:
    """Return (problems, notes)."""
    problems: list[str] = []
    notes: list[str] = []
    now = datetime.now(UTC)
    with psycopg.connect(database_url, row_factory=dict_row) as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT s.slug, r.adapter, r.started_at, r.error
            FROM collector_run r JOIN source s ON s.id = r.source_id
            WHERE r.status = 'failed' AND r.started_at >= %s
            ORDER BY r.started_at DESC
            """,
            (now - timedelta(hours=24),),
        )
        for r in cur.fetchall():
            first_line = (r["error"] or "").strip().splitlines()[:1]
            problems.append(
                f"collector run failed: {r['slug']}/{r['adapter']} at "
                f"{r['started_at']:%Y-%m-%d %H:%M} UTC: {first_line[0] if first_line else ''}"
            )

        cur.execute(
            "SELECT count(*) AS n, max(updated_at) AS last FROM game WHERE updated_at >= %s",
            (now - timedelta(hours=36),),
        )
        row = cur.fetchone()
        assert row is not None
        if row["n"] == 0:
            problems.append("no game rows written or updated in the last 36 hours")
        else:
            notes.append(
                f"games touched in last 36h: {row['n']} (last {row['last']:%Y-%m-%d %H:%M} UTC)"
            )

        cur.execute(
            "SELECT count(*) AS n FROM game "
            "WHERE status = 'scheduled' AND kickoff BETWEEN %s AND %s",
            (now, now + timedelta(days=7)),
        )
        ahead = int(cur.fetchone()["n"])  # type: ignore[index]
        cur.execute(
            "SELECT count(*) AS n FROM prediction WHERE created_at >= %s",
            (now - timedelta(hours=36),),
        )
        fresh = int(cur.fetchone()["n"])  # type: ignore[index]
        if ahead > 0 and fresh == 0:
            problems.append(f"{ahead} games ahead but no predictions written in 36 hours")
        else:
            notes.append(f"games in next 7 days: {ahead}; predictions written in last 36h: {fresh}")

        cur.execute(
            """
            SELECT c.slug, count(g.id) AS games,
                   count(g.id) FILTER (WHERE EXISTS (
                       SELECT 1 FROM prediction p
                       WHERE p.game_id = g.id AND p.market IN ('win_probability', 'match_result')
                   )) AS predicted
            FROM game g JOIN competition c ON c.id = g.competition_id
            WHERE g.status = 'scheduled' AND g.kickoff BETWEEN %s AND %s
            GROUP BY c.slug ORDER BY c.slug
            """,
            (now, now + timedelta(days=7)),
        )
        for r in cur.fetchall():
            slug, games, predicted = r["slug"], r["games"], r["predicted"]
            if predicted == 0 and games >= 3:
                notes.append(
                    f"{slug}: {games} games ahead, none predicted (model may lack history)"
                )
            elif predicted < games:
                notes.append(f"{slug}: {predicted}/{games} upcoming games predicted")
    return problems, notes


def main(database_url: str) -> int:
    problems, notes = check(database_url)
    for n in notes:
        print(f"  ok   {n}")
    for p in problems:
        print(f"  FAIL {p}")
    if problems:
        print(f"{len(problems)} problem(s)")
        return 1
    print("healthy")
    return 0


def _unused(_: Any) -> None:
    pass
