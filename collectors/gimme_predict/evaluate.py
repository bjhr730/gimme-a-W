"""Back-tests: train on earlier seasons, predict the next, score against the market.

Football: log loss, Brier and accuracy of the model, the blend and the closing
moneyline; MAE of expected margin vs. the closing spread and of the total.
Soccer: multiclass log loss of 1X2 vs. the closing (Pinnacle) line; over 2.5 MAE.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from gimme_predict.data import Game, market_probs
from gimme_predict.features import build_features
from gimme_predict.markets import football, soccer
from gimme_predict.models import brier, log_loss, multiclass_log_loss


@dataclass
class SeasonResult:
    season: str
    games: int
    metrics: dict[str, float] = field(default_factory=dict)


def _seasons(games: list[Game]) -> list[str]:
    seen: list[str] = []
    for g in games:
        if g.final and g.season_label not in seen:
            seen.append(g.season_label)
    return seen


def backtest_football(games: list[Game], *, min_train_seasons: int = 2) -> list[SeasonResult]:
    features = build_features(games)
    seasons = _seasons(games)
    results: list[SeasonResult] = []
    for idx in range(min_train_seasons, len(seasons)):
        target = seasons[idx]
        train_rows = [f for f in features if f.game.season_label in seasons[:idx] and f.game.final]
        test_rows = [
            f
            for f in features
            if f.game.season_label == target
            and f.game.final
            and f.games_home >= 2
            and f.games_away >= 2
            and f.game.margin != 0
        ]
        model = football.train(train_rows)
        if model is None or not test_rows:
            continue
        preds = football.predict(model, test_rows)
        y = np.array([1.0 if f.game.margin > 0 else 0.0 for f in test_rows])
        margin = np.array([f.game.margin for f in test_rows], dtype=float)
        total = np.array([f.game.home_score + f.game.away_score for f in test_rows], dtype=float)  # type: ignore[operator]
        p_model = np.array([p.p_home_model for p in preds])
        p_blend = np.array([p.p_home for p in preds])
        metrics: dict[str, float] = {
            "model_log_loss": log_loss(y, p_model),
            "model_brier": brier(y, p_model),
            "model_accuracy": float(np.mean((p_model > 0.5) == (y > 0.5))),
            "blend_log_loss": log_loss(y, p_blend),
            "blend_accuracy": float(np.mean((p_blend > 0.5) == (y > 0.5))),
            "spread_mae_model": float(
                np.mean(np.abs(np.array([p.margin for p in preds]) - margin))
            ),
            "total_mae_model": float(np.mean(np.abs(np.array([p.total for p in preds]) - total))),
        }
        has_market = [i for i, p in enumerate(preds) if p.p_home_market is not None]
        if len(has_market) >= 20:
            pm = np.array([preds[i].p_home_market for i in has_market], dtype=float)
            metrics["market_log_loss"] = log_loss(y[has_market], pm)
            metrics["market_brier"] = brier(y[has_market], pm)
            metrics["market_accuracy"] = float(np.mean((pm > 0.5) == (y[has_market] > 0.5)))
            metrics["model_log_loss_on_market_games"] = log_loss(y[has_market], p_model[has_market])
            metrics["blend_log_loss_on_market_games"] = log_loss(y[has_market], p_blend[has_market])
            metrics["market_coverage"] = len(has_market) / len(preds)
        spreads = [i for i, p in enumerate(preds) if p.market_spread_home is not None]
        if len(spreads) >= 20:
            line = np.array([-preds[i].market_spread_home for i in spreads], dtype=float)  # type: ignore[operator]
            metrics["spread_mae_market"] = float(np.mean(np.abs(line - margin[spreads])))
        totals = [i for i, p in enumerate(preds) if p.market_total is not None]
        if len(totals) >= 20:
            line = np.array([preds[i].market_total for i in totals], dtype=float)
            metrics["total_mae_market"] = float(np.mean(np.abs(line - total[totals])))
        results.append(SeasonResult(season=target, games=len(test_rows), metrics=metrics))
    return results


def backtest_soccer(games: list[Game], *, min_train_seasons: int = 1) -> list[SeasonResult]:
    seasons = _seasons(games)
    results: list[SeasonResult] = []
    for idx in range(min_train_seasons, len(seasons)):
        target = seasons[idx]
        train_games = [g for g in games if g.season_label in seasons[:idx]]
        test_games = [g for g in games if g.season_label == target and g.final]
        if len(test_games) < 30:
            continue
        # walk the target season so each game is predicted with what preceded it
        preds = []
        history = list(train_games)
        model = soccer.train(history)
        for k, g in enumerate(test_games):
            if k % 40 == 0 and k > 0:
                model = soccer.train(history + test_games[:k])
            if model is None:
                break
            preds.extend(soccer.predict(model, [g]))
        if len(preds) != len(test_games):
            continue
        outcome = np.array([0 if g.margin > 0 else 1 if g.margin == 0 else 2 for g in test_games])
        pm = np.array([[p.p_model["home"], p.p_model["draw"], p.p_model["away"]] for p in preds])
        pb = np.array([[p.p["home"], p.p["draw"], p.p["away"]] for p in preds])
        total = np.array([g.home_score + g.away_score for g in test_games], dtype=float)  # type: ignore[operator]
        metrics: dict[str, float] = {
            "model_log_loss": multiclass_log_loss(outcome, pm),
            "blend_log_loss": multiclass_log_loss(outcome, pb),
            "model_accuracy": float(np.mean(pm.argmax(axis=1) == outcome)),
            "total_goals_mae_model": float(
                np.mean(np.abs(np.array([p.lam + p.mu for p in preds]) - total))
            ),
        }
        with_market = [i for i, p in enumerate(preds) if len(p.p_market) == 3]
        if len(with_market) >= 30:
            mk = np.array(
                [[preds[i].p_market[k] for k in ("home", "draw", "away")] for i in with_market]
            )
            metrics["market_log_loss"] = multiclass_log_loss(outcome[with_market], mk)
            metrics["model_log_loss_on_market_games"] = multiclass_log_loss(
                outcome[with_market], pm[with_market]
            )
            metrics["blend_log_loss_on_market_games"] = multiclass_log_loss(
                outcome[with_market], pb[with_market]
            )
            metrics["market_coverage"] = len(with_market) / len(preds)
        results.append(SeasonResult(season=target, games=len(test_games), metrics=metrics))
    return results


def summarize(results: list[SeasonResult]) -> dict[str, Any]:
    if not results:
        return {"seasons": [], "overall": {}}
    keys = sorted({k for r in results for k in r.metrics})
    total_games = sum(r.games for r in results)
    overall = {}
    for k in keys:
        rows = [(r.metrics[k], r.games) for r in results if k in r.metrics]
        overall[k] = round(sum(v * n for v, n in rows) / sum(n for _, n in rows), 4)
    return {
        "seasons": [
            {"season": r.season, "games": r.games, **{k: round(v, 4) for k, v in r.metrics.items()}}
            for r in results
        ],
        "overall": {**overall, "games": total_games},
    }


def _unused(_: Any) -> None:  # keep imports referenced for type checkers
    market_probs({})
