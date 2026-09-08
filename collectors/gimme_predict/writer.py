"""Persist model runs, feature snapshots and predictions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from gimme_predict.markets.football import FootballPrediction
from gimme_predict.markets.soccer import SoccerPrediction


class PredictionWriter:
    def __init__(self, database_url: str) -> None:
        self.conn = psycopg.connect(database_url, row_factory=dict_row)
        self.rows = 0

    def begin(self, model_name: str, version: str, sport: str, notes: str | None = None) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_run (model_name, model_version, sport_id, notes)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (model_name, version, sport, notes),
            )
            row = cur.fetchone()
        self.conn.commit()
        assert row is not None
        return int(row["id"])

    def finish(
        self, run_id: int, *, status: str, metrics: dict[str, Any] | None, snapshot_count: int
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                UPDATE model_run SET finished_at = now(), status = %s, metrics = %s,
                    snapshot_count = %s WHERE id = %s
                """,
                (status, Jsonb(metrics or {}), snapshot_count, run_id),
            )
        self.conn.commit()

    def _snapshot(self, cur: Any, game_id: int, features: dict[str, Any], as_of: datetime) -> None:
        cur.execute(
            """
            INSERT INTO feature_snapshot (game_id, subject_type, subject_id, as_of, features)
            VALUES (%s, 'game', %s, %s, %s)
            ON CONFLICT (game_id, subject_type, subject_id, as_of) DO UPDATE
                SET features = EXCLUDED.features
            """,
            (game_id, game_id, as_of, Jsonb(features)),
        )

    def _prediction(
        self,
        cur: Any,
        run_id: int,
        game_id: int,
        market: str,
        selection: str,
        *,
        probability: float | None = None,
        mean: float | None = None,
        line: float | None = None,
        quantiles: dict[str, float] | None = None,
        explanation: dict[str, Any] | None = None,
    ) -> None:
        cur.execute(
            """
            INSERT INTO prediction (model_run_id, game_id, market, subject_type, subject_id,
                                    selection, probability, mean, line, quantiles, explanation)
            VALUES (%s, %s, %s, 'game', %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (model_run_id, game_id, market, subject_type, subject_id, selection)
                DO UPDATE SET probability = EXCLUDED.probability, mean = EXCLUDED.mean,
                    line = EXCLUDED.line, quantiles = EXCLUDED.quantiles,
                    explanation = EXCLUDED.explanation
            """,
            (
                run_id,
                game_id,
                market,
                game_id,
                selection,
                None if probability is None else round(probability, 5),
                None if mean is None else round(mean, 3),
                line,
                Jsonb(quantiles or {}),
                Jsonb(explanation or {}),
            ),
        )
        self.rows += 1

    def write_football(
        self, run_id: int, preds: list[FootballPrediction], features: dict[int, dict[str, Any]]
    ) -> None:
        now = datetime.now(UTC)
        with self.conn.cursor() as cur:
            for p in preds:
                self._snapshot(cur, p.game_id, features.get(p.game_id, {}), now)
                self._prediction(
                    cur,
                    run_id,
                    p.game_id,
                    "win_probability",
                    "home",
                    probability=p.p_home,
                    explanation=p.explanation,
                )
                self._prediction(
                    cur, run_id, p.game_id, "win_probability", "away", probability=1 - p.p_home
                )
                self._prediction(
                    cur,
                    run_id,
                    p.game_id,
                    "spread",
                    "home",
                    mean=p.margin,
                    line=p.market_spread_home,
                    quantiles={
                        "p25": round(p.margin - 0.674 * p.margin_sd, 1),
                        "p75": round(p.margin + 0.674 * p.margin_sd, 1),
                        "sd": round(p.margin_sd, 2),
                    },
                )
                self._prediction(
                    cur,
                    run_id,
                    p.game_id,
                    "total_points",
                    "",
                    mean=p.total,
                    line=p.market_total,
                    quantiles={
                        "p25": round(p.total - 0.674 * p.total_sd, 1),
                        "p75": round(p.total + 0.674 * p.total_sd, 1),
                        "sd": round(p.total_sd, 2),
                    },
                )
        self.conn.commit()

    def write_soccer(self, run_id: int, preds: list[SoccerPrediction]) -> None:
        now = datetime.now(UTC)
        with self.conn.cursor() as cur:
            for p in preds:
                self._snapshot(
                    cur,
                    p.game_id,
                    {"lambda": round(p.lam, 3), "mu": round(p.mu, 3), **p.explanation},
                    now,
                )
                for sel in ("home", "draw", "away"):
                    self._prediction(
                        cur,
                        run_id,
                        p.game_id,
                        "match_result",
                        sel,
                        probability=p.p[sel],
                        explanation=p.explanation if sel == "home" else None,
                    )
                self._prediction(
                    cur,
                    run_id,
                    p.game_id,
                    "total_goals",
                    "over 2.5",
                    probability=p.over_25,
                    mean=p.lam + p.mu,
                    line=2.5,
                )
                self._prediction(
                    cur,
                    run_id,
                    p.game_id,
                    "total_goals",
                    "under 2.5",
                    probability=p.under_25,
                    mean=p.lam + p.mu,
                    line=2.5,
                )
                self._prediction(cur, run_id, p.game_id, "team_goals", "home", mean=p.lam)
                self._prediction(cur, run_id, p.game_id, "team_goals", "away", mean=p.mu)
                self._prediction(cur, run_id, p.game_id, "btts", "yes", probability=p.btts)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
