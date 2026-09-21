"""The loaders project a fixed key list in SQL, so the list must not drift.

If a model starts reading a new stat key and nobody adds it here, the key is
silently absent from every row and the feature quietly reads zero -- no error,
just a worse model. These tests make that a failure instead.
"""

import ast
import pathlib

from gimme_predict import players
from gimme_predict.markets import soccer_props


def _keys_read_by(func_name: str) -> set[str]:
    """Every literal passed to stats.get(...) inside one function."""
    source = pathlib.Path(players.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == func_name)
    found: set[str] = set()
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return found


def test_football_values_reads_nothing_unprojected():
    assert _keys_read_by("football_values") <= set(players.PLAYER_STAT_KEYS)


def test_soccer_values_reads_nothing_unprojected():
    read = _keys_read_by("soccer_values")
    assert read, "expected soccer_values to read some keys"
    assert read <= set(players.PLAYER_STAT_KEYS)


def test_football_keys_are_all_projected():
    assert set(players.FOOTBALL_KEYS) <= set(players.PLAYER_STAT_KEYS)


def test_soccer_keys_are_all_projected():
    assert set(players.SOCCER_KEYS) <= set(players.PLAYER_STAT_KEYS)


def test_team_keys_match_the_markets_that_use_them():
    assert set(players.TEAM_STAT_KEYS) == set(soccer_props.COUNT_MARKETS.values())


def test_projection_is_actually_narrower_than_a_box_score():
    # a real ESPN soccer row carries far more than the models touch
    assert len(players.PLAYER_STAT_KEYS) == 17
    assert "yellowCards" not in players.PLAYER_STAT_KEYS
    assert "formation" not in players.PLAYER_STAT_KEYS


class _Cursor:
    """Records the statement instead of running it."""

    def __init__(self, sink):
        self.sink = sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sink.append((sql, list(params or [])))

    def fetchall(self):
        return []


class _Conn:
    def __init__(self):
        self.statements = []

    def cursor(self, **_):
        return _Cursor(self.statements)


def _binds(conn):
    sql, params = conn.statements[-1]
    return sql.count("%s"), params


def test_every_placeholder_has_a_parameter_for_each_call_shape():
    for kwargs in (
        {"competition_slug": "eng.1"},
        {"team_ids": [1, 2, 3]},
        {"competition_slug": "eng.1", "team_ids": [1]},
        {"competition_slug": "eng.1", "history_days": None},
        {"team_ids": [7], "history_days": 90},
    ):
        conn = _Conn()
        players.load_player_games(conn, **kwargs)
        placeholders, params = _binds(conn)
        assert placeholders == len(params), f"{kwargs}: {placeholders} != {len(params)}"
        # the projection binds first, before any WHERE parameter
        assert params[0] == list(players.PLAYER_STAT_KEYS)


def test_team_loader_binds_in_order():
    for kwargs in ({}, {"history_days": None}, {"history_days": 30}):
        conn = _Conn()
        players.load_team_games(conn, "eng.1", **kwargs)
        placeholders, params = _binds(conn)
        assert placeholders == len(params), f"{kwargs}: {placeholders} != {len(params)}"
        assert params[0] == list(players.TEAM_STAT_KEYS)
        assert params[1] == "eng.1"


def test_history_bound_is_applied_unless_waived():
    conn = _Conn()
    players.load_player_games(conn, "eng.1")
    assert "make_interval" in conn.statements[-1][0]
    assert players.HISTORY_DAYS in conn.statements[-1][1]

    conn = _Conn()
    players.load_player_games(conn, "eng.1", history_days=None)
    assert "make_interval" not in conn.statements[-1][0]
