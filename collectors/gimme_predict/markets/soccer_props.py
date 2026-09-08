"""Soccer props: shots on target and corners per team (negative-binomial GLM) and
anytime goalscorer per player (expected goals share).

Team counts: log E[count] = b0 + b1 log(team rate for) + b2 log(opponent rate against)
+ b3 home, over the last 8 games. Over/under probabilities use the fitted
negative-binomial dispersion.

Anytime scorer: lambda = team expected goals x player's share of the team's
recent goal threat (goals plus a fraction of shots) x probability of playing.
P(scores) = 1 - exp(-lambda).
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from gimme_predict.data import Game
from gimme_predict.models import PoissonGLM
from gimme_predict.players import ROLL_N, PlayerGame, Rolling, soccer_values

MODEL_NAME = "soccer-props"
MODEL_VERSION = "v1"
COUNT_MARKETS = {"shots_on_target": "shotsOnTarget", "corners": "wonCorners"}
LINES = {"shots_on_target": [2.5, 3.5, 4.5, 5.5], "corners": [3.5, 4.5, 5.5, 6.5]}
MATCH_CORNER_LINES = [7.5, 8.5, 9.5, 10.5, 11.5]
SHOT_WEIGHT = 0.12  # a shot is worth this many goals of "threat" for share purposes
MIN_TEAM_GAMES = 3


@dataclass
class TeamState:
    for_: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=ROLL_N))
    )
    against: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=ROLL_N))
    )
    goals: deque[float] = field(default_factory=lambda: deque(maxlen=ROLL_N))

    def rate(self, kind: str, key: str, default: float) -> float:
        window = self.for_[key] if kind == "for" else self.against[key]
        return sum(window) / len(window) if window else default

    def games(self, key: str) -> int:
        return len(self.for_[key])


DEFAULTS = {"shotsOnTarget": 4.3, "wonCorners": 5.0}


def _features(team: TeamState, opp: TeamState, key: str, home: bool) -> list[float]:
    d = DEFAULTS[key]
    return [
        math.log(max(team.rate("for", key, d), 0.3)),
        math.log(max(opp.rate("against", key, d), 0.3)),
        1.0 if home else 0.0,
    ]


@dataclass
class SoccerPropsModel:
    counts: dict[str, PoissonGLM]
    state: dict[int, TeamState]
    train_size: dict[str, int]


def train(team_rows: list[dict[str, Any]]) -> SoccerPropsModel | None:
    """team_rows: (game, team) rows with stats, kickoff order (players.load_team_games)."""
    state: dict[int, TeamState] = defaultdict(TeamState)
    samples: dict[str, list[tuple[list[float], float]]] = {k: [] for k in COUNT_MARKETS}
    by_game: dict[int, list[dict[str, Any]]] = defaultdict(list)
    order: list[int] = []
    for r in team_rows:
        if r["game_id"] not in order:
            order.append(r["game_id"])
        by_game[r["game_id"]].append(r)
    for game_id in order:
        rows = by_game[game_id]
        for r in rows:
            team, opp = state[r["team_id"]], state[r["opp_id"]]
            for market, key in COUNT_MARKETS.items():
                value = r["stats"].get(key)
                if (
                    value is None
                    or team.games(key) < MIN_TEAM_GAMES
                    or opp.games(key) < MIN_TEAM_GAMES
                ):
                    continue
                samples[market].append((_features(team, opp, key, bool(r["home"])), float(value)))
        for r in rows:
            team = state[r["team_id"]]
            opp = state[r["opp_id"]]
            for key in COUNT_MARKETS.values():
                value = r["stats"].get(key)
                if value is not None:
                    team.for_[key].append(float(value))
                    opp.against[key].append(float(value))
            goals = r["stats"].get("totalGoals")
            if goals is not None:
                team.goals.append(float(goals))
    models: dict[str, PoissonGLM] = {}
    sizes: dict[str, int] = {}
    for market, sample in samples.items():
        if len(sample) < 60:
            continue
        x = np.array([s[0] for s in sample])
        y = np.array([s[1] for s in sample])
        models[market] = PoissonGLM(alpha=0.1).fit(x, y)
        sizes[market] = len(sample)
    if not models:
        return None
    return SoccerPropsModel(counts=models, state=state, train_size=sizes)


@dataclass
class TeamProp:
    game_id: int
    team_id: int | None  # None = whole match
    market: str
    mean: float
    lines: dict[str, float]  # "over 4.5" -> probability
    explanation: dict[str, Any] = field(default_factory=dict)


def predict_counts(model: SoccerPropsModel, game: Game) -> list[TeamProp]:
    out: list[TeamProp] = []
    means: dict[str, dict[str, float]] = defaultdict(dict)
    for market, key in COUNT_MARKETS.items():
        glm = model.counts.get(market)
        if glm is None:
            continue
        for side, team_id, opp_id in (
            ("home", game.home_id, game.away_id),
            ("away", game.away_id, game.home_id),
        ):
            team, opp = model.state[team_id], model.state[opp_id]
            if team.games(key) < MIN_TEAM_GAMES:
                continue
            mu = float(glm.predict(np.array([_features(team, opp, key, side == "home")]))[0])
            means[market][side] = mu
            out.append(
                TeamProp(
                    game_id=game.id,
                    team_id=team_id,
                    market=market,
                    mean=round(mu, 2),
                    lines={
                        f"over {line}": round(glm.prob_over(mu, line), 4) for line in LINES[market]
                    },
                    explanation={
                        "team_rate_for": round(team.rate("for", key, DEFAULTS[key]), 2),
                        "opponent_rate_against": round(opp.rate("against", key, DEFAULTS[key]), 2),
                        "dispersion": round(glm.dispersion_, 3),
                        "games_in_window": team.games(key),
                    },
                )
            )
        if market == "corners" and len(means[market]) == 2:
            total = means[market]["home"] + means[market]["away"]
            glm = model.counts[market]
            out.append(
                TeamProp(
                    game_id=game.id,
                    team_id=None,
                    market="match_corners",
                    mean=round(total, 2),
                    lines={
                        f"over {line}": round(glm.prob_over(total, line), 4)
                        for line in MATCH_CORNER_LINES
                    },
                    explanation={
                        "home_expected": round(means[market]["home"], 2),
                        "away_expected": round(means[market]["away"], 2),
                    },
                )
            )
    return out


# ------------------------------------------------------------ scorers


@dataclass
class ScorerProp:
    game_id: int
    team_id: int
    player_id: int
    name: str
    position: str | None
    probability: float
    expected_goals: float
    explanation: dict[str, Any] = field(default_factory=dict)


def player_threat(rows: list[PlayerGame]) -> dict[int, Rolling]:
    """Rolling per-player goal threat from lineup rows (already in kickoff order)."""
    players: dict[int, Rolling] = defaultdict(Rolling)
    for pg in rows:
        players[pg.player_id].push(soccer_values(pg.stats))
    return players


def predict_scorers(
    game: Game,
    *,
    team_id: int,
    team_xg: float,
    roster: list[dict[str, Any]],
    threat: dict[int, Rolling],
    team_games_window: int,
) -> list[ScorerProp]:
    """Anytime scorer probabilities for one team's players in one game."""
    candidates = []
    for p in roster:
        r = threat.get(p["player_id"])
        if r is None or r.games == 0:
            continue
        apps = sum(v.get("app", 0.0) for v in r.window)
        if apps == 0:
            continue
        per_app_threat = (
            sum(v.get("goals", 0.0) + SHOT_WEIGHT * v.get("shots", 0.0) for v in r.window) / apps
        )
        play_prob = min(1.0, apps / max(team_games_window, 1))
        starts = sum(v.get("start", 0.0) for v in r.window) / apps
        minutes_factor = 0.55 + 0.45 * starts  # subs see roughly half the minutes
        candidates.append((p, r, per_app_threat, play_prob, minutes_factor))
    team_threat = sum(c[2] * c[3] * c[4] for c in candidates)
    if team_threat <= 0:
        return []
    out: list[ScorerProp] = []
    for p, r, per_app_threat, play_prob, minutes_factor in candidates:
        share = per_app_threat * minutes_factor / team_threat
        lam = (
            team_xg * share * play_prob * (1 / max(play_prob, 1e-6)) * play_prob
        )  # = team_xg * share * play_prob
        lam = team_xg * share * play_prob
        if lam <= 0.02:
            continue
        out.append(
            ScorerProp(
                game_id=game.id,
                team_id=team_id,
                player_id=p["player_id"],
                name=p["full_name"],
                position=p.get("position"),
                probability=round(1 - math.exp(-lam), 4),
                expected_goals=round(lam, 3),
                explanation={
                    "team_expected_goals": round(team_xg, 2),
                    "share_of_team_threat": round(share, 3),
                    "goals_per_app_last_games": round(
                        sum(v.get("goals", 0.0) for v in r.window) / apps_of(r), 2
                    ),
                    "shots_per_app_last_games": round(
                        sum(v.get("shots", 0.0) for v in r.window) / apps_of(r), 2
                    ),
                    "play_probability": round(play_prob, 2),
                    "starter_rate": round(
                        sum(v.get("start", 0.0) for v in r.window) / apps_of(r), 2
                    ),
                },
            )
        )
    out.sort(key=lambda s: -s.probability)
    return out


def apps_of(r: Rolling) -> float:
    return max(sum(v.get("app", 0.0) for v in r.window), 1.0)
