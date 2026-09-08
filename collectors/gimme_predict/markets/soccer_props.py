"""Soccer props: shots on target and corners per team (negative-binomial GLM),
and goals, assists and shots on target per player.

Team counts: log E[count] = b0 + b1 log(team rate for) + b2 log(opponent rate against)
+ b3 home, over the last 8 games. Over/under probabilities use the fitted
negative-binomial dispersion.

Player markets: each player takes a share of the team's expected goals and
expected shots on target, weighted by their recent rate per appearance and by the
minutes they are expected to play. Assists come from the team's expected goals
scaled by the share of goals that are assisted, with the player's own share shrunk
toward their share of minutes because assists are sparse. Counts are Poisson, so
P(at least one) = 1 - exp(-lambda).
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


# ------------------------------------------------- goals, assists, shots

# Roughly three in four goals are assisted, so a team's assists are its expected
# goals scaled down; the rest are unassisted.
ASSIST_RATE = 0.75
# Assists are rare enough in an eight-game window that a raw share is mostly
# noise, so it is shrunk toward the player's share of minutes. This is the number
# of assists' worth of evidence needed before the observed share carries half the
# weight.
ASSIST_PRIOR_K = 4.0
MIN_EXPECTED_GOALS = 0.02
MIN_EXPECTED_SOT = 0.15
# A full lineup is worth about this much minutes-weighted presence once the
# goalkeeper is set aside. Early in a season only part of a squad has appeared,
# and the players we have no record of still take a share of the team's goals:
# without this the handful on record would split the whole total between them.
EXPECTED_SQUAD_WEIGHT = 10.0
# Appearances' worth of squad-average evidence mixed into every player's rate.
# One goal in one appearance is not a goal a game; this says so.
SHRINK_APPEARANCES = 4.0


@dataclass
class ScorerProp:
    """One player's attacking markets for one game.

    Shares are built so that a team's players sum back to the team's own expected
    goals and expected shots on target: nobody is projected in isolation.
    """

    game_id: int
    team_id: int
    player_id: int
    name: str
    position: str | None
    probability: float  # anytime scorer
    expected_goals: float
    expected_assists: float = 0.0
    assist_probability: float = 0.0
    expected_sot: float = 0.0
    sot_probability: float = 0.0  # one or more
    sot_two_probability: float = 0.0  # two or more
    explanation: dict[str, Any] = field(default_factory=dict)


def player_threat(rows: list[PlayerGame]) -> dict[int, Rolling]:
    """Rolling per-player attacking record from lineup rows (in kickoff order)."""
    players: dict[int, Rolling] = defaultdict(Rolling)
    for pg in rows:
        players[pg.player_id].push(soccer_values(pg.stats))
    return players


def _totals(r: Rolling) -> dict[str, float]:
    return {
        key: sum(v.get(key, 0.0) for v in r.window)
        for key in ("goals", "shots", "sot", "assists", "app", "start")
    }


def _poisson_at_least(lam: float, k: int) -> float:
    """P(X >= k) for a Poisson count, for k of 1 or 2."""
    if lam <= 0:
        return 0.0
    if k == 1:
        return 1 - math.exp(-lam)
    return 1 - math.exp(-lam) * (1 + lam)


def predict_players(
    game: Game,
    *,
    team_id: int,
    team_xg: float,
    team_sot: float | None,
    roster: list[dict[str, Any]],
    threat: dict[int, Rolling],
    team_games_window: int,
    play_probability: dict[int, float] | None = None,
) -> list[ScorerProp]:
    """Goals, assists and shots on target for one team's players in one game.

    `team_xg` is the team's expected goals from the match model and `team_sot`
    its expected shots on target from the count model. Each player takes a share
    of both, weighted by their recent rate and by how much of the match they are
    expected to be on the pitch for, so the parts add up to the team's total.

    Two corrections keep a short season honest. Rates are shrunk toward the
    squad average, so one goal in one appearance is not read as a goal a game.
    Shares are diluted when only part of a squad has appeared, so the players on
    record do not split a total that belongs to the whole team.
    """
    candidates: list[dict[str, Any]] = []
    for entry in roster:
        rolling = threat.get(entry["player_id"])
        if rolling is None or rolling.games == 0:
            continue
        totals = _totals(rolling)
        apps = totals["app"]
        if apps == 0:
            continue
        available = 1.0
        if play_probability is not None:
            available = play_probability.get(entry["player_id"], 1.0)
        if available <= 0:
            continue
        starter_rate = totals["start"] / apps
        # a substitute is on the pitch for roughly half a starter's minutes
        minutes_factor = 0.55 + 0.45 * starter_rate
        selection = min(1.0, apps / max(team_games_window, 1)) * available
        candidates.append(
            {
                "entry": entry,
                "apps": apps,
                "totals": totals,
                "starter_rate": starter_rate,
                "weight": selection * minutes_factor,
                "selection": selection,
            }
        )
    if not candidates:
        return []

    index = list(range(len(candidates)))
    appearances = sum(c["apps"] for c in candidates)

    def rate(i: int, key: str) -> float:
        """Per-appearance rate, pulled toward the squad average by the number of
        appearances still missing from a settled sample."""
        prior = (sum(c["totals"][key] for c in candidates) / appearances) if appearances else 0.0
        c = candidates[i]
        return (c["totals"][key] + SHRINK_APPEARANCES * prior) / (c["apps"] + SHRINK_APPEARANCES)

    weight_total = sum(c["weight"] for c in candidates)
    # the minutes belonging to players we have no record of
    missing_weight = max(0.0, EXPECTED_SQUAD_WEIGHT - weight_total)

    def divide(raw: dict[int, float]) -> dict[int, float]:
        """Share out a team total, leaving the unrecorded squad its part."""
        observed = sum(raw.values())
        if observed <= 0 or weight_total <= 0:
            return {}
        # the missing players are assumed to be as productive per minute as the
        # ones on record, which keeps a thin squad from inflating anybody
        per_weight = observed / weight_total
        total = observed + missing_weight * per_weight
        return {i: v / total for i, v in raw.items()}

    minutes_share = divide({i: candidates[i]["weight"] for i in index}) or {i: 0.0 for i in index}
    goal_share = divide(
        {
            i: (rate(i, "goals") + SHOT_WEIGHT * rate(i, "shots")) * candidates[i]["weight"]
            for i in index
        }
    ) or dict(minutes_share)
    sot_share = divide({i: rate(i, "sot") * candidates[i]["weight"] for i in index}) or dict(
        minutes_share
    )
    assist_raw = divide({i: rate(i, "assists") * candidates[i]["weight"] for i in index}) or dict(
        minutes_share
    )
    assists_seen = sum(c["totals"]["assists"] for c in candidates)
    blend = assists_seen / (assists_seen + ASSIST_PRIOR_K)
    assist_share = {
        i: blend * assist_raw[i] + (1 - blend) * minutes_share[i] for i in minutes_share
    }

    covered = round(min(1.0, weight_total / EXPECTED_SQUAD_WEIGHT), 2)
    team_assists = team_xg * ASSIST_RATE
    out: list[ScorerProp] = []
    for i in index:
        c = candidates[i]
        lam_goal = team_xg * goal_share[i]
        lam_assist = team_assists * assist_share[i]
        lam_sot = (team_sot * sot_share[i]) if team_sot else 0.0
        if lam_goal < MIN_EXPECTED_GOALS and lam_sot < MIN_EXPECTED_SOT:
            continue
        entry = c["entry"]
        apps = c["apps"]
        out.append(
            ScorerProp(
                game_id=game.id,
                team_id=team_id,
                player_id=entry["player_id"],
                name=entry["full_name"],
                position=entry.get("position"),
                probability=round(_poisson_at_least(lam_goal, 1), 4),
                expected_goals=round(lam_goal, 3),
                expected_assists=round(lam_assist, 3),
                assist_probability=round(_poisson_at_least(lam_assist, 1), 4),
                expected_sot=round(lam_sot, 2),
                sot_probability=round(_poisson_at_least(lam_sot, 1), 4),
                sot_two_probability=round(_poisson_at_least(lam_sot, 2), 4),
                explanation={
                    "team_expected_goals": round(team_xg, 2),
                    "team_expected_shots_on_target": round(team_sot, 2) if team_sot else None,
                    "share_of_team_threat": round(goal_share[i], 3),
                    "share_of_team_shots_on_target": round(sot_share[i], 3),
                    "goals_per_appearance": round(c["totals"]["goals"] / apps, 2),
                    "assists_per_appearance": round(c["totals"]["assists"] / apps, 2),
                    "shots_on_target_per_appearance": round(c["totals"]["sot"] / apps, 2),
                    "appearances_in_window": int(apps),
                    "starter_rate": round(c["starter_rate"], 2),
                    "play_probability": round(c["selection"], 2),
                    "squad_covered": covered,
                },
            )
        )
    out.sort(key=lambda s: -s.probability)
    return out
