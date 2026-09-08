"""Point-in-time features: walk games in kickoff order, record what each team
looked like *before* the game, then update with the result.

Elo here mirrors gimme_collectors.derive (same K, home advantage, margin
multiplier, season regression) so the web's Elo and the model's Elo agree.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from gimme_collectors.derive import ELO, _expected, _mov_multiplier
from gimme_predict.data import Game

FORM_N = 5
DEFAULT_REST = 7


@dataclass
class TeamState:
    elo: float = 1500.0
    season_id: int | None = None
    last_kickoff: datetime | None = None
    margins: deque[float] | None = None
    scored: deque[float] | None = None
    allowed: deque[float] | None = None
    games: int = 0

    def __post_init__(self) -> None:
        self.margins = deque(maxlen=FORM_N)
        self.scored = deque(maxlen=FORM_N)
        self.allowed = deque(maxlen=FORM_N)


@dataclass
class Features:
    game: Game
    elo_home: float
    elo_away: float
    rest_home: int
    rest_away: int
    form_home: float  # mean margin over last N
    form_away: float
    scored_home: float  # mean points/goals scored over last N
    scored_away: float
    allowed_home: float
    allowed_away: float
    games_home: int
    games_away: int

    @property
    def home_adv(self) -> float:
        return 0.0 if self.game.neutral else ELO[self.game.sport]["home"]

    @property
    def elo_diff(self) -> float:
        return self.elo_home + self.home_adv - self.elo_away

    def vector(self) -> list[float]:
        """Model inputs, scaled to roughly unit range."""
        rest = max(-7, min(7, self.rest_home - self.rest_away)) / 7.0
        return [
            self.elo_diff / 100.0,
            rest,
            (self.form_home - self.form_away) / 10.0,
        ]

    def as_dict(self) -> dict[str, float | int]:
        return {
            "elo_home": round(self.elo_home, 1),
            "elo_away": round(self.elo_away, 1),
            "elo_diff": round(self.elo_diff, 1),
            "rest_home": self.rest_home,
            "rest_away": self.rest_away,
            "form_home": round(self.form_home, 2),
            "form_away": round(self.form_away, 2),
            "scored_home": round(self.scored_home, 2),
            "scored_away": round(self.scored_away, 2),
            "allowed_home": round(self.allowed_home, 2),
            "allowed_away": round(self.allowed_away, 2),
            "games_home": self.games_home,
            "games_away": self.games_away,
        }


FEATURE_NAMES = ["elo_diff", "rest_diff", "form_diff"]


def _mean(values: deque[float] | None, default: float) -> float:
    return sum(values) / len(values) if values else default


def _rest_days(st: TeamState, kickoff: datetime) -> int:
    if st.last_kickoff is None:
        return DEFAULT_REST
    return max(0, min(21, (kickoff - st.last_kickoff).days))


def build_features(games: list[Game]) -> list[Features]:
    """One Features row per game (final or not), in kickoff order."""
    state: dict[int, TeamState] = defaultdict(TeamState)
    out: list[Features] = []
    league_avg = 24.0 if games and games[0].sport == "american_football" else 1.35

    for g in games:
        params = ELO[g.sport]
        for team_id in (g.home_id, g.away_id):
            st = state[team_id]
            if st.season_id is not None and st.season_id != g.season_id:
                st.elo = st.elo * (2 / 3) + 1500.0 / 3
            st.season_id = g.season_id
        h, a = state[g.home_id], state[g.away_id]

        out.append(
            Features(
                game=g,
                elo_home=h.elo,
                elo_away=a.elo,
                rest_home=_rest_days(h, g.kickoff),
                rest_away=_rest_days(a, g.kickoff),
                form_home=_mean(h.margins, 0.0),
                form_away=_mean(a.margins, 0.0),
                scored_home=_mean(h.scored, league_avg),
                scored_away=_mean(a.scored, league_avg),
                allowed_home=_mean(h.allowed, league_avg),
                allowed_away=_mean(a.allowed, league_avg),
                games_home=h.games,
                games_away=a.games,
            )
        )

        if not g.final:
            continue
        margin = g.margin
        diff = h.elo + (0.0 if g.neutral else params["home"]) - a.elo
        exp_home = _expected(diff)
        actual = 1.0 if margin > 0 else 0.0 if margin < 0 else 0.5
        k = params["k"]
        if params["mov"] and margin != 0:
            k *= _mov_multiplier(margin, diff if margin > 0 else -diff)
        delta = k * (actual - exp_home)
        h.elo += delta
        a.elo -= delta
        for st, gf, ga, sign in (
            (h, g.home_score, g.away_score, 1),
            (a, g.away_score, g.home_score, -1),
        ):
            assert gf is not None and ga is not None
            assert st.margins is not None and st.scored is not None and st.allowed is not None
            st.margins.append(sign * margin)
            st.scored.append(float(gf))
            st.allowed.append(float(ga))
            st.games += 1
            st.last_kickoff = g.kickoff
    return out


def normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))
