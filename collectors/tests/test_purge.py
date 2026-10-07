"""Deleting a retired competition without taking half the database with it.

The dangerous part is not the games -- those belong to one competition. It is
the teams and players: a club in the Europa League also plays in its own league,
so "delete everything in the Europa League" must not delete Arsenal. Teams and
players go only when nothing anywhere points at them, which is only safe if the
list of "anywhere" is complete. These tests check that list against the schema
rather than trusting it.
"""

import pathlib
import re

from gimme_collectors import purge

SCHEMA = pathlib.Path(__file__).resolve().parents[2] / "packages" / "db" / "src" / "schema.ts"


def _foreign_keys_into(entity: str) -> set[tuple[str, str]]:
    """(table, column) pairs in the Drizzle schema that reference `entity`.id."""
    source = SCHEMA.read_text(encoding="utf-8")
    found: set[tuple[str, str]] = set()
    table = None
    for line in source.splitlines():
        table_match = re.search(r'^\s*"([a-z_]+)",\s*$', line)
        if table_match:
            table = table_match.group(1)
        column_match = re.search(r'^\s*([a-zA-Z]+):\s*\w+\("([a-z_]+)"', line)
        if column_match:
            _pending = column_match.group(2)
        if f"references(() => {entity}.id)" in line and table:
            # the column name is on this line or the one that opened the field
            col = re.search(r'\w+\("([a-z_]+)"', line)
            found.add((table, col.group(1) if col else _pending))
    return found


def _covered(references: tuple[str, ...]) -> set[tuple[str, str]]:
    out = set()
    for sql in references:
        m = re.match(r"SELECT (\w+) FROM (\w+)", sql)
        assert m, sql
        out.add((m.group(2), m.group(1)))
    return out


def test_every_foreign_key_into_team_is_checked_before_deleting_one():
    """If a new table gains a team_id and is not listed here, purge would delete
    teams that are still in use. Fail loudly instead."""
    schema_fks = _foreign_keys_into("team")
    assert schema_fks, "could not read team foreign keys out of the schema"
    missing = schema_fks - _covered(purge.TEAM_REFERENCES)
    assert not missing, f"purge.TEAM_REFERENCES is missing: {sorted(missing)}"


def test_every_foreign_key_into_player_is_checked():
    schema_fks = _foreign_keys_into("player")
    assert schema_fks
    missing = schema_fks - _covered(purge.PLAYER_REFERENCES)
    assert not missing, f"purge.PLAYER_REFERENCES is missing: {sorted(missing)}"


def test_every_child_of_game_is_deleted_before_the_games():
    schema_fks = {t for t, _c in _foreign_keys_into("game")}
    missing = schema_fks - set(purge.GAME_CHILDREN)
    assert not missing, f"purge.GAME_CHILDREN is missing: {sorted(missing)}"


def test_every_child_of_season_is_deleted_before_the_seasons():
    schema_fks = {t for t, _c in _foreign_keys_into("season")}
    # `game` is handled earlier, by competition, so it is not in SEASON_CHILDREN
    missing = schema_fks - set(purge.SEASON_CHILDREN) - {"game"}
    assert not missing, f"purge.SEASON_CHILDREN is missing: {sorted(missing)}"


def test_the_orphan_queries_are_not_silently_empty():
    assert len(purge.TEAM_REFERENCES) >= 8
    assert len(purge.PLAYER_REFERENCES) >= 3
    for sql in purge.TEAM_REFERENCES + purge.PLAYER_REFERENCES:
        assert sql.startswith("SELECT ")
