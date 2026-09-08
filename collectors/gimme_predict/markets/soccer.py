"""Soccer: match result and total goals with a Dixon-Coles Poisson model.

Each team gets an attack and a defence strength; home advantage is shared. Expected
goals are exp(attack_home - defence_away + home) and exp(attack_away - defence_home).
Older games count less (exponential time decay, half-life ~ 6 months). The
Dixon-Coles rho term corrects the Poisson's known bias on 0-0, 1-0, 0-1 and 1-1.

Fitted by gradient ascent with a ridge penalty that pulls strengths toward zero,
which keeps a league with only a few rounds played from over-reacting. When a
market line exists the published probabilities are blended 60/40 with it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np

from gimme_predict.data import Game, market_probs

MODEL_NAME = "soccer-dixon-coles"
MODEL_VERSION = "v1"
HALF_LIFE_DAYS = 180.0
MAX_GOALS = 8
BLEND_MODEL_WEIGHT = 0.6


@dataclass
class SoccerModel:
    teams: dict[int, int]  # team id -> index
    attack: np.ndarray
    defence: np.ndarray
    home: float
    rho: float
    train_size: int
    league_goals: float = 1.35

    def strengths(self, team_id: int) -> tuple[float, float]:
        i = self.teams.get(team_id)
        if i is None:
            return 0.0, 0.0
        return float(self.attack[i]), float(self.defence[i])


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    """Dixon-Coles low-score correction."""
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


def train(
    games: list[Game], *, as_of: datetime | None = None, ridge: float = 0.05, iterations: int = 300
) -> SoccerModel | None:
    finals = [g for g in games if g.final]
    if len(finals) < 30:
        return None
    as_of = as_of or max(g.kickoff for g in finals)
    teams: dict[int, int] = {}
    for g in finals:
        for t in (g.home_id, g.away_id):
            teams.setdefault(t, len(teams))
    n = len(teams)
    hi = np.array([teams[g.home_id] for g in finals])
    ai = np.array([teams[g.away_id] for g in finals])
    hg = np.array([g.home_score for g in finals], dtype=float)
    ag = np.array([g.away_score for g in finals], dtype=float)
    age = np.array([(as_of - g.kickoff).days for g in finals], dtype=float)
    w = np.power(0.5, np.clip(age, 0, None) / HALF_LIFE_DAYS)

    attack = np.zeros(n)
    defence = np.zeros(n)
    home = 0.25
    lr = 0.02
    for _ in range(iterations):
        lam = np.exp(attack[hi] - defence[ai] + home)
        mu = np.exp(attack[ai] - defence[hi])
        # gradient of weighted Poisson log-likelihood
        d_lam = w * (hg - lam)
        d_mu = w * (ag - mu)
        g_att = np.bincount(hi, d_lam, n) + np.bincount(ai, d_mu, n) - ridge * attack
        g_def = -np.bincount(ai, d_lam, n) - np.bincount(hi, d_mu, n) - ridge * defence
        g_home = float(np.sum(d_lam))
        attack += lr * g_att / max(1.0, np.sqrt(len(finals) / n))
        defence += lr * g_def / max(1.0, np.sqrt(len(finals) / n))
        home += lr * g_home / len(finals)
        attack -= attack.mean()  # identifiability
    # rho by a coarse grid on the corrected likelihood
    lam = np.exp(attack[hi] - defence[ai] + home)
    mu = np.exp(attack[ai] - defence[hi])
    best_rho, best_ll = 0.0, -math.inf
    for rho in np.linspace(-0.15, 0.05, 21):
        ll = 0.0
        for k in range(len(finals)):
            x, y = int(hg[k]), int(ag[k])
            t = _tau(x, y, lam[k], mu[k], rho)
            if t <= 0:
                ll = -math.inf
                break
            ll += w[k] * math.log(t)
        if ll > best_ll:
            best_ll, best_rho = ll, float(rho)
    return SoccerModel(
        teams=teams,
        attack=attack,
        defence=defence,
        home=home,
        rho=best_rho,
        train_size=len(finals),
        league_goals=float((hg.sum() + ag.sum()) / (2 * len(finals))),
    )


@dataclass
class SoccerPrediction:
    game_id: int
    lam: float  # expected home goals
    mu: float  # expected away goals
    p_model: dict[str, float]
    p_market: dict[str, float]
    p: dict[str, float]  # published
    over_25: float
    under_25: float
    btts: float
    explanation: dict[str, float | str] = field(default_factory=dict)


def _score_matrix(lam: float, mu: float, rho: float) -> np.ndarray:
    xs = np.arange(MAX_GOALS + 1)
    ph = np.exp(-lam) * np.power(lam, xs) / np.array([math.factorial(i) for i in xs])
    pa = np.exp(-mu) * np.power(mu, xs) / np.array([math.factorial(i) for i in xs])
    m = np.outer(ph, pa)
    for x in range(2):
        for y in range(2):
            m[x, y] *= _tau(x, y, lam, mu, rho)
    return m / m.sum()


def predict(model: SoccerModel, games: list[Game]) -> list[SoccerPrediction]:
    out: list[SoccerPrediction] = []
    for g in games:
        a_h, d_h = model.strengths(g.home_id)
        a_a, d_a = model.strengths(g.away_id)
        home = 0.0 if g.neutral else model.home
        # Attack strengths are centred on zero; the defence terms carry the league's
        # scoring level, so these are expected goals in real units.
        lam = math.exp(a_h - d_a + home)
        mu = math.exp(a_a - d_h)
        m = _score_matrix(lam, mu, model.rho)
        p_home = float(np.tril(m, -1).sum())
        p_draw = float(np.trace(m))
        p_away = float(np.triu(m, 1).sum())
        totals = np.add.outer(np.arange(MAX_GOALS + 1), np.arange(MAX_GOALS + 1))
        over = float(m[totals > 2.5].sum())
        btts = float(m[1:, 1:].sum())
        p_model = {"home": p_home, "draw": p_draw, "away": p_away}
        mk = market_probs(g.market)
        if mk and all(k in mk for k in ("home", "draw", "away")):
            p = {
                k: BLEND_MODEL_WEIGHT * p_model[k] + (1 - BLEND_MODEL_WEIGHT) * mk[k]
                for k in p_model
            }
        else:
            p = dict(p_model)
        out.append(
            SoccerPrediction(
                game_id=g.id,
                lam=lam,
                mu=mu,
                p_model=p_model,
                p_market=mk,
                p=p,
                over_25=over,
                under_25=1 - over,
                btts=btts,
                explanation={
                    "attack_home": round(a_h, 3),
                    "defence_home": round(d_h, 3),
                    "attack_away": round(a_a, 3),
                    "defence_away": round(d_a, 3),
                    "home_edge": round(home, 3),
                    "rho": round(model.rho, 3),
                    "blend": "60% model / 40% market" if mk else "model only",
                },
            )
        )
    return out
