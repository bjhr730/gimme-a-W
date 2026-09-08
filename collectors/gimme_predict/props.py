"""Orchestration for player and team markets: train, predict upcoming, back-test."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import numpy as np
import psycopg

from gimme_predict import data
from gimme_predict.markets import football_players, soccer, soccer_props
from gimme_predict.models import log_loss
from gimme_predict.players import (
    Rolling,
    football_values,
    load_player_games,
    load_rosters,
    load_team_games,
    walk_football,
)


@dataclass
class PropsOutput:
    football: list[football_players.PlayerProp] = field(default_factory=list)
    team_counts: list[soccer_props.TeamProp] = field(default_factory=list)
    scorers: list[soccer_props.ScorerProp] = field(default_factory=list)
    train_size: dict[str, int] = field(default_factory=dict)

    def count(self) -> int:
        return len(self.football) + len(self.team_counts) + len(self.scorers)


# ------------------------------------------------------------ football


def predict_football(
    conn: psycopg.Connection[Any], slug: str, upcoming: list[data.Game], games: list[data.Game]
) -> PropsOutput | None:
    rows = load_player_games(conn, slug)
    if not rows:
        return None
    games_by_id = {g.id: g for g in games}
    history, players, teams, allowed = walk_football(rows, games_by_id)
    model = football_players.train(history)
    if model is None:
        return None
    team_ids = sorted({t for g in upcoming for t in (g.home_id, g.away_id)})
    rosters = load_rosters(conn, team_ids)
    # players seen recently but missing from a roster (nflverse ids) still get predictions
    last_team: dict[int, tuple[int, str, str | None]] = {}
    for pg in rows:
        last_team[pg.player_id] = (pg.team_id, pg.name, pg.position)
    out = PropsOutput(train_size=model.train_size)
    for g in upcoming:
        for team_id, home in ((g.home_id, True), (g.away_id, False)):
            listed = {r["player_id"]: r for r in rosters.get(team_id, [])}
            for pid, (tid, name, pos) in last_team.items():
                if tid == team_id and pid not in listed:
                    listed[pid] = {"player_id": pid, "full_name": name, "position": pos}
            for pid, r in listed.items():
                if pid not in players:
                    continue
                out.football.extend(
                    football_players.predict_player(
                        model,
                        game=g,
                        home=home,
                        player_id=pid,
                        team_id=team_id,
                        name=r["full_name"],
                        position=r.get("position"),
                        player=players[pid],
                        team=teams[team_id],
                        allowed=allowed[g.away_id if home else g.home_id],
                    )
                )
    return out


def backtest_football(
    conn: psycopg.Connection[Any],
    slug: str,
    games: list[data.Game],
    *,
    holdout_season: str | None = None,
) -> dict[str, Any]:
    """Train on all but the last season, score the last season."""
    rows = load_player_games(conn, slug)
    if not rows:
        return {}
    games_by_id = {g.id: g for g in games}
    history, _, _, _ = walk_football(rows, games_by_id)
    seasons = []
    for r in history:
        if r.game and r.game.season_label not in seasons:
            seasons.append(r.game.season_label)
    if len(seasons) < 2:
        return {}
    target = holdout_season or seasons[-1]
    train_rows = [
        r
        for r in history
        if r.game and r.game.season_label != target and r.game.season_label < target
    ]
    test_rows = [r for r in history if r.game and r.game.season_label == target]
    model = football_players.train(train_rows)
    if model is None:
        return {}
    metrics: dict[str, Any] = {"holdout_season": target, "train_rows": len(train_rows)}
    for cat, (volume_key, yards_key) in football_players.CATEGORIES.items():
        ridge = model.yards.get(cat)
        if ridge is None:
            continue
        sample = [
            r
            for r in test_rows
            if r.player.games >= football_players.MIN_GAMES
            and r.player.mean(volume_key) >= (5 if cat == "passing" else 1.5)
        ]
        if len(sample) < 30:
            continue
        x = np.array(
            [
                football_players.yards_features(
                    r.player, r.team, r.opp_allowed, r.game, r.pg.home, cat
                )
                for r in sample
            ]
        )
        actual = np.array([football_values(r.pg.stats)[yards_key] for r in sample])
        z = ridge.predict(x)
        mean = football_players.from_model_space(cat, z)
        q25, q75 = model.residual_q[cat]
        lo = football_players.from_model_space(cat, z + q25)
        hi = football_players.from_model_space(cat, z + q75)
        naive = np.array([r.player.mean(yards_key) for r in sample])
        metrics[f"{cat}_yards"] = {
            "n": len(sample),
            "mae_model": round(float(np.mean(np.abs(mean - actual))), 2),
            "mae_naive_average": round(float(np.mean(np.abs(naive - actual))), 2),
            "coverage_25_75": round(float(np.mean((actual >= lo) & (actual <= hi))), 3),
        }
    if model.td is not None:
        sample = [
            r
            for r in test_rows
            if r.player.games >= football_players.MIN_GAMES and r.player.mean("touches") >= 1.0
        ]
        if len(sample) >= 50:
            x = np.array(
                [
                    football_players.td_features(r.player, r.team, r.opp_allowed, r.game, r.pg.home)
                    for r in sample
                ]
            )
            y = np.array([1.0 if football_values(r.pg.stats)["td"] > 0 else 0.0 for r in sample])
            p = model.td.predict_proba(x)
            base = np.full(len(y), float(np.mean(y)))
            metrics["anytime_td"] = {
                "n": len(sample),
                "log_loss_model": round(log_loss(y, p), 4),
                "log_loss_base_rate": round(log_loss(y, base), 4),
                "base_rate": round(float(np.mean(y)), 3),
            }
    return metrics


# -------------------------------------------------------------- soccer


def predict_soccer(
    conn: psycopg.Connection[Any], slug: str, upcoming: list[data.Game], games: list[data.Game]
) -> PropsOutput | None:
    team_rows = load_team_games(conn, slug)
    out = PropsOutput()
    counts_model = soccer_props.train(team_rows) if team_rows else None
    if counts_model is not None:
        out.train_size.update(counts_model.train_size)
        for g in upcoming:
            out.team_counts.extend(soccer_props.predict_counts(counts_model, g))
    # expected goals per team: Dixon-Coles when it fits, else rolling goals
    xg_model = soccer.train(games)
    xg: dict[int, tuple[float, float]] = {}
    if xg_model is not None:
        for p in soccer.predict(xg_model, upcoming):
            xg[p.game_id] = (p.lam, p.mu)
    else:
        state = counts_model.state if counts_model else {}
        for g in upcoming:
            h = state.get(g.home_id)
            a = state.get(g.away_id)
            xg[g.id] = (
                (sum(h.goals) / len(h.goals)) if h and h.goals else 1.4,
                (sum(a.goals) / len(a.goals)) if a and a.goals else 1.1,
            )
    player_rows = load_player_games(conn, slug)
    if player_rows:
        threat = soccer_props.player_threat(player_rows)
        team_games: dict[int, list[int]] = defaultdict(list)
        for pg in player_rows:
            if pg.game_id not in team_games[pg.team_id]:
                team_games[pg.team_id].append(pg.game_id)
        team_ids = sorted({t for g in upcoming for t in (g.home_id, g.away_id)})
        rosters = load_rosters(conn, team_ids)
        # players in recent lineups count as rostered even without a roster pull
        for pg in player_rows[-4000:]:
            lst = rosters.setdefault(pg.team_id, [])
            if all(r["player_id"] != pg.player_id for r in lst):
                lst.append(
                    {"player_id": pg.player_id, "full_name": pg.name, "position": pg.position}
                )
        for g in upcoming:
            lam, mu = xg.get(g.id, (1.4, 1.1))
            for team_id, team_xg in ((g.home_id, lam), (g.away_id, mu)):
                window = min(len(team_games.get(team_id, [])), Rolling().n)
                out.scorers.extend(
                    soccer_props.predict_scorers(
                        g,
                        team_id=team_id,
                        team_xg=team_xg,
                        roster=rosters.get(team_id, []),
                        threat=threat,
                        team_games_window=window,
                    )
                )
    return out if out.count() else None


def _unused(_: datetime) -> None:
    pass
