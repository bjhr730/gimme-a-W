"""American football (NFL, college): win probability, spread, total points.

    win probability  logistic on [elo diff incl. home edge, rest diff, form diff]
    spread           ridge on the same inputs -> expected home margin
    total points     ridge on [scored/allowed rates of both teams, elo sum]

The published win probability is blended with the market when a moneyline
exists (60% model, 40% market): the market knows injuries and news we do not
collect yet. Explanations are the feature contributions in Elo-equivalent
points so the UI can say "Seahawks +112 Elo, well rested".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from gimme_predict.data import market_probs
from gimme_predict.features import FEATURE_NAMES, Features, normal_cdf
from gimme_predict.models import Logistic, Ridge

MODEL_NAME = "football-elo-logit"
MODEL_VERSION = "v1"
BLEND_MODEL_WEIGHT = 0.6
MARGIN_SD_FALLBACK = 13.5


@dataclass
class FootballModel:
    win: Logistic
    spread: Ridge
    total: Ridge
    margin_sd: float
    total_sd: float
    train_size: int


def _x_result(rows: list[Features]) -> np.ndarray:
    return np.array([f.vector() for f in rows], dtype=float)


def _x_total(rows: list[Features]) -> np.ndarray:
    return np.array(
        [
            [
                (f.scored_home + f.allowed_away) / 2.0,
                (f.scored_away + f.allowed_home) / 2.0,
                (f.elo_home + f.elo_away - 3000.0) / 200.0,
            ]
            for f in rows
        ],
        dtype=float,
    )


def train(rows: list[Features], *, min_games: int = 2) -> FootballModel | None:
    train_rows = [
        f for f in rows if f.game.final and f.games_home >= min_games and f.games_away >= min_games
    ]
    if len(train_rows) < 40:
        return None
    x = _x_result(train_rows)
    margin = np.array([f.game.margin for f in train_rows], dtype=float)
    win = np.array([1.0 if m > 0 else 0.0 if m < 0 else 0.5 for m in margin])
    xt = _x_total(train_rows)
    total = np.array([f.game.home_score + f.game.away_score for f in train_rows], dtype=float)  # type: ignore[operator]

    spread = Ridge(alpha=1.0).fit(x, margin)
    total_model = Ridge(alpha=2.0).fit(xt, total)
    return FootballModel(
        win=Logistic(alpha=0.5).fit(x, win),
        spread=spread,
        total=total_model,
        margin_sd=spread.residual_sd(x, margin),
        total_sd=total_model.residual_sd(xt, total),
        train_size=len(train_rows),
    )


@dataclass
class FootballPrediction:
    game_id: int
    p_home_model: float
    p_home_market: float | None
    p_home: float  # published (blended when market exists)
    margin: float  # expected home margin (positive = home favored)
    total: float
    margin_sd: float
    total_sd: float
    market_spread_home: float | None
    market_total: float | None
    explanation: dict[str, float | str]


def predict(model: FootballModel, rows: list[Features]) -> list[FootballPrediction]:
    if not rows:
        return []
    x = _x_result(rows)
    xt = _x_total(rows)
    p_model = model.win.predict_proba(x)
    margins = model.spread.predict(x)
    totals = model.total.predict(xt)
    coef = model.win.coef_
    assert coef is not None
    out: list[FootballPrediction] = []
    for i, f in enumerate(rows):
        mk = market_probs(f.game.market)
        p_market = mk.get("home")
        spread_home = f.game.market.get("spread_home_line")
        if p_market is None and spread_home is not None:
            p_market = normal_cdf(-spread_home / MARGIN_SD_FALLBACK)
        p_pub = (
            BLEND_MODEL_WEIGHT * float(p_model[i]) + (1 - BLEND_MODEL_WEIGHT) * p_market
            if p_market is not None
            else float(p_model[i])
        )
        contributions = {
            name: round(float(coef[j] * x[i, j]), 3) for j, name in enumerate(FEATURE_NAMES)
        }
        explanation: dict[str, float | str] = {
            **contributions,
            "elo_home": round(f.elo_home),
            "elo_away": round(f.elo_away),
            "home_edge": round(f.home_adv),
            "rest_home": f.rest_home,
            "rest_away": f.rest_away,
            "form_home": round(f.form_home, 1),
            "form_away": round(f.form_away, 1),
            "blend": "60% model / 40% market" if p_market is not None else "model only",
        }
        out.append(
            FootballPrediction(
                game_id=f.game.id,
                p_home_model=float(p_model[i]),
                p_home_market=p_market,
                p_home=float(p_pub),
                margin=float(margins[i]),
                total=float(totals[i]),
                margin_sd=model.margin_sd,
                total_sd=model.total_sd,
                market_spread_home=spread_home,
                market_total=f.game.market.get("total_over_line"),
                explanation=explanation,
            )
        )
    return out
