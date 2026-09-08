"""Pin ESPN response shapes. If ESPN changes its API these fail first."""

from __future__ import annotations

from datetime import UTC, date, datetime

from gimme_collectors.sources import espn

assert hasattr(espn, "SeasonRef")


def test_season_labels(fixture):
    eng = espn.parse_scoreboard(fixture("espn/eng1-scoreboard.json"), espn.league("eng.1"))
    nfl = espn.parse_scoreboard(fixture("espn/nfl-scoreboard.json"), espn.league("nfl"))
    assert eng[0].season.label == "2026-27"
    assert eng[0].season.year == 2026
    assert nfl[0].season.label == "2026"


def test_nfl_scoreboard_games(fixture):
    games = espn.parse_scoreboard(fixture("espn/nfl-scoreboard.json"), espn.league("nfl"))
    assert len(games) == 4
    g = games[0]
    assert g.competition.slug == "nfl"
    assert g.competition.sport == "american_football"
    assert g.home.external_id and g.away.external_id
    assert g.home.name != g.away.name
    assert g.kickoff.tzinfo is not None
    assert g.week == 1
    assert g.venue is not None and g.venue.name
    # scheduled games carry no score even though ESPN sends "0"
    scheduled = [x for x in games if x.status == "scheduled"]
    assert all(x.home_score is None and x.away_score is None for x in scheduled)


def test_nfl_odds_parsed(fixture):
    games = espn.parse_scoreboard(fixture("espn/nfl-scoreboard.json"), espn.league("nfl"))
    with_odds = [g for g in games if g.odds]
    assert with_odds, "expected at least one game with a DraftKings line"
    markets = {(o.market, o.selection) for o in with_odds[0].odds}
    assert {("h2h", "home"), ("h2h", "away"), ("spread", "home"), ("total", "over")} <= markets
    spread_home = next(
        o for o in with_odds[0].odds if o.market == "spread" and o.selection == "home"
    )
    assert spread_home.line is not None
    assert spread_home.price is not None and spread_home.price > 1


def test_american_to_decimal():
    assert espn.american_to_decimal("+142") == 2.42
    assert espn.american_to_decimal("-170") == 1.5882
    assert espn.american_to_decimal("EVEN") == 2.0
    assert espn.american_to_decimal(None) is None


def test_soccer_scoreboard_stats_and_status(fixture):
    games = espn.parse_scoreboard(fixture("espn/eng1-scoreboard.json"), espn.league("eng.1"))
    assert games
    g = games[0]
    assert g.status == "final"
    assert g.home_score is not None and g.away_score is not None
    for stats in (g.home_stats, g.away_stats):
        assert isinstance(stats["shotsOnTarget"], int | float)
        assert isinstance(stats["wonCorners"], int | float)
        assert isinstance(stats["possessionPct"], int | float)
        assert "form" in stats


def test_cfb_scoreboard(fixture):
    games = espn.parse_scoreboard(
        fixture("espn/cfb-scoreboard.json"), espn.league("college-football")
    )
    assert len(games) == 4
    assert all(g.competition.slug == "college-football" for g in games)
    assert any(g.conference_game is not None for g in games)


def test_game_status_mapping():
    def status(name: str, state: str, period: int | None = None) -> str:
        node: dict = {"type": {"name": name, "state": state}}
        if period is not None:
            node["period"] = period
        return espn.game_status(node)

    assert status("STATUS_FULL_TIME", "post") == "final"
    assert status("STATUS_HALFTIME", "in") == "in_progress"
    assert status("STATUS_POSTPONED", "post") == "postponed"
    assert status("STATUS_DELAYED", "in", 0) == "scheduled"
    assert status("STATUS_DELAYED", "in", 2) == "in_progress"
    assert espn.game_status({}) == "scheduled"


def test_external_ids_are_sport_scoped(fixture):
    """ESPN reuses numeric team ids across sports; the uid must be the key."""
    nfl = espn.parse_teams(fixture("espn/nfl-teams.json"), espn.league("nfl"))
    eng = espn.parse_teams(fixture("espn/eng1-teams.json"), espn.league("eng.1"))
    assert nfl[0].team.external_id == "s:20~l:28~t:22"
    assert eng[0].team.external_id == "s:600~t:349"
    games = espn.parse_scoreboard(fixture("espn/nfl-scoreboard.json"), espn.league("nfl"))
    assert games[0].external_id.startswith("s:20~l:28~e:")
    assert games[0].venue is not None and games[0].venue.external_id.startswith("football:")
    # payloads without a uid (rosters) must rebuild the same uid shape
    assert espn.team_external_id({"id": "7"}, espn.league("eng.1")) == "s:600~t:7"
    assert espn.team_external_id({"id": "26"}, espn.league("nfl")) == "s:20~l:28~t:26"
    assert espn.team_external_id({"id": "52"}, espn.league("college-football")) == "s:20~l:23~t:52"


