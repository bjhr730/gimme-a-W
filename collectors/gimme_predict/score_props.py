"""Grade published player props against what the players actually did.

The match models have been graded against the closing line since the scorecard
existed. The player props never have -- the site has been publishing several
hundred of them per competition per run with no measurement of whether any are
better than a guess. This closes that.

There is no market price to compare a prop against without a paid feed, so the
benchmark is the base rate: "every player has the competition's average chance of
scoring". A model that cannot beat that adds nothing, however plausible its
numbers look. Brier skill is the headline -- above zero beats the base rate,
zero or below does not.

Two things keep the measurement honest:

  * Only predictions published *before* kickoff are graded. A prop written by a
    run that started after the whistle is not a prediction.
  * Only games whose lineups were actually collected are graded. A player with no
    box-score row did not play and scored nothing, which is a real miss the model
    should own -- but if the lineups were never collected, every player in the
    game looks that way and the scorecard would be measuring a gap in
    collection rather than a flaw in the model.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row

from gimme_predict.models import brier, log_loss

# Binary player props: a probability, and an event that either happened or did not.
# The yardage markets are distributions rather than events and are not graded here.
MARKETS = ("anytime_scorer", "anytime_assist", "player_shots_on_target", "anytime_td")

# Below this many box-score rows, treat the game's lineups as not collected.
# A soccer game carries two full squads; a blank game would otherwise read as
# every prop missing.
MIN_PLAYER_ROWS = 12

# Calibration buckets: predicted probability bands, wide enough to hold a
# meaningful count at the volumes involved.
BANDS = ((0.0, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 0.35), (0.35, 0.6), (0.6, 1.01))

SQL = """
WITH covered AS (
    SELECT game_id FROM player_game_stat
    GROUP BY game_id HAVING count(*) >= %s
),
latest AS (
    SELECT DISTINCT ON (p.game_id, p.market, p.subject_id, p.selection)
           p.game_id, p.market, p.subject_id, p.selection,
           p.probability, p.line
    FROM prediction p
    JOIN model_run mr ON mr.id = p.model_run_id
    JOIN game g ON g.id = p.game_id
    JOIN covered ON covered.game_id = p.game_id
    WHERE p.subject_type = 'player'
      AND p.probability IS NOT NULL
      AND p.market = ANY(%s)
      AND g.status = 'final'
      AND g.kickoff >= %s
      AND mr.started_at < g.kickoff
    ORDER BY p.game_id, p.market, p.subject_id, p.selection, p.created_at DESC
)
SELECT l.market, l.selection, l.probability, l.line,
       c.slug AS competition,
       COALESCE((s.stats->>'totalGoals')::numeric, 0) AS goals,
       COALESCE((s.stats->>'goalAssists')::numeric, 0) AS assists,
       COALESCE((s.stats->>'shotsOnTarget')::numeric, 0) AS sot,
       COALESCE((s.stats->>'rushingTouchdowns')::numeric, 0)
         + COALESCE((s.stats->>'receivingTouchdowns')::numeric, 0) AS tds,
       (s.player_id IS NOT NULL) AS played
FROM latest l
JOIN game g ON g.id = l.game_id
JOIN competition c ON c.id = g.competition_id
LEFT JOIN player_game_stat s
       ON s.game_id = l.game_id AND s.player_id = l.subject_id
"""


def _happened(row: dict[str, Any]) -> bool | None:
    """Did the thing the prop predicted actually occur? None if ungradable."""
    market = row["market"]
    if market == "anytime_scorer":
        return float(row["goals"]) > 0
    if market == "anytime_assist":
        return float(row["assists"]) > 0
    if market == "anytime_td":
        return float(row["tds"]) > 0
    if market == "player_shots_on_target":
        line = row["line"]
        if line is None:
            return None  # the mean-only row carries no probability to grade
        return float(row["sot"]) > float(line)
    return None


def _label(row: dict[str, Any]) -> str:
    """Market name, with the line where one market covers several."""
    if row["market"] == "player_shots_on_target" and row["line"] is not None:
        return f"player_shots_on_target over {float(row['line']):g}"
    return str(row["market"])


def _metrics(y: np.ndarray, p: np.ndarray) -> dict[str, Any]:
    base_rate = float(y.mean())
    # the benchmark: predict the observed base rate for everyone
    baseline = np.full_like(p, base_rate)
    model_brier = brier(y, p)
    base_brier = brier(y, baseline)
    skill = 1.0 - (model_brier / base_brier) if base_brier > 0 else 0.0
    return {
        "n": int(len(y)),
        "base_rate": round(base_rate, 4),
        "mean_predicted": round(float(p.mean()), 4),
        "brier": round(model_brier, 5),
        "brier_base_rate": round(base_brier, 5),
        "brier_skill": round(skill, 4),
        "log_loss": round(log_loss(y, p), 5),
        "log_loss_base_rate": round(log_loss(y, baseline), 5),
        "beats_base_rate": bool(skill > 0),
    }


def _calibration(y: np.ndarray, p: np.ndarray) -> list[dict[str, Any]]:
    """Predicted vs observed, by band. A calibrated model tracks the diagonal."""
    out: list[dict[str, Any]] = []
    for low, high in BANDS:
        idx = np.where((p >= low) & (p < high))[0]
        if len(idx) == 0:
            continue
        out.append(
            {
                "band": f"{low:g}-{min(high, 1.0):g}",
                "n": int(len(idx)),
                "predicted": round(float(p[idx].mean()), 4),
                "observed": round(float(y[idx].mean()), 4),
            }
        )
    return out


def scorecard(conn: psycopg.Connection[Any], since: datetime) -> dict[str, Any]:
    """Per-market and per-competition grades for the window."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(SQL, (MIN_PLAYER_ROWS, list(MARKETS), since))
        rows = cur.fetchall()

    by_market: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    by_comp: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    did_not_play = 0
    for row in rows:
        outcome = _happened(row)
        if outcome is None:
            continue
        probability = float(row["probability"])
        label = _label(row)
        by_market[label]["y"].append(float(outcome))
        by_market[label]["p"].append(probability)
        by_comp[row["competition"]]["y"].append(float(outcome))
        by_comp[row["competition"]]["p"].append(probability)
        if not row["played"]:
            did_not_play += 1

    def summarise(groups: dict[str, dict[str, list[float]]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, vals in sorted(groups.items()):
            y = np.array(vals["y"], dtype=float)
            p = np.array(vals["p"], dtype=float)
            if len(y) == 0 or len(set(y.tolist())) < 2:
                # every outcome the same way: skill is undefined, so say so
                out[key] = {"n": int(len(y)), "note": "no variation in outcomes yet"}
                continue
            entry = _metrics(y, p)
            entry["calibration"] = _calibration(y, p)
            out[key] = entry
        return out

    graded = sum(len(v["y"]) for v in by_market.values())
    return {
        "graded": graded,
        "predicted_but_did_not_play": did_not_play,
        "markets": summarise(by_market),
        "competitions": summarise(by_comp),
    }
