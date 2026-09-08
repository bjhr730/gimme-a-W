"""Drop predictions that a newer run has superseded.

Every prediction run writes a complete fresh set of rows and nothing removed the
old ones, so four passes a day added roughly 70 MB and the table grew to be the
largest in the database. Left alone it refills the 512 MB project inside a week
and writes start failing.

What is kept: for each game and each model, the rows from the newest run. That is
exactly what the site reads and what the scorecard grades, since predictions are
only ever written for games that have not kicked off, so the newest run for a
finished game is also the last one published before it started. Everything older
is unreachable by any query the app makes.

Deleting in batches keeps the transaction short, which matters on a database that
has already hit its ceiling once.
"""

from __future__ import annotations

from typing import Any

import psycopg

BATCH = 20_000

# The newest run per game and model. Predictions are written only for upcoming
# games, so this row is also the last one published before kickoff.
SUPERSEDED = """
    WITH keep AS (
        SELECT p.game_id, mr.model_name, MAX(p.model_run_id) AS run_id
        FROM prediction p
        JOIN model_run mr ON mr.id = p.model_run_id
        GROUP BY p.game_id, mr.model_name
    )
    SELECT p.id
    FROM prediction p
    JOIN model_run mr ON mr.id = p.model_run_id
    JOIN keep k ON k.game_id = p.game_id AND k.model_name = mr.model_name
    WHERE p.model_run_id < k.run_id
    LIMIT %s
"""


def count_superseded(conn: psycopg.Connection[Any]) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH keep AS (
                SELECT p.game_id, mr.model_name, MAX(p.model_run_id) AS run_id
                FROM prediction p
                JOIN model_run mr ON mr.id = p.model_run_id
                GROUP BY p.game_id, mr.model_name
            )
            SELECT count(*)
            FROM prediction p
            JOIN model_run mr ON mr.id = p.model_run_id
            JOIN keep k ON k.game_id = p.game_id AND k.model_name = mr.model_name
            WHERE p.model_run_id < k.run_id
            """
        )
        row = cur.fetchone()
    return int(row[0]) if row else 0


def run(database_url: str, *, dry_run: bool = False) -> dict[str, Any]:
    conn = psycopg.connect(database_url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            before = (cur.fetchone() or ["?"])[0]
            cur.execute("SELECT count(*) FROM prediction")
            rows_before = int((cur.fetchone() or [0])[0])

        superseded = count_superseded(conn)
        if dry_run:
            return {
                "database_before": before,
                "predictions": rows_before,
                "superseded": superseded,
                "deleted": 0,
                "dry_run": True,
            }

        deleted = 0
        while True:
            with conn.cursor() as cur:
                cur.execute(f"DELETE FROM prediction WHERE id IN ({SUPERSEDED})", (BATCH,))
                removed = cur.rowcount
            if removed <= 0:
                break
            deleted += removed
            print(f"    pruned {deleted:,} of {superseded:,}", flush=True)

        with conn.cursor() as cur:
            # give the space back rather than leaving it as bloat
            cur.execute("VACUUM (ANALYZE) prediction")
            cur.execute("SELECT pg_size_pretty(pg_database_size(current_database()))")
            after = (cur.fetchone() or ["?"])[0]
            cur.execute("SELECT count(*) FROM prediction")
            rows_after = int((cur.fetchone() or [0])[0])
        return {
            "database_before": before,
            "database_after": after,
            "predictions_before": rows_before,
            "predictions_after": rows_after,
            "deleted": deleted,
        }
    finally:
        conn.close()
