"""Pulling soccer team strengths toward their shots-on-target fit.

Goals are the outcome but a thin signal. Shots on target are several times more
numerous, so they pin a team's strength faster. The prior is optional and must
reduce to exactly the old model when switched off -- otherwise a back-test
comparing the two is comparing nothing.
"""

from datetime import UTC, datetime, timedelta

import numpy as np

from gimme_predict.data import Game
from gimme_predict.markets import soccer
from gimme_predict.players import shots_by_game

START = datetime(2026, 1, 1, tzinfo=UTC)


def game(gid: int, home: int, away: int, hs: int, as_: int, day: int) -> Game:
    return Game(
        id=gid,
        competition="eng.1",
        sport="soccer",
        season_id=1,
        season_label="2026",
        kickoff=START + timedelta(days=day),
        home_id=home,
        away_id=away,
        home_name=f"T{home}",
        away_name=f"T{away}",
        home_abbr=None,
        away_abbr=None,
        status="final",
        home_score=hs,
        away_score=as_,
        neutral=False,
        week=None,
    )


def round_robin(scoreline_for, n_teams=8, rounds=6):
    """A small league where scoreline_for(home, away) decides every result."""
    games, gid, day = [], 1, 0
    for r in range(rounds):
        for home in range(1, n_teams + 1):
            away = (home + r) % n_teams + 1
            if away == home:
                continue
            hs, as_ = scoreline_for(home, away)
            games.append(game(gid, home, away, hs, as_, day))
            gid += 1
            day += 1
    return games


# ------------------------------------------------------------ the switch


def test_weight_zero_is_exactly_the_old_model():
    games = round_robin(lambda h, a: (2, 1) if h < a else (0, 1))
    shots = {g.id: (6.0, 3.0) for g in games}
    plain = soccer.train(games)
    with_shots_off = soccer.train(games, shots=shots, shot_prior_weight=0.0)
    assert plain is not None and with_shots_off is not None
    assert np.allclose(plain.attack, with_shots_off.attack)
    assert np.allclose(plain.defence, with_shots_off.defence)
    assert plain.home == with_shots_off.home


def test_shots_without_a_weight_change_nothing():
    games = round_robin(lambda h, a: (1, 0))
    a = soccer.train(games)
    b = soccer.train(games, shots={g.id: (9.0, 1.0) for g in games})
    assert a is not None and b is not None
    assert np.allclose(a.attack, b.attack)


def test_a_weight_without_shots_changes_nothing():
    games = round_robin(lambda h, a: (1, 0))
    a = soccer.train(games)
    b = soccer.train(games, shots=None, shot_prior_weight=5.0)
    assert a is not None and b is not None
    assert np.allclose(a.attack, b.attack)


def test_too_few_games_with_shots_leaves_the_prior_alone():
    games = round_robin(lambda h, a: (2, 0) if h < a else (0, 2))
    thin = {g.id: (8.0, 2.0) for g in games[:5]}  # under the 30-game floor
    plain = soccer.train(games)
    guarded = soccer.train(games, shots=thin, shot_prior_weight=3.0)
    assert plain is not None and guarded is not None
    assert np.allclose(plain.attack, guarded.attack)


# ------------------------------------------------------- does it do work


def test_the_prior_pulls_an_unlucky_team_up():
    """Team 1 out-shoots everyone and scores nothing; the goals-only fit calls it
    weak, the shot prior should not agree as strongly."""
    teams = 8

    def scoreline(home, away):
        # team 1 loses every game 0-1 despite dominating the shot count
        if home == 1:
            return (0, 1)
        if away == 1:
            return (1, 0)
        return (1, 1)

    games = round_robin(scoreline, n_teams=teams, rounds=10)
    shots = {}
    for g in games:
        if g.home_id == 1:
            shots[g.id] = (12.0, 2.0)
        elif g.away_id == 1:
            shots[g.id] = (2.0, 12.0)
        else:
            shots[g.id] = (4.0, 4.0)

    plain = soccer.train(games)
    primed = soccer.train(games, shots=shots, shot_prior_weight=8.0)
    assert plain is not None and primed is not None
    i = plain.teams[1]
    # the shot-informed fit rates team 1's attack higher than goals alone do
    assert primed.attack[i] > plain.attack[i]


def test_the_prior_does_not_rewrite_a_team_the_shots_agree_about():
    """When shots and goals tell the same story the prior should barely move it."""
    teams = 8

    def scoreline(home, away):
        if home == 1:
            return (3, 0)
        if away == 1:
            return (0, 3)
        return (1, 1)

    games = round_robin(scoreline, n_teams=teams, rounds=10)
    shots = {}
    for g in games:
        if g.home_id == 1:
            shots[g.id] = (10.0, 2.0)
        elif g.away_id == 1:
            shots[g.id] = (2.0, 10.0)
        else:
            shots[g.id] = (4.0, 4.0)
    plain = soccer.train(games)
    primed = soccer.train(games, shots=shots, shot_prior_weight=4.0)
    assert plain is not None and primed is not None
    i = plain.teams[1]
    assert plain.attack[i] > 0 and primed.attack[i] > 0  # both call team 1 strong


def test_shot_strengths_are_scaled_to_goals_not_to_shots():
    """Shots are several times more numerous; without rescaling the prior would
    sit on a completely different scale from the goal fit and swamp it."""
    n = 4
    hi = np.array([0, 1, 2, 3] * 10)
    ai = np.array([1, 2, 3, 0] * 10)
    h_sot = np.full(40, 8.0)
    a_sot = np.full(40, 4.0)
    hg = np.full(40, 2.0)
    ag = np.full(40, 1.0)
    w = np.ones(40)
    attack, defence = soccer.shot_strengths(
        hi, ai, h_sot, a_sot, hg, ag, w, n, ridge=0.2, iterations=200
    )
    # strengths live near zero on the log scale, as the goal fit's do
    assert np.all(np.abs(attack) < 2.0)
    assert np.all(np.abs(defence) < 2.0)


def test_no_shots_at_all_yields_a_flat_prior():
    n = 3
    hi, ai = np.array([0, 1, 2]), np.array([1, 2, 0])
    zero = np.zeros(3)
    attack, defence = soccer.shot_strengths(
        hi, ai, zero, zero, np.ones(3), np.ones(3), np.ones(3), n, ridge=0.2, iterations=50
    )
    assert np.allclose(attack, 0) and np.allclose(defence, 0)


# ------------------------------------------------------------- the loader


def test_shots_by_game_pairs_the_two_sides():
    rows = [
        {"game_id": 7, "home": True, "stats": {"shotsOnTarget": 6}},
        {"game_id": 7, "home": False, "stats": {"shotsOnTarget": 3}},
        {"game_id": 8, "home": True, "stats": {"shotsOnTarget": 4}},
        {"game_id": 8, "home": False, "stats": {"shotsOnTarget": 0}},
    ]
    assert shots_by_game(rows) == {7: (6.0, 3.0), 8: (4.0, 0.0)}


def test_a_one_sided_game_is_dropped_rather_than_read_as_a_shut_out():
    rows = [
        {"game_id": 9, "home": True, "stats": {"shotsOnTarget": 5}},
        {"game_id": 10, "home": True, "stats": {"shotsOnTarget": 5}},
        {"game_id": 10, "home": False, "stats": {}},
        {"game_id": 11, "home": True, "stats": {"shotsOnTarget": "not a number"}},
        {"game_id": 11, "home": False, "stats": {"shotsOnTarget": 2}},
    ]
    assert shots_by_game(rows) == {}


def test_shots_by_game_handles_nothing():
    assert shots_by_game([]) == {}
