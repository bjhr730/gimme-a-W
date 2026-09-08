"""Prediction engine command line.

gimme-predict backtest --competition nfl
gimme-predict backtest --competition eng.1
gimme-predict run --competition nfl --competition college-football --days 8
gimme-predict run --sport soccer --days 4
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from datetime import UTC, datetime, timedelta

import psycopg

from gimme_collectors.config import settings
from gimme_predict import data, evaluate, props
from gimme_predict.features import build_features
from gimme_predict.markets import football, football_players, soccer, soccer_props

SOCCER_DEFAULT = [
    "eng.1",
    "eng.2",
    "esp.1",
    "ita.1",
    "ger.1",
    "fra.1",
    "ned.1",
    "por.1",
    "usa.1",
    "mex.1",
    "arg.1",
    "bra.1",
    "uefa.champions",
    "uefa.europa",
    "uefa.europa.conf",
    "conmebol.libertadores",
]
FOOTBALL_DEFAULT = ["nfl", "college-football"]


def _competitions(args: argparse.Namespace) -> list[str]:
    if args.competition:
        return args.competition
    if args.sport == "soccer":
        return SOCCER_DEFAULT
    if args.sport == "american_football":
        return FOOTBALL_DEFAULT
    return FOOTBALL_DEFAULT + SOCCER_DEFAULT


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gimme-predict",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    score = sub.add_parser("score", help="grade published predictions against results")
    score.add_argument("--days", type=int, default=30)
    prune = sub.add_parser(
        "prune", help="drop predictions a newer run has superseded, keeping what the site reads"
    )
    prune.add_argument(
        "--dry-run", action="store_true", help="report how many rows would go, delete nothing"
    )
    for name in ("backtest", "run"):
        p = sub.add_parser(name)
        p.add_argument("--competition", action="append", default=[], help="slug, repeatable")
        p.add_argument("--sport", choices=["soccer", "american_football"], default=None)
        p.add_argument("--json", action="store_true", help="print full metrics as JSON")
        p.add_argument(
            "--markets",
            default="games,props",
            help="games (result/spread/total) and/or props (player and team markets)",
        )
        if name == "run":
            p.add_argument(
                "--days", type=int, default=8, help="predict games kicking off within N days"
            )
            p.add_argument("--dry-run", action="store_true")
    return parser


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg = settings()
    if not cfg.database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    from gimme_predict.writer import PredictionWriter

    writer = PredictionWriter(cfg.database_url)
    markets = {m.strip() for m in args.markets.split(",")}
    with psycopg.connect(cfg.database_url) as conn:
        for slug in _competitions(args):
            games = data.load_games(conn, slug)
            if not games:
                print(f"[{slug}] no games")
                continue
            sport = games[0].sport
            if "props" in markets and sport != "soccer":
                metrics = props.backtest_football(conn, slug, games)
                if metrics:
                    run_id = writer.begin(
                        football_players.MODEL_NAME,
                        football_players.MODEL_VERSION,
                        sport,
                        notes=f"backtest {slug}",
                    )
                    writer.finish(
                        run_id,
                        status="succeeded",
                        metrics={"competition": slug, "props": metrics},
                        snapshot_count=0,
                    )
                    holdout = metrics["holdout_season"]
                    print(f"[{slug}] {football_players.MODEL_NAME} holdout {holdout}")
                    for k, v in metrics.items():
                        if isinstance(v, dict):
                            print(f"  {k}: " + ", ".join(f"{a}={b}" for a, b in v.items()))
                else:
                    print(f"[{slug}] props: not enough player history to back-test")
            if "games" not in markets:
                continue
            if sport == "soccer":
                results = evaluate.backtest_soccer(games)
                name, version = soccer.MODEL_NAME, soccer.MODEL_VERSION
            else:
                results = evaluate.backtest_football(games)
                name, version = football.MODEL_NAME, football.MODEL_VERSION
            summary = evaluate.summarize(results)
            if not results:
                print(f"[{slug}] not enough seasons to back-test ({len(games)} games)")
                continue
            run_id = writer.begin(name, version, sport, notes=f"backtest {slug}")
            writer.finish(
                run_id,
                status="succeeded",
                metrics={"competition": slug, **summary},
                snapshot_count=summary["overall"].get("games", 0),
            )
            o = summary["overall"]
            print(f"[{slug}] {name} {version} · {len(results)} seasons · {o['games']} games")
            for r in results:
                m = r.metrics
                line = f"  {r.season}: n={r.games} model_ll={m['model_log_loss']:.4f}"
                if "market_log_loss" in m:
                    blend = m.get("blend_log_loss_on_market_games", m["blend_log_loss"])
                    line += f" market_ll={m['market_log_loss']:.4f} blend_ll={blend:.4f}"
                if "spread_mae_model" in m:
                    line += f" spread_mae={m['spread_mae_model']:.2f}"
                    if "spread_mae_market" in m:
                        line += f"/{m['spread_mae_market']:.2f}"
                if "total_mae_model" in m:
                    line += f" total_mae={m['total_mae_model']:.2f}"
                    if "total_mae_market" in m:
                        line += f"/{m['total_mae_market']:.2f}"
                print(line)
            if args.json:
                print(json.dumps(summary, indent=1))
    writer.close()
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = settings()
    if not cfg.database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    from gimme_predict.writer import PredictionWriter

    horizon = datetime.now(UTC) + timedelta(days=args.days)
    # Only games that have not kicked off. Predicting one already under way
    # produced rows the scorecard cannot grade, since grading compares what was
    # published in advance against the result, and a number produced at minute 70
    # is not a prediction.
    since = datetime.now(UTC)
    writer = None if args.dry_run else PredictionWriter(cfg.database_url)
    markets = {m.strip() for m in args.markets.split(",")}
    with psycopg.connect(cfg.database_url) as conn:
        for slug in _competitions(args):
            games = data.load_games(conn, slug)
            upcoming = [g for g in games if not g.final and since <= g.kickoff <= horizon]
            if not games or not upcoming:
                print(f"[{slug}] nothing to predict")
                continue
            sport = games[0].sport
            if "props" in markets:
                output = (
                    props.predict_soccer(conn, slug, upcoming, games)
                    if sport == "soccer"
                    else props.predict_football(conn, slug, upcoming, games)
                )
                if output is None:
                    print(f"[{slug}] props: not enough player history")
                else:
                    print(
                        f"[{slug}] props: {len(output.football)} player lines, "
                        f"{len(output.team_counts)} team counts, {len(output.scorers)} scorers"
                        + (
                            f", {output.withheld} withheld as out, {output.flagged} flagged"
                            if output.withheld or output.flagged
                            else ""
                        )
                    )
                    for s in output.scorers[:3]:
                        print(f"    scorer {s.name} {s.probability:.0%}")
                    for p in output.football[:3]:
                        value = p.mean if p.mean is not None else p.probability
                        print(f"    {p.name} {p.market} {value}")
                    if writer is not None:
                        name = (
                            soccer_props.MODEL_NAME
                            if sport == "soccer"
                            else football_players.MODEL_NAME
                        )
                        version = (
                            soccer_props.MODEL_VERSION
                            if sport == "soccer"
                            else football_players.MODEL_VERSION
                        )
                        run_id = writer.begin(name, version, sport, notes=slug)
                        writer.write_props(run_id, output)
                        writer.finish(
                            run_id,
                            status="succeeded",
                            metrics={
                                "competition": slug,
                                "train_rows": output.train_size,
                                # how the injury report changed the slate
                                "players_withheld_unavailable": output.withheld,
                                "players_flagged_doubtful": output.flagged,
                            },
                            snapshot_count=output.count(),
                        )
            if "games" not in markets:
                continue
            if sport == "soccer":
                model = soccer.train(games)
                if model is None:
                    print(f"[{slug}] not enough history to fit a model")
                    continue
                preds = soccer.predict(model, upcoming)
                for p, g in zip(preds, upcoming, strict=True):
                    print(
                        f"[{slug}] {g.home_name} v {g.away_name}: "
                        f"{p.p['home']:.0%}/{p.p['draw']:.0%}/{p.p['away']:.0%} "
                        f"xG {p.lam:.2f}-{p.mu:.2f} O2.5 {p.over_25:.0%}"
                    )
                if writer is not None:
                    run_id = writer.begin(
                        soccer.MODEL_NAME, soccer.MODEL_VERSION, sport, notes=slug
                    )
                    writer.write_soccer(run_id, preds)
                    writer.finish(
                        run_id,
                        status="succeeded",
                        metrics={"competition": slug, "train_games": model.train_size},
                        snapshot_count=len(preds),
                    )
            else:
                features = build_features(games)
                model = football.train(features)
                if model is None:
                    print(f"[{slug}] not enough history to fit a model")
                    continue
                rows = [f for f in features if f.game.id in {g.id for g in upcoming}]
                preds = football.predict(model, rows)
                for p, f in zip(preds, rows, strict=True):
                    g = f.game
                    fav = g.home_name if p.p_home >= 0.5 else g.away_name
                    prob = p.p_home if p.p_home >= 0.5 else 1 - p.p_home
                    print(
                        f"[{slug}] {g.away_name} at {g.home_name}: {fav} {prob:.0%} "
                        f"margin {p.margin:+.1f} total {p.total:.1f}"
                    )
                if writer is not None:
                    run_id = writer.begin(
                        football.MODEL_NAME, football.MODEL_VERSION, sport, notes=slug
                    )
                    writer.write_football(run_id, preds, {f.game.id: f.as_dict() for f in rows})
                    writer.finish(
                        run_id,
                        status="succeeded",
                        metrics={
                            "competition": slug,
                            "train_games": model.train_size,
                            "margin_sd": round(model.margin_sd, 2),
                        },
                        snapshot_count=len(preds),
                    )
    if writer is not None:
        print(f"predictions written: {writer.rows}")
        writer.close()
    return 0


def _use_utf8_output() -> None:
    """Never let an unprintable name kill a run.

    Console encodings outside UTF-8 (cp1252 on Windows) raise on characters like
    the c-acute in a Croatian surname. That exception used to abort the command
    before any prediction was written, so a player's name decided whether a
    league got published.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _use_utf8_output()
    args = _build_parser().parse_args(argv)
    if args.command == "backtest":
        return cmd_backtest(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "prune":
        cfg = settings()
        if not cfg.database_url:
            print("DATABASE_URL is not set.", file=sys.stderr)
            return 2
        from gimme_predict import prune as prune_module

        result = prune_module.run(cfg.database_url, dry_run=args.dry_run)
        print(", ".join(f"{k}={v}" for k, v in result.items()))
        return 0
    if args.command == "score":
        cfg = settings()
        if not cfg.database_url:
            print("DATABASE_URL is not set.", file=sys.stderr)
            return 2
        from gimme_predict import score

        card = score.run(cfg.database_url, days=args.days)
        print(f"scorecard: {card['games']} games in the last {args.days} days")
        for slug, m in sorted(card["competitions"].items()):
            line = f"  {slug}: n={m['games']} log_loss={m['log_loss']} acc={m['accuracy']}"
            if "market_log_loss" in m:
                ours = m["log_loss_on_market_games"]
                line += f" market={m['market_log_loss']} (ours on same games {ours})"
            print(line)
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
