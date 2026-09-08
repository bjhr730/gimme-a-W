"""NFL / college player markets: passing, rushing, receiving yards and anytime touchdown.

Yards: ridge on log1p(yards) with rolling usage, share of team volume, what the
opponent's defence has allowed, and the game script from the market (team spread,
total). The middle-half range comes from the empirical residual quantiles in log
space, so busy players get wider ranges in yards than fringe players.

Anytime TD: logistic on rolling touchdown rate, share of team touches, opponent
touchdowns allowed, and the team's implied points from the market.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from gimme_predict.data import Game
from gimme_predict.models import Logistic, Ridge
from gimme_predict.players import PlayerRow, Rolling, football_values

MODEL_NAME = "football-player-props"
MODEL_VERSION = "v1"

CATEGORIES = {
    "passing": ("attempts", "passYds"),
    "rushing": ("carries", "rushYds"),
    "receiving": ("targets", "recYds"),
}
# Rushing and receiving are skewed (many small games, a few huge ones): fit in log
# space. Passing is roughly symmetric around a large mean: fit raw yards.
LOG_SPACE = {"passing": False, "rushing": True, "receiving": True}
MIN_GAMES = 3


def to_model_space(cat: str, yards: np.ndarray) -> np.ndarray:
    return np.log1p(np.maximum(yards, 0.0)) if LOG_SPACE[cat] else yards


def from_model_space(cat: str, z: np.ndarray) -> np.ndarray:
    return np.expm1(z) if LOG_SPACE[cat] else np.maximum(z, 0.0)


def implied_points(game: Game | None, home: bool) -> tuple[float, float]:
    """(team implied points, team spread) from the market; league-average fallback."""
    if game is None:
        return 22.0, 0.0
    total = game.market.get("total_over_line", 44.0)
    spread_home = game.market.get("spread_home_line")
    if spread_home is None:
        return total / 2.0, 0.0
    team_spread = spread_home if home else -spread_home
    return (total - team_spread) / 2.0, team_spread


def yards_features(
    player: Rolling, team: Rolling, allowed: Rolling, game: Game | None, home: bool, cat: str
) -> list[float]:
    volume_key, yards_key = CATEGORIES[cat]
    team_vol = team.mean(volume_key)
    share = player.mean(volume_key) / team_vol if team_vol > 0 else 0.0
    points, spread = implied_points(game, home)
    # rolling yards can be negative (kneel-downs, sacks): clip before the log
    return [
        np.log1p(max(player.mean(yards_key), 0.0)),
        player.mean(volume_key) / 10.0,
        share,
        np.log1p(max(allowed.mean(yards_key), 0.0))
        if allowed.games
        else np.log1p(200.0 if cat == "passing" else 100.0),
        points / 10.0,
        spread / 10.0,
        1.0 if home else 0.0,
    ]


def td_features(
    player: Rolling, team: Rolling, allowed: Rolling, game: Game | None, home: bool
) -> list[float]:
    team_touch = team.mean("touches")
    points, _ = implied_points(game, home)
    return [
        player.mean("td"),
        player.mean("touches") / team_touch if team_touch > 0 else 0.0,
        player.mean("carries") / 10.0,
        player.mean("targets") / 10.0,
        allowed.mean("td") if allowed.games else 2.5,
        points / 10.0,
        1.0 if home else 0.0,
    ]


@dataclass
class PropsModel:
    yards: dict[str, Ridge]
    residual_q: dict[str, tuple[float, float]]  # (q25, q75) of log-space residuals
    td: Logistic | None
    train_size: dict[str, int] = field(default_factory=dict)


def train(rows: list[PlayerRow]) -> PropsModel | None:
    yards: dict[str, Ridge] = {}
    residual_q: dict[str, tuple[float, float]] = {}
    sizes: dict[str, int] = {}
    for cat, (volume_key, yards_key) in CATEGORIES.items():
        sample = [
            r
            for r in rows
            if r.player.games >= MIN_GAMES
            and r.player.mean(volume_key) >= (5 if cat == "passing" else 1.5)
        ]
        if len(sample) < 40:
            continue
        x = np.array(
            [
                yards_features(r.player, r.team, r.opp_allowed, r.game, r.pg.home, cat)
                for r in sample
            ]
        )
        y = to_model_space(
            cat, np.array([football_values(r.pg.stats)[yards_key] for r in sample], dtype=float)
        )
        model = Ridge(alpha=1.0).fit(x, y)
        resid = y - model.predict(x)
        yards[cat] = model
        residual_q[cat] = (float(np.quantile(resid, 0.25)), float(np.quantile(resid, 0.75)))
        sizes[cat] = len(sample)
    td_rows = [r for r in rows if r.player.games >= MIN_GAMES and r.player.mean("touches") >= 1.0]
    td_model = None
    if len(td_rows) >= 80:
        x = np.array(
            [td_features(r.player, r.team, r.opp_allowed, r.game, r.pg.home) for r in td_rows]
        )
        y = np.array([1.0 if football_values(r.pg.stats)["td"] > 0 else 0.0 for r in td_rows])
        td_model = Logistic(alpha=0.5).fit(x, y)
        sizes["td"] = len(td_rows)
    if not yards and td_model is None:
        return None
    return PropsModel(yards=yards, residual_q=residual_q, td=td_model, train_size=sizes)


@dataclass
class PlayerProp:
    game_id: int
    player_id: int
    team_id: int
    name: str
    position: str | None
    market: str  # passing_yards | rushing_yards | receiving_yards | anytime_td
    mean: float | None = None
    p25: float | None = None
    p75: float | None = None
    probability: float | None = None
    explanation: dict[str, Any] = field(default_factory=dict)


def predict_player(
    model: PropsModel,
    *,
    game: Game,
    home: bool,
    player_id: int,
    team_id: int,
    name: str,
    position: str | None,
    player: Rolling,
    team: Rolling,
    allowed: Rolling,
) -> list[PlayerProp]:
    if player.games < MIN_GAMES:
        return []
    out: list[PlayerProp] = []
    points, spread = implied_points(game, home)
    base_expl = {
        "games_in_window": player.games,
        "team_implied_points": round(points, 1),
        "team_spread": spread,
    }
    for cat, (volume_key, yards_key) in CATEGORIES.items():
        ridge = model.yards.get(cat)
        if ridge is None:
            continue
        volume = player.mean(volume_key)
        if volume < (5 if cat == "passing" else 1.5):
            continue
        x = np.array([yards_features(player, team, allowed, game, home, cat)])
        z = float(ridge.predict(x)[0])
        if not np.isfinite(z):
            continue
        q25, q75 = model.residual_q[cat]
        mean, lo, hi = from_model_space(cat, np.array([z, z + q25, z + q75]))
        out.append(
            PlayerProp(
                game_id=game.id,
                player_id=player_id,
                team_id=team_id,
                name=name,
                position=position,
                market=f"{cat}_yards",
                mean=round(float(mean), 1),
                p25=round(float(lo), 1),
                p75=round(float(hi), 1),
                explanation={
                    **base_expl,
                    "avg_yards_last_games": round(player.mean(yards_key), 1),
                    "avg_volume_last_games": round(volume, 1),
                    "share_of_team_volume": round(
                        player.mean(volume_key) / team.mean(volume_key), 3
                    )
                    if team.mean(volume_key)
                    else None,
                    "opponent_allowed_per_game": round(allowed.mean(yards_key), 1)
                    if allowed.games
                    else None,
                },
            )
        )
    if model.td is not None and player.mean("touches") >= 1.0:
        x = np.array([td_features(player, team, allowed, game, home)])
        p = float(model.td.predict_proba(x)[0])
        out.append(
            PlayerProp(
                game_id=game.id,
                player_id=player_id,
                team_id=team_id,
                name=name,
                position=position,
                market="anytime_td",
                probability=round(p, 4),
                explanation={
                    **base_expl,
                    "td_per_game_last_games": round(player.mean("td"), 2),
                    "touches_per_game": round(player.mean("touches"), 1),
                    "opponent_td_allowed_per_game": round(allowed.mean("td"), 2)
                    if allowed.games
                    else None,
                },
            )
        )
    return out
