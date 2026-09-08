"""Prediction engine: models on synthetic data, feature walk, Dixon-Coles sanity."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import numpy as np

from gimme_predict.data import Game, market_probs
from gimme_predict.features import build_features
from gimme_predict.markets import football, soccer
from gimme_predict.models import Logistic, Ridge, log_loss


def _game(
    i: int,
    home: int,
    away: int,
    hs: int | None,
    as_: int | None,
    season: int = 1,
    sport: str = "american_football",
    days: int = 0,
) -> Game:
    return Game(
        id=i,
        competition="x",
        sport=sport,
        season_id=season,
        season_label=str(season),
        kickoff=datetime(2024, 9, 1, tzinfo=UTC) + timedelta(days=days),
        home_id=home,
        away_id=away,
        home_name=f"T{home}",
        away_name=f"T{away}",
        home_abbr=None,
        away_abbr=None,
        status="final" if hs is not None else "scheduled",
        home_score=hs,
        away_score=as_,
        neutral=False,
        week=None,
    )


def test_ridge_and_logistic_recover_known_relationships():
    # numpy.random is blocked by an application-control policy on the dev box;
    # Python's random is enough here.
    rng = random.Random(0)
    x = np.array([[rng.gauss(0, 1), rng.gauss(0, 1)] for _ in range(500)])
    noise = np.array([rng.gauss(0, 0.1) for _ in range(500)])
    y = 3.0 + 2.0 * x[:, 0] - 1.0 * x[:, 1] + noise
    r = Ridge(alpha=0.01).fit(x, y)
    assert abs(r.intercept_ - 3.0) < 0.05 and abs(r.coef_[0] - 2.0) < 0.05
    z = 1.5 * x[:, 0]
    u = np.array([rng.random() for _ in range(500)])
    yb = (u < 1 / (1 + np.exp(-z))).astype(float)
    lg = Logistic(alpha=0.01).fit(x, yb)
    assert 1.0 < lg.coef_[0] < 2.2 and abs(lg.coef_[1]) < 0.4
    assert log_loss(yb, lg.predict_proba(x)) < log_loss(yb, np.full(500, 0.5))


def test_market_probs_devig():
    p = market_probs({"h2h_home_price": 1.5, "h2h_away_price": 3.0})
    assert abs(p["home"] + p["away"] - 1) < 1e-9 and p["home"] > p["away"]
    assert market_probs({}) == {}


def test_features_are_point_in_time():
    games = [
        _game(1, 1, 2, 30, 10, days=0),
        _game(2, 1, 3, 20, 20, days=7),
        _game(3, 2, 1, None, None, days=14),
    ]
    rows = build_features(games)
    first, second, third = rows
    assert first.elo_home == 1500 and first.games_home == 0 and first.rest_home == 7
    assert second.elo_home > 1500  # team 1 won game 1
    assert second.form_home == 20 and second.rest_home == 7
    # a draw against a 1500 side costs the higher-rated team a few points
    assert 1500 < third.elo_away < second.elo_home
    assert third.rest_away == 7 and third.games_away == 2
    assert third.form_away == 10  # mean of +20 and 0
    v = second.vector()
    assert len(v) == 3 and v[0] > 0


def test_football_model_learns_strength():
    rng = random.Random(1)
    games: list[Game] = []
    gid = 0
    strength = {t: (t - 5) * 3.0 for t in range(1, 11)}  # team 10 is best
    for season in (1, 2, 3):
        for week in range(18):
            teams = list(range(1, 11))
            rng.shuffle(teams)
            for k in range(0, 10, 2):
                h, a = teams[k], teams[k + 1]
                margin = round(strength[h] - strength[a] + 2.5 + rng.gauss(0, 10))
                hs = max(0, 24 + margin // 2)
                as_ = max(0, hs - margin)
                gid += 1
                games.append(
                    _game(gid, h, a, hs, as_, season=season, days=(season - 1) * 200 + week * 7)
                )
    features = build_features(games)
    model = football.train(features)
    assert model is not None and model.train_size > 100
    upcoming = [_game(999, 10, 1, None, None, season=3, days=600)]
    rows = build_features(games + upcoming)[-1:]
    pred = football.predict(model, rows)[0]
    assert pred.p_home > 0.75 and pred.margin > 10
    assert "elo_diff" in pred.explanation and pred.explanation["blend"] == "model only"


def test_dixon_coles_fits_and_predicts():
    rng = random.Random(2)
    games: list[Game] = []
    attack = {t: (t - 3) * 0.15 for t in range(1, 7)}
    gid = 0
    for rnd in range(30):
        teams = list(range(1, 7))
        rng.shuffle(teams)
        for k in range(0, 6, 2):
            h, a = teams[k], teams[k + 1]
            lam = 1.4 * pow(2.718, attack[h] - attack[a] * 0.5 + 0.2)
            mu = 1.1 * pow(2.718, attack[a] - attack[h] * 0.5)
            hs = sum(rng.random() < lam / 6 for _ in range(6))
            as_ = sum(rng.random() < mu / 6 for _ in range(6))
            gid += 1
            games.append(_game(gid, h, a, hs, as_, sport="soccer", days=rnd * 7))
    model = soccer.train(games)
    assert model is not None
    strong, weak = model.strengths(6)[0], model.strengths(1)[0]
    assert strong > weak
    pred = soccer.predict(model, [_game(999, 6, 1, None, None, sport="soccer", days=300)])[0]
    assert pred.p["home"] > pred.p["away"]
    assert abs(sum(pred.p.values()) - 1) < 1e-6
    assert 0 < pred.over_25 < 1 and pred.lam > pred.mu
