"""Grading player props against outcomes.

The headline number is Brier skill against the base rate, so these tests pin the
three cases that matter: a model that knows something, a model that knows exactly
the base rate, and a model that is worse than knowing nothing.
"""

from datetime import UTC, datetime

import pytest

from gimme_predict import score_props

SINCE = datetime(2026, 8, 1, tzinfo=UTC)


def row(
    market,
    probability,
    *,
    goals=0,
    assists=0,
    sot=0,
    tds=0,
    line=None,
    played=True,
    competition="eng.1",
    selection="yes",
):
    return {
        "market": market,
        "selection": selection,
        "probability": probability,
        "line": line,
        "competition": competition,
        "goals": goals,
        "assists": assists,
        "sot": sot,
        "tds": tds,
        "played": played,
    }


class _Cursor:
    def __init__(self, rows, sink):
        self.rows, self.sink = rows, sink

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self.sink.append((sql, list(params or [])))

    def fetchall(self):
        return self.rows


class _Conn:
    def __init__(self, rows):
        self.rows, self.statements = rows, []

    def cursor(self, **_):
        return _Cursor(self.rows, self.statements)


# ----------------------------------------------------------------- outcomes


@pytest.mark.parametrize(
    "market,kwargs,expected",
    [
        ("anytime_scorer", {"goals": 1}, True),
        ("anytime_scorer", {"goals": 0}, False),
        ("anytime_assist", {"assists": 2}, True),
        ("anytime_assist", {"assists": 0}, False),
        ("anytime_td", {"tds": 1}, True),
        ("anytime_td", {"tds": 0}, False),
        ("player_shots_on_target", {"sot": 1, "line": 0.5}, True),
        ("player_shots_on_target", {"sot": 0, "line": 0.5}, False),
        ("player_shots_on_target", {"sot": 1, "line": 1.5}, False),
        ("player_shots_on_target", {"sot": 2, "line": 1.5}, True),
    ],
)
def test_outcomes(market, kwargs, expected):
    assert score_props._happened(row(market, 0.5, **kwargs)) is expected


def test_the_mean_only_row_is_not_gradable():
    # player_shots_on_target is written once with no line, carrying the mean
    assert score_props._happened(row("player_shots_on_target", 0.5, line=None)) is None


def test_unknown_market_is_not_gradable():
    assert score_props._happened(row("passing_yards", 0.5)) is None


def test_lines_are_kept_apart_in_the_label():
    assert score_props._label(row("player_shots_on_target", 0.3, line=0.5)) == (
        "player_shots_on_target over 0.5"
    )
    assert score_props._label(row("player_shots_on_target", 0.3, line=1.5)) == (
        "player_shots_on_target over 1.5"
    )
    assert score_props._label(row("anytime_scorer", 0.3)) == "anytime_scorer"


# ------------------------------------------------------------------- skill


def test_a_model_that_knows_something_beats_the_base_rate():
    # half score and were given 0.9; half did not and were given 0.1
    rows = [row("anytime_scorer", 0.9, goals=1) for _ in range(20)]
    rows += [row("anytime_scorer", 0.1, goals=0) for _ in range(20)]
    card = score_props.scorecard(_Conn(rows), SINCE)
    m = card["markets"]["anytime_scorer"]
    assert m["beats_base_rate"] is True
    assert m["brier_skill"] > 0.5
    assert m["base_rate"] == 0.5


def test_predicting_the_base_rate_scores_exactly_zero_skill():
    rows = [row("anytime_scorer", 0.25, goals=1) for _ in range(10)]
    rows += [row("anytime_scorer", 0.25, goals=0) for _ in range(30)]
    m = score_props.scorecard(_Conn(rows), SINCE)["markets"]["anytime_scorer"]
    assert m["base_rate"] == 0.25
    assert m["brier_skill"] == 0.0
    assert m["beats_base_rate"] is False


