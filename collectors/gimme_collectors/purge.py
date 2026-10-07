"""Delete a retired competition and everything that belonged only to it.

Switching a competition off stops it being collected; marking it inactive takes
it off the site. This removes it. That is a different kind of operation -- there
is no undo beyond Neon's six-hour history window -- so it reports before it acts
and refuses to run without being told to.

The order below follows the foreign keys from the leaves inward: rows that point
at games, then the games, then rows that point at seasons, then the seasons, then
the competition. Teams and players are the subtle part. A club that played in the
Europa League also plays in its own league, so deleting by competition must not
delete Arsenal; teams and players are removed only when nothing anywhere refers
to them any more.
"""

from __future__ import annotations

from typing import Any

import psycopg

# Children of `game`, deleted before the games themselves.
GAME_CHILDREN = (
    "feature_snapshot",
    "odds",
    "pick",
    "player_game_stat",
    "prediction",
    "team_game_stat",
)

# Children of `season`, deleted before the seasons.
SEASON_CHILDREN = ("rating", "roster", "standing", "team_form", "team_season")

# Every way a team can still be referenced. A team matching none of these is
# attached to nothing and can go.
TEAM_REFERENCES = (
    "SELECT home_team_id FROM game",
    "SELECT away_team_id FROM game",
    "SELECT pick_team_id FROM pick",
    "SELECT team_id FROM player_game_stat",
    "SELECT team_id FROM player_status",
    "SELECT team_id FROM roster",
    "SELECT team_id FROM standing",
    "SELECT team_id FROM team_form",
    "SELECT team_id FROM team_game_stat",
    "SELECT team_id FROM team_season",
)

PLAYER_REFERENCES = (
    "SELECT player_id FROM player_game_stat",
    "SELECT player_id FROM player_status",
    "SELECT player_id FROM roster",
)


def _retired(cur: Any, slugs: list[str] | None) -> list[tuple[int, str]]:
    if slugs:
        cur.execute("SELECT id, slug FROM competition WHERE slug = ANY(%s)", (slugs,))
    else:
        cur.execute("SELECT id, slug FROM competition WHERE NOT is_active")
    return [(int(r[0]), str(r[1])) for r in cur.fetchall()]


def _count(cur: Any, sql: str, params: tuple[Any, ...] = ()) -> int:
    cur.execute(f"SELECT count(*) FROM ({sql}) t", params)
    row = cur.fetchone()
    return int(row[0]) if row else 0


def plan(cur: Any, comp_ids: list[int]) -> dict[str, int]:
    """What would go, without touching anything."""
    counts: dict[str, int] = {}
    games = "SELECT id FROM game WHERE competition_id = ANY(%s)"
    seasons = "SELECT id FROM season WHERE competition_id = ANY(%s)"
    for table in GAME_CHILDREN:
        counts[table] = _count(
            cur, f"SELECT 1 FROM {table} WHERE game_id IN ({games})", (comp_ids,)
        )
    counts["game"] = _count(cur, games, (comp_ids,))
    for table in SEASON_CHILDREN:
        counts[table] = _count(
            cur, f"SELECT 1 FROM {table} WHERE season_id IN ({seasons})", (comp_ids,)
        )
    counts["season"] = _count(cur, seasons, (comp_ids,))
    counts["competition"] = len(comp_ids)
    return counts


def _orphans(cur: Any, entity: str, references: tuple[str, ...]) -> int:
    """Delete rows of `entity` nothing refers to any more. Returns how many went."""
    union = " UNION ALL ".join(references)
    cur.execute(
        f"""
        DELETE FROM {entity}
        WHERE id NOT IN (SELECT id FROM ({union}) r(id) WHERE id IS NOT NULL)
        """
    )
    return cur.rowcount


def purge(conn: psycopg.Connection[Any], slugs: list[str] | None = None) -> dict[str, int]:
    """Delete the named competitions, or every inactive one, and their orphans.

    Runs as a single transaction: either the whole competition goes or none of
    it does, so a failure halfway cannot leave games without their results.
    """
    removed: dict[str, int] = {}
    with conn.cursor() as cur:
        retired = _retired(cur, slugs)
        if not retired:
            return {}
        comp_ids = [cid for cid, _ in retired]
        games = "SELECT id FROM game WHERE competition_id = ANY(%s)"
        seasons = "SELECT id FROM season WHERE competition_id = ANY(%s)"

        # external ids for the games about to go, while they can still be found
        cur.execute(
            f"DELETE FROM external_id WHERE entity_type = 'game' AND entity_id IN ({games})",
            (comp_ids,),
        )
        removed["external_id (games)"] = cur.rowcount

        for table in GAME_CHILDREN:
            cur.execute(f"DELETE FROM {table} WHERE game_id IN ({games})", (comp_ids,))
            removed[table] = cur.rowcount
        cur.execute("DELETE FROM game WHERE competition_id = ANY(%s)", (comp_ids,))
        removed["game"] = cur.rowcount

        for table in SEASON_CHILDREN:
            cur.execute(f"DELETE FROM {table} WHERE season_id IN ({seasons})", (comp_ids,))
            removed[table] = cur.rowcount
        cur.execute("DELETE FROM season WHERE competition_id = ANY(%s)", (comp_ids,))
        removed["season"] = cur.rowcount

        cur.execute("DELETE FROM competition WHERE id = ANY(%s)", (comp_ids,))
        removed["competition"] = cur.rowcount

        # Only now are teams and players orphaned, and only the ones that played
        # nowhere else: a club in both the Europa League and its own league keeps
        # every row it has there.
        removed["player_status (orphaned)"] = _orphans(
            cur,
            "player_status",
            ("SELECT player_id FROM player_game_stat", "SELECT player_id FROM roster"),
        )
        removed["player (orphaned)"] = _orphans(cur, "player", PLAYER_REFERENCES)
        removed["team (orphaned)"] = _orphans(cur, "team", TEAM_REFERENCES)
        cur.execute(
            """
            DELETE FROM external_id
            WHERE (entity_type = 'team' AND entity_id NOT IN (SELECT id FROM team))
               OR (entity_type = 'player' AND entity_id NOT IN (SELECT id FROM player))
            """
        )
        removed["external_id (teams, players)"] = cur.rowcount
    conn.commit()
    return {k: v for k, v in removed.items() if v}
