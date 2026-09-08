"""Pin ESPN summary and roster shapes."""

from __future__ import annotations

from datetime import UTC, datetime

from gimme_collectors.sources import espn, espn_summary


def test_nfl_roster(fixture):
    rows = espn_summary.parse_roster(fixture("espn/nfl-roster.json"), espn.league("nfl"))
    assert len(rows) == 15  # 5 unit groups x 3 athletes in the trimmed fixture
    p = rows[0].player
    assert p.external_id.startswith("s:20~l:28~a:")
    assert p.full_name == "Elijah Arroyo" and p.position == "TE" and p.jersey == "18"
    assert p.height_cm == 196 and p.weight_kg == 115
    assert p.birth_date is not None and p.birth_date.year == 2003
    assert p.headshot_url and p.headshot_url.startswith("https://")
    assert rows[0].team.external_id == "s:20~l:28~t:26"
    assert rows[0].season is not None and rows[0].season.label == "2026"


def test_soccer_roster(fixture):
    rows = espn_summary.parse_roster(fixture("espn/eng1-roster.json"), espn.league("eng.1"))
    assert len(rows) == 5
    p = rows[0].player
    assert p.external_id == "s:600~a:169532"
    assert p.full_name == "Kepa Arrizabalaga" and p.position == "G"
    assert p.nationality == "Spain"


def test_cfb_summary_players(fixture):
    s = espn_summary.parse_summary(
        fixture("espn/cfb-summary.json"), espn.league("college-football")
    )
    assert s is not None
    assert s.game_external_id.startswith("s:20~l:23~e:")
    assert s.status == "final"
    assert s.home_score is not None and s.away_score is not None
    assert s.home_stats["totalYards"] and s.away_stats["totalYards"] == 336
    qb = next(p for p in s.players if p.player.full_name == "Luke Weaver")
    assert qb.stats["passingYards"] == 234
    assert qb.stats["completions"] == 21 and qb.stats["passingAttempts"] == 32
    assert qb.stats["passingTouchdowns"] == 2
    assert qb.stats["rushingYards"] == 42  # merged across categories
    assert "passing" in qb.stats["categories"] and "rushing" in qb.stats["categories"]
    assert qb.team.abbreviation == "SJSU"


def test_soccer_summary_lineups(fixture):
    s = espn_summary.parse_summary(fixture("espn/eng1-summary.json"), espn.league("eng.1"))
    assert s is not None
    assert s.status == "final"
    assert s.home_stats["shotsOnTarget"] == 6 and s.home_stats["wonCorners"] == 4
    assert s.home_stats["accuratePasses"] == 362
    scorers = [p.player.full_name for p in s.players if p.stats.get("totalGoals")]
    assert "Tyrique George" in scorers and "Bryan Mbeumo" in scorers
    keeper = next(p for p in s.players if p.player.full_name == "Jordan Pickford")
    assert keeper.stats["starter"] is True and keeper.stats["saves"] == 1
    assert keeper.player.position == "G"
    assert len(s.lineups) == len(s.players)


def test_nfl_pregame_predictor(fixture):
    at = datetime(2026, 9, 7, tzinfo=UTC)
    s = espn_summary.parse_summary(fixture("espn/nfl-summary-pregame.json"), espn.league("nfl"), at)
    assert s is not None
    assert s.status == "scheduled" and s.home_score is None
    assert s.players == []
    assert len(s.picks) == 1
    pick = s.picks[0]
    assert pick.author == "ESPN FPI"
    assert pick.pick_team is not None and pick.pick_team.external_id == s.home.external_id
    assert pick.win_probability == 0.611
    assert pick.published_at == at


def test_id_helpers():
    assert espn_summary.event_id_from_external("s:20~l:23~e:401864494") == "401864494"
    assert espn_summary.event_id_from_external("football:401864494") == "401864494"
    assert espn_summary.team_id_from_external("s:20~l:28~t:26") == "26"
    assert espn_summary.team_id_from_external("s:600~t:359") == "359"
    assert espn_summary.team_id_from_external("soccer:359") == "359"
    assert espn_summary.summary_url(espn.league("nfl"), "1").endswith("/nfl/summary?event=1")
    assert espn_summary.roster_url(espn.league("eng.1"), "359").endswith(
        "/soccer/eng.1/teams/359/roster"
    )
