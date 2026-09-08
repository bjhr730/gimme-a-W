# collectors

Python package with two parts:

- `gimme_collectors`: source adapters (ESPN today; Sports-Reference, CFBD, nflverse and
  football-data.co.uk next), a throttled fetcher with an on-disk cache, and the Postgres writer.
- `gimme_predict`: the prediction engine (phase 4 onward).

## Run

```bash
uv sync
uv run gimme-collect leagues
uv run gimme-collect run espn --kind all --league nfl --league eng.1 --date today --dry-run

# injury and availability reports: one request per league
# (ESPN has a full NFL feed, a thin college one, and nothing for soccer)
uv run gimme-collect run espn --kind injuries --league nfl --league college-football

# backfill lineups for a whole season: month-sized range requests, played games only
uv run gimme-collect run espn --kind summary --league eng.1 --date 2026-01-01 --days 255
uv run gimme-collect run espn --kind scoreboard --league college-football --date 2026-09-06 --json --dry-run
```

Without `--dry-run` the command needs `DATABASE_URL` (see `.env.example` at the repo root)
and writes games, teams, standings, odds, raw pages and a `collector_run` row.

## Test

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

Fixtures under `tests/fixtures/espn` are trimmed real responses. When ESPN changes a shape,
refresh the fixture and fix the parser in the same commit.