def test_a_model_worse_than_nothing_scores_negative_skill():
    # confidently backwards: the scorers were given the low number
    rows = [row("anytime_scorer", 0.1, goals=1) for _ in range(20)]
    rows += [row("anytime_scorer", 0.9, goals=0) for _ in range(20)]
    m = score_props.scorecard(_Conn(rows), SINCE)["markets"]["anytime_scorer"]
    assert m["brier_skill"] < 0
    assert m["beats_base_rate"] is False


def test_a_market_with_no_variation_says_so_instead_of_dividing_by_zero():
    rows = [row("anytime_assist", 0.2, assists=0) for _ in range(15)]
    m = score_props.scorecard(_Conn(rows), SINCE)["markets"]["anytime_assist"]
    assert m["n"] == 15
    assert "brier_skill" not in m
    assert m["note"] == "no variation in outcomes yet"


# ------------------------------------------------------------- bookkeeping


def test_a_player_who_never_played_counts_as_a_miss_and_is_reported():
    rows = [row("anytime_scorer", 0.4, goals=0, played=False) for _ in range(5)]
    rows += [row("anytime_scorer", 0.4, goals=1) for _ in range(5)]
    card = score_props.scorecard(_Conn(rows), SINCE)
    assert card["predicted_but_did_not_play"] == 5
    assert card["graded"] == 10
    assert card["markets"]["anytime_scorer"]["base_rate"] == 0.5


def test_markets_and_competitions_are_graded_separately():
    rows = [row("anytime_scorer", 0.8, goals=1, competition="eng.1") for _ in range(6)]
    rows += [row("anytime_td", 0.3, tds=0, competition="nfl") for _ in range(6)]
    rows += [row("anytime_td", 0.3, tds=1, competition="nfl") for _ in range(2)]
    card = score_props.scorecard(_Conn(rows), SINCE)
    assert set(card["markets"]) == {"anytime_scorer", "anytime_td"}
    assert set(card["competitions"]) == {"eng.1", "nfl"}
    assert card["competitions"]["nfl"]["n"] == 8


def test_calibration_bands_report_predicted_against_observed():
    # 10 at p=0.1 of which 1 happens; 10 at p=0.5 of which 5 happen
    rows = [row("anytime_scorer", 0.1, goals=1)]
    rows += [row("anytime_scorer", 0.1, goals=0) for _ in range(9)]
    rows += [row("anytime_scorer", 0.5, goals=1) for _ in range(5)]
    rows += [row("anytime_scorer", 0.5, goals=0) for _ in range(5)]
    bands = score_props.scorecard(_Conn(rows), SINCE)["markets"]["anytime_scorer"]["calibration"]
    by_band = {b["band"]: b for b in bands}
    assert by_band["0.1-0.2"]["predicted"] == 0.1
    assert by_band["0.1-0.2"]["observed"] == 0.1
    assert by_band["0.35-0.6"]["predicted"] == 0.5
    assert by_band["0.35-0.6"]["observed"] == 0.5


def test_the_query_is_bound_with_its_three_parameters():
    conn = _Conn([])
    score_props.scorecard(conn, SINCE)
    sql, params = conn.statements[-1]
    assert sql.count("%s") == len(params) == 3
    assert params[0] == score_props.MIN_PLAYER_ROWS
    assert params[1] == list(score_props.MARKETS)
    assert params[2] == SINCE


def test_only_pre_kickoff_predictions_on_covered_games_are_graded():
    # the guards live in SQL, so assert they are present rather than silently lost
    assert "mr.started_at < g.kickoff" in score_props.SQL
    assert "g.status = 'final'" in score_props.SQL
    assert "HAVING count(*) >= %s" in score_props.SQL


def test_empty_window_is_harmless():
    card = score_props.scorecard(_Conn([]), SINCE)
    assert card == {
        "graded": 0,
        "predicted_but_did_not_play": 0,
        "markets": {},
        "competitions": {},
    }
