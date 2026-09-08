"""Command line entry point.

gimme-collect leagues
gimme-collect run espn --kind all --league nfl --league eng.1 --date today --days 2
gimme-collect run espn --kind roster --league nfl
gimme-collect run nflverse --seasons 2015-2026 --what games,players
gimme-collect run fdcouk --league eng.1 --league esp.1 --seasons 2015-2025
gimme-collect derive --what form,elo
gimme-collect live
"""

from __future__ import annotations

import argparse
import contextlib
import sys
import traceback
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

from gimme_collectors.config import settings
from gimme_collectors.models import CollectResult
from gimme_collectors.pipeline.fetch import Fetcher
from gimme_collectors.sources import espn, fdcouk, nflverse

KINDS = {"scoreboard", "teams", "standings", "summary", "roster", "injuries"}
DAILY_KINDS = {"scoreboard", "teams", "standings", "summary", "injuries"}  # `all`; rosters weekly
DERIVATIONS = {"form", "elo"}

SOURCES: dict[str, dict[str, Any]] = {
    "espn": {
        "slug": espn.SOURCE_SLUG,
        "name": espn.SOURCE_NAME,
        "base_url": espn.BASE_URL,
        "rate": espn.RATE_LIMIT_PER_MIN,
    },
    "nflverse": {
        "slug": nflverse.SOURCE_SLUG,
        "name": nflverse.SOURCE_NAME,
        "base_url": nflverse.BASE_URL,
        "rate": nflverse.RATE_LIMIT_PER_MIN,
    },
    "fdcouk": {
        "slug": fdcouk.SOURCE_SLUG,
        "name": fdcouk.SOURCE_NAME,
        "base_url": fdcouk.BASE_URL,
        "rate": fdcouk.RATE_LIMIT_PER_MIN,
    },
}


def _parse_date(text: str) -> date:
    if text in {"today", ""}:
        return datetime.now(UTC).date()
    if text == "yesterday":
        return datetime.now(UTC).date() - timedelta(days=1)
    if text == "tomorrow":
        return datetime.now(UTC).date() + timedelta(days=1)
    return date.fromisoformat(text)


def _parse_seasons(text: str) -> list[int]:
    """'2015-2026' or '2024,2025' -> sorted list of start years. 'current' -> this season."""
    if text in {"current", ""}:
        now = datetime.now(UTC)
        return [now.year if now.month >= 7 else now.year - 1]
    years: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            years.update(range(int(a), int(b) + 1))
        elif part:
            years.add(int(part))
    return sorted(years)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gimme-collect",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("leagues", help="list known leagues")

    run = sub.add_parser("run", help="run a collector")
    run.add_argument("source", choices=sorted(SOURCES), help="source adapter")
    run.add_argument(
        "--kind",
        default="all",
        help="espn: all | scoreboard | teams | standings | summary | injuries | roster "
        "(comma separated). "
        "'all' is everything except roster.",
    )
    run.add_argument(
        "--what",
        default="games,players",
        help="nflverse: games | players (comma separated)",
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
        "--seasons",
        default="current",
        help="nflverse/fdcouk: '2015-2026', '2024,2025' or 'current' (season start year)",
    )
    run.add_argument(
        "--dry-run", action="store_true", help="fetch and parse but write nothing to the database"
    )
    run.add_argument("--json", action="store_true", help="print parsed records as JSON")
    run.add_argument("--no-cache", action="store_true", help="bypass the on-disk HTTP cache")

    derive = sub.add_parser("derive", help="recompute derived tables from collected games")
    derive.add_argument("--what", default="form,elo", help="form | elo (comma separated)")

    sub.add_parser("health", help="exit 1 when the pipeline is stale or a run failed")
    sub.add_parser(
        "live",
        help="refresh scores for competitions with a game on right now, and nothing else",
    )
    return parser


def _kinds(text: str) -> set[str]:
    if text == "all":
        return set(DAILY_KINDS)
    kinds = {k.strip() for k in text.split(",") if k.strip()}
    unknown = kinds - KINDS
    if unknown:
        raise SystemExit(f"Unknown kind(s): {', '.join(sorted(unknown))}. Use {sorted(KINDS)}.")
    return kinds


def _summary(label: str, result: CollectResult) -> str:
    counts = {k: v for k, v in result.counts().items() if v}
    parts = ", ".join(f"{k}={v}" for k, v in counts.items())
    return f"[{label}] {parts}"


def cmd_leagues() -> int:
    for slug, lg in sorted(espn.LEAGUES.items()):
        fd = fdcouk.DIVISIONS.get(slug, "")
        print(f"{slug:24} {lg.sport:18} {lg.name:34} {'history: ' + fd if fd else ''}")
    print("\nAny other ESPN soccer slug (e.g. tur.1, sco.1) also works.")
    return 0


# ---------------------------------------------------------------- units
# Each source yields (label, CollectResult) units so the CLI can write and report
# them one at a time and keep going when one fails.


def _espn_units(args: argparse.Namespace, fetcher: Fetcher) -> Iterator[tuple[str, CollectResult]]:
    kinds = _kinds(args.kind)
    start = _parse_date(args.date)
    days = [start + timedelta(days=i) for i in range(max(args.days, 1))]
    slugs = args.league or ["nfl", "college-football", "eng.1"]
    if "all" in slugs:
        slugs = sorted(espn.LEAGUES)
    adapter = espn.EspnAdapter(fetcher)
    for slug in slugs:
        yield slug, adapter.collect(espn.league(slug), kinds=kinds, days=days)