def test_teams(fixture):
    nfl = espn.parse_teams(fixture("espn/nfl-teams.json"), espn.league("nfl"))
    eng = espn.parse_teams(fixture("espn/eng1-teams.json"), espn.league("eng.1"))
    assert len(nfl) == 3 and len(eng) == 3
    assert nfl[0].team.name == "Arizona Cardinals"
    assert nfl[0].team.logo_url and nfl[0].team.logo_url.startswith("https://")
    assert nfl[0].season.label == "2026"
    assert eng[0].team.abbreviation == "BOU"


def test_standings(fixture):
    as_of = date(2026, 9, 7)
    nfl = espn.parse_standings(fixture("espn/nfl-standings.json"), espn.league("nfl"), as_of)
    eng = espn.parse_standings(fixture("espn/eng1-standings.json"), espn.league("eng.1"), as_of)
    cfb = espn.parse_standings(
        fixture("espn/cfb-standings.json"), espn.league("college-football"), as_of
    )
    assert {s.group_name for s in nfl} == {
        "American Football Conference",
        "National Football Conference",
    }
    assert eng and all(s.group_name == "" for s in eng)
    assert eng[0].season.label == "2026-27"
    assert eng[0].rank == 1 and eng[0].points == 9 and eng[0].played == 3
    assert eng[0].points_for == 7 and eng[0].points_against == 2
    assert cfb and all(s.group_name for s in cfb)
    assert cfb[0].points_for == 69 and cfb[0].wins == 2
    # CFB repeats stat names per split; the first (overall) wins
    assert cfb[0].stats["pointsFor"] == 69


def test_event_season_in_range_responses():
    league = espn.SeasonRef(label="2026-27", year=2026)
    old = espn.event_season(
        {"season": {"year": 2019, "slug": "2019-20-english-premier-league"}}, league
    )
    assert old.label == "2019-20" and old.year == 2019
    mls_league = espn.SeasonRef(label="2026", year=2026)
    mls = espn.event_season({"season": {"year": 2024, "slug": "regular-season"}}, mls_league)
    assert mls.label == "2024"
    # some leagues spell the slug with two full years
    liga = espn.event_season({"season": {"year": 2020, "slug": "2020-2021-spanish-laliga"}}, league)
    assert liga.label == "2020-21"
    # a slug without years in a split-year league still gets a split-year label
    serie = espn.event_season({"season": {"year": 2022, "slug": "italian-serie-a"}}, league)
    assert serie.label == "2022-23"
    calendar = espn.SeasonRef(label="2026", year=2026)
    assert espn.event_season({"season": {"year": 2024, "slug": "x"}}, calendar).label == "2024"
    assert espn.event_season({"season": {"year": 2026}}, league) is league
    assert espn.scoreboard_url(espn.league("eng.1"), date(2019, 8, 1), date(2019, 8, 31)).endswith(
        "/soccer/eng.1/scoreboard?dates=20190801-20190831&limit=1000"
    )
    days = [date(2019, 8, 30), date(2019, 8, 31), date(2019, 9, 1), date(2019, 9, 2)]
    assert espn.month_chunks(days) == [
        (date(2019, 8, 30), date(2019, 8, 31)),
        (date(2019, 9, 1), date(2019, 9, 2)),
    ]


def test_urls():
    assert espn.scoreboard_url(espn.league("nfl"), date(2026, 9, 7)).endswith(
        "/football/nfl/scoreboard?dates=20260907"
    )
    cfb = espn.scoreboard_url(espn.league("college-football"), date(2026, 9, 7))
    assert "groups=80" in cfb and "dates=20260907" in cfb
    assert espn.standings_url(espn.league("eng.1")).endswith("/soccer/eng.1/standings")
    assert espn.league("tur.1").sport == "soccer"


def test_parse_scoreboard_captured_at(fixture):
    at = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    games = espn.parse_scoreboard(fixture("espn/nfl-scoreboard.json"), espn.league("nfl"), at)
    assert all(o.captured_at == at for g in games for o in g.odds)
