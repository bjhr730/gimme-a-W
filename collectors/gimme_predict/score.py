"""Live scorecard: grade published predictions against results as games finish.

Back-tests say how a model *would* have done; this says how the predictions the
site actually showed *did*. Each run stores one model_run row (model
"scorecard") whose metrics hold, per competition over the window: games graded,
log loss and accuracy of our published probability, and the same for the closing
line when we have one. The models page shows the latest.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gimme_predict.models import brier, log_loss, multiclass_log_loss

MODEL_NAME = "scorecard"
MODEL_VERSION = "v1"


def _rows(conn: psycopg.Connection[Any], since: datetime) -> list[dict[str, Any]]:
    """Latest published probability per (game, selection) for games that finished in the window."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            WITH latest AS (
                SELECT DISTINCT ON (p.game_id, p.market, p.selection)
                       p.game_id, p.market, p.selection, p.probability, p.created_at
                FROM prediction p
                JOIN game g ON g.id = p.game_id
                WHERE p.market IN ('win_probability', 'match_result')
                  AND p.subject_type = 'game'
                  AND p.created_at < g.kickoff            -- only what was published before kickoff
                ORDER BY p.game_id, p.market, p.selection, p.created_at DESC
            )
            SELECT l.game_id, l.market, l.selection, l.probability, c.slug AS competition,
                   c.sport_id AS sport, g.home_score, g.away_score, g.kickoff
            FROM latest l
            JOIN game g ON g.id = l.game_id
            JOIN competition c ON c.id = g.competition_id
            WHERE g.status = 'final' AND g.kickoff >= %s
            """,
            (since,),
        )
        return [dict(r) for r in cur.fetchall()]


def _market(conn: psycopg.Connection[Any], game_ids: list[int]) -> dict[int, dict[str, float]]:
    """De-vigged closing (else latest) h2h probabilities per game."""
    if not game_ids:
        return {}
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (game_id, selection) game_id, selection, price
            FROM odds
            WHERE game_id = ANY(%s) AND market = 'h2h' AND price > 1
            ORDER BY game_id, selection, is_closing DESC, captured_at DESC
            """,
            (game_ids,),
        )
        raw: dict[int, dict[str, float]] = defaultdict(dict)
        for r in cur.fetchall():
            raw[r["game_id"]][r["selection"]] = 1.0 / float(r["price"])
    out: dict[int, dict[str, float]] = {}
    for gid, sides in raw.items():
        total = sum(sides.values())
        if total > 0:
            out[gid] = {k: v / total for k, v in sides.items()}
    return out


def scorecard(conn: psycopg.Connection[Any], *, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = _rows(conn, since)
    by_game: dict[int, dict[str, Any]] = {}
    for r in rows:
        g = by_game.setdefault(
            r["game_id"],
            {
                "competition": r["competition"],
                "sport": r["sport"],
                "home": r["home_score"],
                "away": r["away_score"],
                "p": {},
            },
        )
        g["p"][r["selection"]] = float(r["probability"])
    market = _market(conn, list(by_game))

    per_comp: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))
    for gid, g in by_game.items():
        comp = per_comp[g["competition"]]
        margin = g["home"] - g["away"]
        if g["sport"] == "soccer":
            if not all(k in g["p"] for k in ("home", "draw", "away")):
                continue
            outcome = 0 if margin > 0 else 1 if margin == 0 else 2
            comp["y3"].append(outcome)
            comp["p3"].append([g["p"]["home"], g["p"]["draw"], g["p"]["away"]])
            mk = market.get(gid)
            if mk and all(k in mk for k in ("home", "draw", "away")):
                comp["m3"].append([mk["home"], mk["draw"], mk["away"]])
                comp["m3_idx"].append(len(comp["y3"]) - 1)
        else:
            if "home" not in g["p"] or margin == 0:
                continue
            comp["y"].append(1.0 if margin > 0 else 0.0)
            comp["p"].append(g["p"]["home"])
            mk = market.get(gid)
            if mk and "home" in mk:
                comp["m"].append(mk["home"])
                comp["m_idx"].append(len(comp["y"]) - 1)

    result: dict[str, Any] = {"window_days": days, "competitions": {}}
    total_games = 0
    for slug, comp in per_comp.items():
        entry: dict[str, Any] = {}
        if comp["y"]:
            y, p = np.array(comp["y"]), np.array(comp["p"])
            entry.update(
                games=len(y),
                log_loss=round(log_loss(y, p), 4),
                brier=round(brier(y, p), 4),
                accuracy=round(float(np.mean((p > 0.5) == (y > 0.5))), 3),
            )
            if len(comp["m"]) >= 5:
                idx = comp["m_idx"]
                m = np.array(comp["m"])
                entry["market_log_loss"] = round(log_loss(y[idx], m), 4)
                entry["log_loss_on_market_games"] = round(log_loss(y[idx], p[idx]), 4)
                entry["market_games"] = len(idx)
        if comp["y3"]:
            y3, p3 = np.array(comp["y3"]), np.array(comp["p3"])
            entry.update(
                games=len(y3),
                log_loss=round(multiclass_log_loss(y3, p3), 4),
                accuracy=round(float(np.mean(p3.argmax(axis=1) == y3)), 3),
            )
            if len(comp["m3"]) >= 5:
                idx = comp["m3_idx"]
                m3 = np.array(comp["m3"])
                entry["market_log_loss"] = round(multiclass_log_loss(y3[idx], m3), 4)
                entry["log_loss_on_market_games"] = round(multiclass_log_loss(y3[idx], p3[idx]), 4)
                entry["market_games"] = len(idx)
        if entry:
            result["competitions"][slug] = entry
            total_games += int(entry["games"])
    result["games"] = total_games
    return result


def run(database_url: str, *, days: int = 30) -> dict[str, Any]:
    with psycopg.connect(database_url) as conn:
        card = scorecard(conn, days=days)
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_run (model_name, model_version, status, finished_at,
                                       snapshot_count, metrics, notes)
                VALUES (%s, %s, 'succeeded', now(), %s, %s, %s)
                """,
                (MODEL_NAME, MODEL_VERSION, card["games"], Jsonb(card), f"last {days} days"),
            )
        conn.commit()
    return card