def _nflverse_units(
    args: argparse.Namespace, fetcher: Fetcher
) -> Iterator[tuple[str, CollectResult]]:
    what = {w.strip() for w in args.what.split(",") if w.strip()}
    seasons = _parse_seasons(args.seasons)
    games_csv, _ = fetcher.get(nflverse.GAMES_URL), None
    text = games_csv.body
    if "games" in what:
        result = CollectResult(fetched_urls=[nflverse.GAMES_URL])
        result.games = nflverse.parse_games(text, seasons)
        yield f"nflverse games {seasons[0]}-{seasons[-1]}", result
    if "players" in what:
        ids = nflverse.game_id_map(text, seasons)
        for season in seasons:
            url = nflverse.player_stats_url(season)
            try:
                fetched = fetcher.get(url)
            except Exception as exc:  # a season not published yet
                print(f"[nflverse players {season}] skipped: {exc}")
                continue
            result = CollectResult(fetched_urls=[url])
            result.summaries = nflverse.parse_player_stats(fetched.body, ids)
            yield f"nflverse players {season}", result


def _fdcouk_units(
    args: argparse.Namespace, fetcher: Fetcher
) -> Iterator[tuple[str, CollectResult]]:
    seasons = _parse_seasons(args.seasons)
    slugs = args.league or sorted(fdcouk.DIVISIONS)
    if "all" in slugs:
        slugs = sorted(fdcouk.DIVISIONS)
    for slug in slugs:
        if slug not in fdcouk.DIVISIONS:
            print(f"[fdcouk] no division code for {slug}; known: {sorted(fdcouk.DIVISIONS)}")
            continue
        for season in seasons:
            url = fdcouk.csv_url(slug, season)
            try:
                fetched = fetcher.get(url)
            except Exception as exc:
                print(f"[fdcouk {slug} {season}] skipped: {exc}")
                continue
            result = CollectResult(fetched_urls=[url])
            result.games = fdcouk.parse_season(fetched.body, slug, season)
            yield f"fdcouk {slug} {fdcouk.season_label(season)}", result


UNITS = {"espn": _espn_units, "nflverse": _nflverse_units, "fdcouk": _fdcouk_units}


def cmd_run(args: argparse.Namespace) -> int:
    cfg = settings()
    source = SOURCES[args.source]

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
            source_slug=source["slug"],
            source_name=source["name"],
            base_url=source["base_url"],
            rate_limit_per_min=source["rate"],
        )
        run_id = writer.begin_run(
            args.source,
            {
                k: v
                for k, v in vars(args).items()
                if k in {"kind", "what", "league", "date", "days", "seasons"}
            },
        )

    fetcher = Fetcher(
        source["slug"],
        cache_dir=cfg.cache_dir,
        user_agent=cfg.user_agent,
        rate_limit_per_min=source["rate"],
        cache_ttl_seconds=0 if args.no_cache else cfg.cache_ttl_seconds,
        sink=writer.save_raw if writer else None,
    )
    failures: list[str] = []

    try:
        for label, result in UNITS[args.source](args, fetcher):
            try:
                if args.json:
                    print(result.model_dump_json(indent=1))
                if writer is not None:
                    written = writer.write(result)
                    print(_summary(label, result), f"rows_written={written}")
                else:
                    print(_summary(label, result), "(dry run)")
            except Exception as exc:  # keep going with the other units
                failures.append(f"{label}: {exc}")
                traceback.print_exc()
    except Exception as exc:
        failures.append(f"{args.source}: {exc}")
        traceback.print_exc()
    finally:
        fetcher.close()
        if writer is not None and run_id is not None:
            if writer.raw_pages_skipped:
                print(
                    f"Raw page cache: stored {writer.raw_pages_stored}, "
                    f"skipped {writer.raw_pages_skipped} (too large or past this run's budget)"
                )
            if writer.unmatched:
                names = ", ".join(f"{n} x{c}" for n, c in sorted(writer.unmatched.items()))
                print(f"Unmatched team names (games skipped): {names}", file=sys.stderr)
            status = "failed" if failures else "succeeded"
            writer.finish_run(
                run_id, status=status, error="\n".join(failures) if failures else None
            )
            writer.close()

    if failures:
        print("Failures:\n  " + "\n  ".join(failures), file=sys.stderr)
        return 1
    return 0


def cmd_live() -> int:
    """Scores only, only where a ball is in play.

    The daily passes leave a match played between them frozen at its pre-kickoff
    state. This is meant to run often, so it asks the database what is actually on
    before touching the network: on a quiet hour it makes no requests at all.
    """
    cfg = settings()
    if not cfg.database_url:
        print("DATABASE_URL is not set.", file=sys.stderr)
        return 2
    from gimme_collectors import live

    slugs = live.active_competitions(cfg.database_url)
    if not slugs:
        print("Nothing in play; no requests made.")
        return 0
    print(f"In play: {', '.join(slugs)}")
    args = argparse.Namespace(
        source="espn",
        kind="scoreboard",
        what="games,players",
        league=slugs,
        date="today",
        days=1,
        seasons="current",
        dry_run=False,
        json=False,
        # scores go stale in minutes, so never serve them from the disk cache
        no_cache=True,
    )
    return cmd_run(args)


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
    if args.command == "leagues":
        return cmd_leagues()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "derive":
        return cmd_derive(args)
    if args.command == "live":
        return cmd_live()
    if args.command == "health":
        cfg = settings()
        if not cfg.database_url:
            print("DATABASE_URL is not set.", file=sys.stderr)
            return 2
        from gimme_collectors import health

        return health.main(cfg.database_url)
    return 2


if __name__ == "__main__":
    sys.exit(main())
