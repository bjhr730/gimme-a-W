"""The quota guard must be narrow: a real outage has to stay loud."""

import psycopg
import pytest

from gimme_collectors import quota

NEON = (
    'connection failed: connection to server at "98.89.155.173", port 5432 failed: '
    "ERROR:  Your account or project has exceeded the quota. "
    "Upgrade your plan to increase limits."
)


def test_recognises_the_real_message():
    assert quota.over_quota(psycopg.OperationalError(NEON))


def test_recognises_it_through_a_chain():
    try:
        try:
            raise psycopg.OperationalError(NEON)
        except psycopg.OperationalError as inner:
            raise RuntimeError("collect failed") from inner
    except RuntimeError as outer:
        assert quota.over_quota(outer)


@pytest.mark.parametrize(
    "message",
    [
        "connection failed: Connection refused",
        "connection failed: timeout expired",
        "FATAL: too many connections for role",
        "FATAL: remaining connection slots are reserved",
        # mentions a quota, but the account is not out of allowance
        "ERROR: disk quota exceeded for tablespace",
    ],
)
def test_ordinary_failures_stay_loud(message):
    assert not quota.over_quota(psycopg.OperationalError(message))


def test_other_exception_types_are_not_swallowed():
    # same words, wrong type: only the driver refusing a connection counts
    assert not quota.over_quota(RuntimeError(NEON))
    assert not quota.over_quota(ValueError("exceeded the quota"))


def test_guard_returns_zero_only_for_quota():
    def over():
        raise psycopg.OperationalError(NEON)

    def broken():
        raise psycopg.OperationalError("connection failed: Connection refused")

    assert quota.guard(lambda: 7) == 7
    assert quota.guard(over) == 0
    with pytest.raises(psycopg.OperationalError):
        quota.guard(broken)
