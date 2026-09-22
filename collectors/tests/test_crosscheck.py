"""Comparing a second source's results against what is stored.

The point of this is to notice when ESPN is wrong or silent, so the tests care
most about the cases where the two sides differ -- agreement is the easy half.
"""

from datetime import UTC, datetime, timedelta

from gimme_collectors import crosscheck
from gimme_collectors.models import CompetitionRef, GameRecord, SeasonRef, TeamRef

COMP = CompetitionRef(slug="eng.1", name="English Premier League", sport="soccer")
SEASON = SeasonRef(label="2026-27", year=2026)
DAY = datetime(2026, 9, 20, 14, 0, tzinfo=UTC)

# ids as the database would hold them
ARSENAL, CHELSEA, FULHAM, UNITED = 1, 2, 3, 4
NAMES = {
    "Arsenal": ARSENAL,
    "Chelsea": CHELSEA,
    "Fulham": FULHAM,
    "Manchester United": UNITED,
    "Man United": UNITED,  # the writer stores short names too
}


def record(home_name, away_name, hs, as_, *, when=DAY, status="final"):
    return GameRecord(
        external_id=f"fdcouk:{home_name}-{away_name}-{when:%Y%m%d}",
        competition=COMP,
        season=SEASON,
        kickoff=when,
        home=TeamRef(external_id=f"fd:{home_name}", name=home_name, match_by_name=True),
        away=TeamRef(external_id=f"fd:{away_name}", name=away_name, match_by_name=True),
        home_score=hs,
        away_score=as_,
        status=status,
    )


def stored(home_id, away_id, hs, as_, *, day=None, status="final"):
    return crosscheck.StoredGame(
        game_id=100 + home_id,
        kickoff=(day or DAY.date()),
        home_id=home_id,
        away_id=away_id,
        home_score=hs,
        away_score=as_,
        status=status,
    )


def run(records, rows):
    return crosscheck.compare("eng.1", records, rows, NAMES)


def test_matching_results_agree_quietly():
    report = run([record("Arsenal", "Chelsea", 2, 1)], [stored(ARSENAL, CHELSEA, 2, 1)])
    assert report.checked == 1
    assert report.agreed == 1
    assert report.disagreements == 0


def test_a_different_scoreline_is_reported():
    report = run([record("Arsenal", "Chelsea", 2, 1)], [stored(ARSENAL, CHELSEA, 3, 1)])
    assert report.agreed == 0
    finding = report.of_kind("score")[0]
    assert finding.ours == "3-1"
    assert finding.theirs == "2-1"
    assert "Arsenal" in finding.line() and "score" in finding.line()


def test_a_game_we_still_call_scheduled_is_reported():
    """The failure mode that matters: they have a result, we never collected it."""
    report = run(
        [record("Arsenal", "Chelsea", 2, 1)],
        [stored(ARSENAL, CHELSEA, None, None, status="scheduled")],
    )
    finding = report.of_kind("not_final")[0]
    assert finding.theirs == "2-1"
    assert "scheduled" in finding.ours


def test_a_game_we_never_stored_at_all_is_reported():
    report = run([record("Arsenal", "Chelsea", 2, 1)], [])
    finding = report.of_kind("unknown_game")[0]
    assert finding.ours == "not stored"
    assert finding.theirs == "2-1"


def test_a_team_name_we_cannot_place_is_reported_not_guessed():
    report = run([record("Some New Club", "Chelsea", 1, 0)], [])
    assert report.of_kind("unmatched_team")
    assert not report.of_kind("unknown_game")  # not silently counted as a missing game


def test_short_names_resolve():
    report = run([record("Man United", "Fulham", 1, 1)], [stored(UNITED, FULHAM, 1, 1)])
    assert report.agreed == 1


def test_a_day_of_slack_is_allowed_but_not_three():
    """football-data.co.uk publishes a local date with no timezone, so a late
    kickoff can land either side of midnight -- but a different week is a
    different game."""
    near = run(
        [record("Arsenal", "Chelsea", 2, 1)],
        [stored(ARSENAL, CHELSEA, 2, 1, day=DAY.date() + timedelta(days=1))],
    )
    assert near.agreed == 1

    far = run(
        [record("Arsenal", "Chelsea", 2, 1)],
        [stored(ARSENAL, CHELSEA, 2, 1, day=DAY.date() + timedelta(days=3))],
    )
    assert far.of_kind("unknown_game")


def test_reversed_fixtures_are_not_confused_with_each_other():
    """Arsenal at home to Chelsea is not Chelsea at home to Arsenal."""
    report = run([record("Arsenal", "Chelsea", 2, 1)], [stored(CHELSEA, ARSENAL, 2, 1)])
    assert report.of_kind("unknown_game")
    assert report.agreed == 0


def test_unplayed_games_in_the_source_are_skipped():
    report = run(
        [record("Arsenal", "Chelsea", None, None, status="scheduled")],
        [stored(ARSENAL, CHELSEA, None, None, status="scheduled")],
    )
    assert report.checked == 0
    assert report.disagreements == 0


def test_the_window_follows_the_source_not_the_clock():
    """Checking "the last 14 days" against a source that stops updating would
    compare an empty window and look clean. The window ends at the source's own
    latest result instead."""
    records = [
        record("Arsenal", "Chelsea", 1, 0, when=DAY - timedelta(days=30)),
        record("Fulham", "Arsenal", 0, 2, when=DAY),
    ]
    span = crosscheck.window(records, 14)
    assert span == (DAY.date() - timedelta(days=14), DAY.date())


def test_the_window_of_nothing_is_nothing():
    assert crosscheck.window([], 14) is None
    assert crosscheck.window([record("Arsenal", "Chelsea", None, None, status="scheduled")], 14) is None


def test_several_findings_are_all_collected():
    report = run(
        [
            record("Arsenal", "Chelsea", 2, 1),  # agrees
            record("Fulham", "Arsenal", 0, 3),  # differs
            record("Chelsea", "Fulham", 1, 1),  # not stored
        ],
        [stored(ARSENAL, CHELSEA, 2, 1), stored(FULHAM, ARSENAL, 1, 3)],
    )
    assert report.checked == 3
    assert report.agreed == 1
    assert {f.kind for f in report.findings} == {"score", "unknown_game"}
