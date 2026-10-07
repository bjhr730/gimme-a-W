"""Orchestration for player and team markets: train, predict upcoming, back-test."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import psycopg

from gimme_predict import availability, data
from gimme_predict.markets import football_players, soccer_props
from gimme_predict.models import log_loss
from gimme_predict.players import (
    football_values,
    load_player_games,
    load_rosters,
    load_team_games,
    rostered_anywhere,
    walk_football,
)

# How far back an appearance can stand in for a roster row. Long enough to cover
# a player who has been out injured, short enough that last season's squad does
# not come back.
LINEUP_FALLBACK_WINDOW = timedelta(days=75)


@dataclass
class PropsOutput:
    football: list[football_players.PlayerProp] = field(default_factory=list)
    team_counts: list[soccer_props.TeamProp] = field(default_factory=list)
    train_size: dict[str, int] = field(default_factory=dict)
    # players withheld because a source reports them out, and players kept but
    # flagged as a doubt; both are reported in the model run's metrics.
    withheld: int = 0
    flagged: int = 0

    def count(self) -> int:
        return len(self.football) + len(self.team_counts)


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
    statuses = availability.load(conn, team_ids)
    # Players with stats but no roster row anywhere (some nflverse ids) fall back to
    # the team of their last game. Anyone with a roster row is placed by the roster
    # only, so a player who moved clubs is not listed for the old one as well.
    last_team: dict[int, tuple[int, str, str | None]] = {}
    for pg in rows:
        last_team[pg.player_id] = (pg.team_id, pg.name, pg.position)
    has_roster = rostered_anywhere(conn, list(last_team))
    out = PropsOutput(train_size=model.train_size)
    for g in upcoming:
        for team_id, home in ((g.home_id, True), (g.away_id, False)):
            listed = {r["player_id"]: r for r in rosters.get(team_id, [])}
            for pid, (tid, name, pos) in last_team.items():
                if tid == team_id and pid not in listed and pid not in has_roster:
                    listed[pid] = {"player_id": pid, "full_name": name, "position": pos}
            for pid, r in listed.items():
                if pid not in players:
                    continue
                status = statuses.get(pid)
                if status is not None and status.out:
                    out.withheld += 1
                    continue
                projected = football_players.predict_player(
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
                if status is not None and status.availability != "available" and projected:
                    out.flagged += 1
                    apply_status(projected, status)
                out.football.extend(projected)
    return out


def apply_status(rows: list[football_players.PlayerProp], status: availability.Status) -> None:
    """Record the report on every market, and scale the ones that ask whether an
    event happens at all. A yards projection is conditional on the player taking
    the field, so it is labelled rather than shrunk."""
    for row in rows:
        row.explanation = {**row.explanation, "availability": status.summary()}
        if row.probability is not None and status.doubt:
            row.probability = round(row.probability * status.play_probability, 5)


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
    conn: psycopg.Connection[Any],
    slug: str,
    upcoming: list[data.Game],
    games: list[data.Game],
) -> PropsOutput | None:
    """Shots on target and corners per team. Nothing per player.

    `games` is unused: it fed an expected-goals fit that existed only to split a
    team's total across its players. The match model still runs, separately --
    this no longer refits it.
    """
    del games
    team_rows = load_team_games(conn, slug)
    out = PropsOutput()
    counts_model = soccer_props.train(team_rows) if team_rows else None
    if counts_model is not None:
        out.train_size.update(counts_model.train_size)
        for g in upcoming:
            out.team_counts.extend(soccer_props.predict_counts(counts_model, g))
    # No player markets in soccer. The team counts above -- shots on target and
    # corners per side -- are what this competition publishes now. Dropping the
    # player half also drops the heaviest read in the pipeline: a squad's whole
    # box-score history, loaded across every competition its clubs play in.
    return out if out.count() else None


def _unused(_: datetime) -> None:
    pass
