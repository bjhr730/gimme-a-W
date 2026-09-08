"""Command line entry point.

gimme-collect leagues
gimme-collect run espn --kind all --league nfl --league eng.1 --date today --days 2
gimme-collect run espn --kind roster --league nfl
gimme-collect run espn --kind scoreboard --league all --date 2026-09-06 --dry-run --json
gimme-collect derive --what form,elo
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import UTC, date, datetime, timedelta

from gimme_collectors.config import settings
from gimme_collectors.models import CollectResult
from gimme_collectors.pipeline.fetch import Fetcher
from gimme_collectors.sources import espn

KINDS = {"scoreboard", "teams", "standings", "summary", "roster"}
DAILY_KINDS = {"scoreboard", "teams", "standings", "summary"}  # `all`; rosters are weekly
DERIVATIONS = {"form", "elo"}


def _parse_date(text: str) -> date:
    if text in {"today", ""}:
        return datetime.now(UTC).date()
    if text == "yesterday":
        return datetime.now(UTC).date() - timedelta(days=1)
    if text == "tomorrow":
        return datetime.now(UTC).date() + timedelta(days=1)
    return date.fromisoformat(text)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gimme-collect",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("leagues", help="list known leagues")

    run = sub.add_parser("run", help="run a collector")
    run.add_argument("source", choices=["espn"], help="source adapter")
    run.add_argument(
        "--kind",
        default="all",
        help="all | scoreboard | teams | standings | summary | roster (comma separated). "
        "'all' is everything except roster.",
    )
    run.add_argument(
        "--league",
        action="append",
        default=[],
        help="league slug, repeatable; 'all' for every known league",
    )
    run.add_argument("--date", default="today", help="YYYY-MM-DD | today | yesterday | tomorrow")
    run.add_argument(
        "--days", type=int, default=1, help="number of days to collect starting at --date"
    )
    run.add_argument(
        "--dry-run", action="store_true", help="fetch and parse but write nothing to the database"
    )
    run.add_argument("--json", action="store_true", help="print parsed records as JSON")
    run.add_argument("--no-cache", action="store_true", help="bypass the on-disk HTTP cache")

    derive = sub.add_parser("derive", help="recompute derived tables from collected games")
    derive.add_argument("--what", default="form,elo", help="form | elo (comma separated)")
    return parser


def _kinds(text: str) -> set[str]:
    if text == "all":
        return set(DAILY_KINDS)
    kinds = {k.strip() for k in text.split(",") if k.strip()}
    unknown = kinds - KINDS
    if unknown:
        raise SystemExit(f"Unknown kind(s): {', '.join(sorted(unknown))}. Use {sorted(KINDS)}.")
    return kinds


def _summary(slug: str, result: CollectResult) -> str:
    counts = {k: v for k, v in result.counts().items() if v}
    parts = ", ".join(f"{k}={v}" for k, v in counts.items())
    return f"[{slug}] {parts}"


def cmd_leagues() -> int:
    for slug, lg in sorted(espn.LEAGUES.items()):
        print(f"{slug:24} {lg.sport:18} {lg.name}")
    print("\nAny other ESPN soccer slug (e.g. tur.1, sco.1) also works.")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = settings()
    kinds = _kinds(args.kind)
    start = _parse_date(args.date)
    days = [start + timedelta(days=i) for i in range(max(args.days, 1))]
    slugs = args.league or ["nfl", "college-football", "eng.1"]
    if "all" in slugs:
        slugs = sorted(espn.LEAGUES)

    writer = None
    run_id = None
    if not args.dry_run:
        if not cfg.database_url:
            print(
                "DATABASE_URL is not set. Use --dry-run to run without a database.",
                file=sys.stderr,
            )
            return 2
        from gimme_collectors.pipeline.db import Writer

        writer = Writer(
            cfg.database_url,
            source_slug=espn.SOURCE_SLUG,
            source_name=espn.SOURCE_NAME,
            base_url=espn.BASE_URL,
            rate_limit_per_min=espn.RATE_LIMIT_PER_MIN,
        )
        run_id = writer.begin_run(
            "espn",
            {"kinds": sorted(kinds), "leagues": slugs, "days": [d.isoformat() for d in days]},
        )

    fetcher = Fetcher(
        espn.SOURCE_SLUG,
        cache_dir=cfg.cache_dir,
        user_agent=cfg.user_agent,
        rate_limit_per_min=espn.RATE_LIMIT_PER_MIN,
        cache_ttl_seconds=0 if args.no_cache else cfg.cache_ttl_seconds,
        sink=writer.save_raw if writer else None,
    )
    adapter = espn.EspnAdapter(fetcher)
    failures: list[str] = []

    try:
        for slug in slugs:
            try:
                lg = espn.league(slug)
                result = adapter.collect(lg, kinds=kinds, days=days)
                if args.json:
                    print(result.model_dump_json(indent=1))
                if writer is not None:
                    written = writer.write(result)
                    print(_summary(slug, result), f"rows_written={written}")
                else:
                    print(_summary(slug, result), "(dry run)")
            except Exception as exc:  # keep going with the other leagues
                failures.append(f"{slug}: {exc}")
                traceback.print_exc()
    finally:
        fetcher.close()
        if writer is not None and run_id is not None:
            status = "failed" if failures else "succeeded"
            writer.finish_run(
                run_id, status=status, error="\n".join(failures) if failures else None
            )
            writer.close()

    if failures:
        print("Failures:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


def cmd_derive(args: argparse.Namespace) -> int:
    cfg = settings()
    if not cfg.database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    what = {w.strip() for w in args.what.split(",") if w.strip()}
    unknown = what - DERIVATIONS
    if unknown:
        raise SystemExit(f"Unknown derivation(s): {', '.join(sorted(unknown))}.")
    from gimme_collectors import derive

    counts = derive.run(cfg.database_url, what)
    print(", ".join(f"{k}={v}" for k, v in counts.items()))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "leagues":
        return cmd_leagues()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "derive":
        return cmd_derive(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
