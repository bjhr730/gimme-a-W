"""Runtime settings, read once from the environment (and a repo-root .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_USER_AGENT = "gimme-a-W/0.1 (+https://github.com/bjhr730/gimme-a-W)"


def _load_dotenv() -> None:
    """Load the first .env found walking up from the working directory."""
    here = Path.cwd()
    for candidate in (here, *here.parents):
        env = candidate / ".env"
        if env.is_file():
            load_dotenv(env, override=False)
            return


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    cache_dir: Path
    user_agent: str
    cache_ttl_seconds: int
    cfbd_api_key: str | None
    football_data_api_key: str | None
    odds_api_key: str | None


@lru_cache(maxsize=1)
def settings() -> Settings:
    _load_dotenv()
    return Settings(
        database_url=os.getenv("DATABASE_URL") or None,
        cache_dir=Path(os.getenv("COLLECTOR_CACHE_DIR", "./data/raw")).expanduser(),
        user_agent=os.getenv("COLLECTOR_USER_AGENT", DEFAULT_USER_AGENT),
        cache_ttl_seconds=int(os.getenv("COLLECTOR_CACHE_TTL", "600")),
        cfbd_api_key=os.getenv("CFBD_API_KEY") or None,
        football_data_api_key=os.getenv("FOOTBALL_DATA_API_KEY") or None,
        odds_api_key=os.getenv("ODDS_API_KEY") or None,
    )
