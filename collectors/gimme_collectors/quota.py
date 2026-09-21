"""Recognising a database that has run out of allowance.

Neon's free tier meters storage, compute and network transfer. When one of them
runs out the endpoint stops accepting connections altogether, and every job that
touches it dies the same way:

    OperationalError: connection failed: ERROR: Your account or project has
    exceeded the quota. Upgrade your plan to increase limits.

That is not a bug to be alerted about every six hours. It is a known state with a
known end -- the meter rolls over at the start of the billing period and
everything resumes on its own. So the jobs treat it as "nothing to do today":
they say so loudly in the log, raise a GitHub Actions warning so the run carries a
visible mark, and exit 0 so no failure email goes out.

Anything else still fails the run, which is the point: this must stay narrow
enough that a real outage is never mistaken for a quiet one.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable

# Both halves must appear. "quota" alone is too loose -- a statement timeout or a
# connection limit can mention quotas without the account being out of allowance.
_MARKERS = (("exceeded the quota",), ("quota", "upgrade your plan"))


def over_quota(exc: BaseException) -> bool:
    """True when this exception is Neon refusing service until the meter resets."""
    import psycopg

    for err in _chain(exc):
        if not isinstance(err, psycopg.OperationalError):
            continue
        text = str(err).lower()
        if any(all(part in text for part in group) for group in _MARKERS):
            return True
    return False


def _chain(exc: BaseException) -> list[BaseException]:
    seen: list[BaseException] = []
    cur: BaseException | None = exc
    while cur is not None and cur not in seen:
        seen.append(cur)
        cur = cur.__cause__ or cur.__context__
    return seen


def report(exc: BaseException) -> None:
    """Say what happened where both a human and the Actions UI will see it."""
    message = (
        "Database is out of allowance, so there is nothing this run can do. "
        "It resumes by itself when the quota resets; no data is lost in the meantime."
    )
    print(f"\n*** {message}\n*** {str(exc).strip().splitlines()[0]}\n", file=sys.stderr)
    if os.getenv("GITHUB_ACTIONS") == "true":
        # A warning annotation marks the run in the UI without failing it, so the
        # state is visible on the Actions page but sends no failure email.
        print(f"::warning title=Database over quota::{message}")


def guard(run: Callable[[], int]) -> int:
    """Run a command; turn an out-of-allowance database into a quiet exit 0."""
    try:
        return run()
    except Exception as exc:
        if over_quota(exc):
            report(exc)
            return 0
        raise
