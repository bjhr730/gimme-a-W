"""football-data.org parsing.

Field names and payload shape are copied from live v4 responses, not guessed.
"""

from datetime import UTC, date, datetime

import pytest

from gimme_collectors.sources import football_data as fd

SEASON = {"id": 2502, "startDate": "2026-08-21", "endDate": "2027-05-30", "currentMatchday": 6}
FULHAM = {"id": 63, "name": "Fulham FC", "shortName": "Fulham", "tla": "FUL"}
UNITED = {"id": 66, "name": "Manchester United FC", "shortName": "Man United", "tla": "MUN"}


def match(mid, status, home_goals=None, away_goals=None, **extra):
    node = {
        "id": mid,
        "utcDate": "2026-09-20T15:30:00Z",
        "status": status,
        "matchday": 5,
        "stage": "REGULAR_SEASON",
        "group": None,
        "season": SEASON,
        "homeTeam": FULHAM,
        "awayTeam": UNITED,
        "score": {"winner": "DRAW", "fullTime": {"home": home_goals, "away": away_goals}},
    }
    node.update(extra)
    return node


def test_a_finished_match_carries_its_result():
    games = fd.parse_matches({"matches": [match(560583, "FINISHED", 1, 1)]}, "eng.1")
    g = games[0]
    assert g.status == "final"
    assert (g.home_score, g.away_score) == (1, 1)
    assert g.kickoff == datetime(2026, 9, 20, 15, 30, tzinfo=UTC)
    assert g.week == 5
    assert g.external_id == "football-data:match:560583"
    assert g.competition.slug == "eng.1"
    assert g.competition.name == "English Premier League"


def test_a_fixture_has_no_score_even_if_the_payload_carries_nulls():
    g = fd.parse_matches({"matches": [match(1, "TIMED")]}, "eng.1")[0]
    assert g.status == "scheduled"
    assert g.home_score is None and g.away_score is None
    assert g.status_detail is None


@pytest.mark.parametrize(
    "theirs,ours",
    [
        ("FINISHED", "final"),
        ("AWARDED", "final"),
        ("IN_PLAY", "in_progress"),
        ("PAUSED", "in_progress"),
        ("TIMED", "scheduled"),
        ("SCHEDULED", "scheduled"),
        ("POSTPONED", "postponed"),
        ("SUSPENDED", "suspended"),
        ("CANCELLED", "canceled"),
    ],
)
def test_status_mapping(theirs, ours):
    g = fd.parse_matches({"matches": [match(1, theirs, 2, 0)]}, "eng.1")[0]
    assert g.status == ours


def test_an_unknown_status_is_treated_as_a_fixture_not_a_result():
    g = fd.parse_matches({"matches": [match(1, "SOMETHING_NEW", 3, 3)]}, "eng.1")[0]
    assert g.status == "scheduled"
    assert g.home_score is None  # a score we cannot vouch for is not written


def test_season_label_spans_two_years_or_one():
    assert fd.season_ref(SEASON).label == "2026-27"
    assert fd.season_ref(SEASON).year == 2026
    summer = {"startDate": "2026-03-01", "endDate": "2026-11-30"}
    assert fd.season_ref(summer).label == "2026"
    assert fd.season_ref({}) is None


def test_teams_are_matched_by_name_never_created():
    g = fd.parse_matches({"matches": [match(1, "FINISHED", 0, 0)]}, "eng.1")[0]
    for team in (g.home, g.away):
        assert team.match_by_name is True
        assert team.external_id.startswith("football-data:team:")
    assert g.home.abbreviation == "FUL"
    assert g.away.short_name == "Man United"


def test_a_cup_round_is_recorded_but_a_league_week_is_not():
    league = fd.parse_matches({"matches": [match(1, "FINISHED", 1, 0)]}, "eng.1")[0]
    assert league.round is None  # "REGULAR_SEASON" says nothing worth storing
    cup = fd.parse_matches(
        {"matches": [match(2, "FINISHED", 1, 0, stage="LAST_16", group=None)]},
        "uefa.champions",
    )[0]
    assert cup.round == "LAST_16"


def test_matches_missing_the_parts_that_identify_them_are_skipped():
    broken = [
        match(1, "FINISHED", 1, 0, utcDate=""),
        match(2, "FINISHED", 1, 0, homeTeam={}),
        match(3, "FINISHED", 1, 0, season={}),
        match(4, "FINISHED", 1, 0),  # the good one
    ]
    games = fd.parse_matches({"matches": broken}, "eng.1")
    assert [g.external_id for g in games] == ["football-data:match:4"]


# ----------------------------------------------------------------- tables


STANDINGS = {
    "season": SEASON,
    "standings": [
        {
            "stage": "REGULAR_SEASON",
            "type": "TOTAL",
            "group": None,
            "table": [
                {
                    "position": 1,
                    "team": {
                        "id": 65,
                        "name": "Manchester City FC",
                        "shortName": "Man City",
                        "tla": "MCI",
                    },
                    "playedGames": 5,
                    "won": 5,
                    "draw": 0,
                    "lost": 0,
                    "points": 15,
                    "goalsFor": 13,
                    "goalsAgainst": 5,
                }
            ],
        },
        # the same table again, split home and away -- must not be counted twice
        {
            "stage": "REGULAR_SEASON",
            "type": "HOME",
            "group": None,
            "table": [
                {"position": 1, "team": {"id": 65, "name": "Manchester City FC"}, "playedGames": 3}
            ],
        },
    ],
}


def test_standings_read_the_total_table_only():
    rows = fd.parse_standings(STANDINGS, "eng.1", as_of=date(2026, 10, 7))
    assert len(rows) == 1
    row = rows[0]
    assert row.rank == 1 and row.played == 5 and row.points == 15
    assert (row.wins, row.draws, row.losses) == (5, 0, 0)
    assert (row.points_for, row.points_against) == (13, 5)
    assert row.as_of == date(2026, 10, 7)
    assert row.team.match_by_name is True
    assert row.season.label == "2026-27"


def test_standings_without_a_season_are_dropped():
    assert fd.parse_standings({"standings": STANDINGS["standings"]}, "eng.1") == []


# ------------------------------------------------------------------ urls


def test_urls_use_their_competition_codes():
    assert fd.matches_url("eng.1", 2026).endswith("/competitions/PL/matches?season=2026")
    assert fd.matches_url("uefa.champions").endswith("/competitions/CL/matches")
    assert fd.standings_url("eng.2", 2026).endswith("/competitions/ELC/standings?season=2026")
    assert fd.auth_headers("abc") == {"X-Auth-Token": "abc"}


def test_the_nine_competitions_are_the_ones_on_the_free_tier():
    assert fd.active_slugs() == [
        "eng.1",
        "eng.2",
        "esp.1",
        "fra.1",
        "ger.1",
        "ita.1",
        "ned.1",
        "por.1",
        "uefa.champions",
    ]
    # slugs are unchanged from the ESPN era so stored rows stay attached
    assert fd.competition("eng.1").slug == "eng.1"


def test_empty_payloads_are_harmless():
    assert fd.parse_matches({}, "eng.1") == []
    assert fd.parse_matches({"matches": []}, "eng.1") == []
    assert fd.parse_standings({}, "eng.1") == []
