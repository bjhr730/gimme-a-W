"""nflverse and football-data.co.uk parsers, and team-name matching."""

from __future__ import annotations

from pathlib import Path

from gimme_collectors.pipeline.teamnames import match_team, normalize
from gimme_collectors.sources import fdcouk, nflverse

FIXTURES = Path(__file__).parent / "fixtures"


def _read(rel: str) -> str:
    return (FIXTURES / rel).read_text(encoding="utf-8")


# ------------------------------------------------------------ nflverse


def test_nflverse_games_map_to_espn_ids():
    games = nflverse.parse_games(_read("nflverse/games.csv"), seasons={2025, 2026})
    assert games
    sb = next(g for g in games if g.round == "SB")
    assert sb.external_id == "s:20~l:28~e:401772988"
    assert sb.home.external_id == "s:20~l:28~t:17"  # NE hosted the Super Bowl row
    assert sb.away.external_id == "s:20~l:28~t:26"
    assert sb.home_score == 13 and sb.away_score == 29 and sb.status == "final"
    assert sb.neutral_site is True
    assert sb.weather["temperature_f"] == 67 and sb.weather["roof"] == "outdoors"
    assert sb.venue is not None and "Levi" in sb.venue.name
    # 18:30 Eastern on Feb 8 2026 is 23:30 UTC
    assert sb.kickoff.isoformat() == "2026-02-08T23:30:00+00:00"
    markets = {(o.market, o.selection, o.line) for o in sb.odds}
    assert ("spread", "home", 4.5) in markets  # spread_line -4.5 = away favored by 4.5
    assert ("spread", "away", -4.5) in markets
    assert ("total", "over", 45.5) in markets
    assert all(o.is_closing for o in sb.odds)


def test_nflverse_upcoming_and_old_abbreviations():
    games = nflverse.parse_games(_read("nflverse/games.csv"))
    wk1 = next(g for g in games if g.season.year == 2026)
    assert wk1.status == "scheduled" and wk1.home_score is None
    assert wk1.week == 1 and wk1.round is None
    old = [g for g in games if g.season.year == 2015]
    assert old and all(g.status == "final" for g in old)
    assert nflverse.team_ref("STL").external_id == nflverse.team_ref("LA").external_id
    assert nflverse.team_ref("WAS").abbreviation == "WSH"
    assert nflverse.team_ref("XXX") is None


def test_nflverse_player_stats():
    games_csv = _read("nflverse/games.csv")
    ids = nflverse.game_id_map(games_csv)
    assert ids["2025_22_SEA_NE"] == "s:20~l:28~e:401772988"
    summaries = nflverse.parse_player_stats(_read("nflverse/stats_player_week_2025.csv"), ids)
    sb = next(s for s in summaries if s.game_external_id == "s:20~l:28~e:401772988")
    diggs = next(p for p in sb.players if p.player.full_name == "Stefon Diggs")
    assert diggs.stats["receivingYards"] == 37
    assert "receiving" in diggs.stats["categories"]
    assert diggs.player.external_id.startswith("nflverse:00-")
    assert diggs.team.external_id == "s:20~l:28~t:17"
    assert diggs.player.position == "WR"


# --------------------------------------------------------- football-data


def test_fdcouk_parse_season():
    games = fdcouk.parse_season(_read("fdcouk/E0-2526.csv"), "eng.1", 2025)
    assert len(games) == 4
    g = games[0]
    assert g.competition.slug == "eng.1" and g.season.label == "2025-26"
    assert g.home.name == "Liverpool" and g.home.match_by_name is True
    assert g.home_score == 4 and g.away_score == 2 and g.status == "final"
    # 20:00 UK in August (BST) is 19:00 UTC
    assert g.kickoff.isoformat() == "2025-08-15T19:00:00+00:00"
    assert g.home_stats["shotsOnTarget"] == 9 and g.away_stats["wonCorners"] == 3
    assert g.home_stats["halfTimeGoals"] == 1
    books = {(o.bookmaker, o.market, o.selection, o.is_closing) for o in g.odds}
    assert ("Pinnacle", "h2h", "draw", True) in books
    assert ("Bet365", "total", "over", False) in books
    closing_home = next(o for o in g.odds if o.bookmaker == "Pinnacle" and o.selection == "home")
    assert closing_home.price == 1.24
    future = games[-1]
    assert future.status == "scheduled" and future.home_score is None
    assert future.home_stats == {} and any(o.bookmaker == "Bet365" for o in future.odds)


def test_fdcouk_urls():
    assert fdcouk.csv_url("eng.1", 2025).endswith("/mmz4281/2526/E0.csv")
    assert fdcouk.csv_url("esp.1", 2015).endswith("/mmz4281/1516/SP1.csv")
    assert fdcouk.season_label(2025) == "2025-26"
    assert fdcouk.season_label(2099) == "2099-00"


# ------------------------------------------------------------ names


def test_team_name_matching():
    candidates = {
        "Manchester United": 1,
        "Manchester City": 2,
        "Nottingham Forest": 3,
        "Tottenham Hotspur": 4,
        "Wolverhampton Wanderers": 5,
        "Celta Vigo": 6,
        "Atletico Madrid": 7,
        "Athletic Club": 8,
        "Real Sociedad": 9,
        "Borussia Mönchengladbach": 10,
        "Paris Saint-Germain": 11,
        "AFC Bournemouth": 12,
        "Brighton & Hove Albion": 13,
        "Newcastle United": 14,
        "West Ham United": 15,
    }
    assert match_team("Man United", candidates) == 1
    assert match_team("Man City", candidates) == 2
    assert match_team("Nott'm Forest", candidates) == 3
    assert match_team("Spurs", candidates) == 4
    assert match_team("Wolves", candidates) == 5
    assert match_team("Celta", candidates) == 6
    assert match_team("Ath Madrid", candidates) == 7
    assert match_team("Ath Bilbao", candidates) == 8
    assert match_team("Sociedad", candidates) == 9
    assert match_team("M'gladbach", candidates) == 10
    assert match_team("Paris SG", candidates) == 11
    assert match_team("Bournemouth", candidates) == 12
    assert match_team("Brighton", candidates) == 13
    assert match_team("Newcastle", candidates) == 14
    assert match_team("West Ham", candidates) == 15
    assert match_team("Real Madrid", candidates) is None  # not in this competition
    assert normalize("FC Bayern München") == "bayern munchen"
