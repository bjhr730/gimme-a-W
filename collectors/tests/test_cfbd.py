"""CFBD parsing. Field names come from their published OpenAPI schema
(api.collegefootballdata.com/api-docs.json), not from guesswork.
"""

from datetime import UTC, datetime

from gimme_collectors.sources import cfbd

NOW = datetime(2026, 9, 20, 18, 0, tzinfo=UTC)

GAMES = [
    {
        "id": 401752001,
        "season": 2026,
        "week": 3,
        "seasonType": "regular",
        "startDate": "2026-09-12T23:30:00.000Z",
        "completed": True,
        "neutralSite": False,
        "conferenceGame": True,
        "attendance": 106_588,
        "venueId": 3782,
        "venue": "Michigan Stadium",
        "homeId": 130,
        "homeTeam": "Michigan",
        "homePoints": 31,
        "awayId": 194,
        "awayTeam": "Ohio State",
        "awayPoints": 24,
    },
    {  # not yet played
        "id": 401752002,
        "season": 2026,
        "week": 4,
        "startDate": "2026-09-26T16:00:00.000Z",
        "completed": False,
        "neutralSite": True,
        "conferenceGame": False,
        "homeId": 333,
        "homeTeam": "Alabama",
        "awayId": 99,
        "awayTeam": "LSU",
    },
    {  # kicked off an hour ago, not marked complete: the live job owns this one
        "id": 401752003,
        "season": 2026,
        "week": 3,
        "startDate": "2026-09-20T17:00:00.000Z",
        "completed": False,
        "homeId": 2,
        "homeTeam": "Auburn",
        "awayId": 8,
        "awayTeam": "Arkansas",
    },
    {  # unusable
        "id": 401752004,
        "season": 2026,
        "startDate": "",
        "completed": True,
        "homeTeam": "",
        "awayTeam": "Nowhere",
    },
]


def test_only_settled_and_future_games_are_emitted():
    games = cfbd.parse_games(GAMES, now=NOW)
    assert [g.external_id for g in games] == ["cfbd:game:401752001", "cfbd:game:401752002"]


def test_completed_game_carries_its_result():
    done = cfbd.parse_games(GAMES, now=NOW)[0]
    assert done.status == "final"
    assert (done.home_score, done.away_score) == (31, 24)
    assert done.home.name == "Michigan" and done.away.name == "Ohio State"
    assert done.week == 3
    assert done.conference_game is True
    assert done.neutral_site is False
    assert done.attendance == 106_588
    assert done.kickoff == datetime(2026, 9, 12, 23, 30, tzinfo=UTC)
    assert done.competition.slug == "college-football"
    assert done.season.label == "2026" and done.season.year == 2026


def test_future_game_has_no_score():
    upcoming = cfbd.parse_games(GAMES, now=NOW)[1]
    assert upcoming.status == "scheduled"
    assert upcoming.home_score is None and upcoming.away_score is None
    assert upcoming.status_detail is None
    assert upcoming.neutral_site is True
    assert upcoming.conference_game is False


def test_teams_are_matched_by_name_never_created():
    # ESPN already created these teams; a second source must land on the same rows
    for game in cfbd.parse_games(GAMES, now=NOW):
        for team in (game.home, game.away):
            assert team.match_by_name is True
            assert team.external_id.startswith("cfbd:team:")


def test_american_to_decimal():
    assert cfbd.american_to_decimal(-110) == 1.9091
    assert cfbd.american_to_decimal(150) == 2.5
    assert cfbd.american_to_decimal(0) is None
    assert cfbd.american_to_decimal(None) is None
    assert cfbd.american_to_decimal("not a price") is None


LINES = [
    {
        "id": 401752001,
        "season": 2026,
        "week": 3,
        "homeTeam": "Michigan",
        "awayTeam": "Ohio State",
        "lines": [
            {
                "provider": "DraftKings",
                "spread": -3.5,
                "formattedSpread": "Michigan -3.5",
                "overUnder": 54.5,
                "homeMoneyline": -165,
                "awayMoneyline": 140,
            }
        ],
    },
    {"id": 401752002, "lines": []},
]


def test_lines_are_keyed_by_game_and_cover_three_markets():
    odds = cfbd.parse_lines(LINES, captured_at=NOW)
    assert set(odds) == {"cfbd:game:401752001"}  # the empty one is dropped
    markets = {(o.market, o.selection): o for o in odds["cfbd:game:401752001"]}
    assert set(markets) == {
        ("h2h", "home"),
        ("h2h", "away"),
        ("spread", "home"),
        ("spread", "away"),
        ("total", "over"),
        ("total", "under"),
    }
    assert markets[("h2h", "home")].price == 1.6061
    assert markets[("h2h", "away")].price == 2.4
    assert markets[("total", "over")].line == 54.5
    assert all(o.bookmaker == "DraftKings" for o in odds["cfbd:game:401752001"])


def test_spread_flips_sign_for_the_away_side():
    odds = cfbd.parse_lines(LINES, captured_at=NOW)["cfbd:game:401752001"]
    spreads = {o.selection: o.line for o in odds if o.market == "spread"}
    assert spreads == {"home": -3.5, "away": 3.5}


def test_spreads_and_totals_carry_no_price():
    # CFBD publishes the number without the juice; inventing -110 would be a lie
    odds = cfbd.parse_lines(LINES, captured_at=NOW)["cfbd:game:401752001"]
    assert all(o.price is None for o in odds if o.market in {"spread", "total"})


def test_odds_attach_to_the_matching_game():
    odds = cfbd.parse_lines(LINES, captured_at=NOW)
    games = {g.external_id: g for g in cfbd.parse_games(GAMES, now=NOW, odds=odds)}
    assert len(games["cfbd:game:401752001"].odds) == 6
    assert games["cfbd:game:401752002"].odds == []


def test_urls_match_the_documented_endpoints():
    assert cfbd.games_url(2026, 3) == (
        "https://api.collegefootballdata.com/games"
        "?year=2026&week=3&seasonType=regular&classification=fbs"
    )
    assert "week=" not in cfbd.lines_url(2026)
    assert cfbd.auth_headers("abc") == {"Authorization": "Bearer abc"}


def test_empty_payloads_are_harmless():
    assert cfbd.parse_games([]) == []
    assert cfbd.parse_games(None) == []
    assert cfbd.parse_lines([]) == {}
