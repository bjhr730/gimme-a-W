"""The official NFL injury report, as published by nflverse.

Column names match injuries_{season}.csv from the nflverse-data `injuries`
release; the rows below are shaped exactly like real ones.
"""

from gimme_collectors.sources import nflverse

HEADER = (
    "season,season_type,game_type,team,week,gsis_id,position,full_name,"
    "first_name,last_name,report_primary_injury,report_secondary_injury,"
    "report_status,practice_primary_injury,practice_secondary_injury,practice_status\n"
)

ROWS = (
    # out, and a later week supersedes the earlier one for the same player
    "2026,REG,REG,WAS,1,00-0037809,TE,Chig Okonkwo,Chig,Okonkwo,Hamstring,,"
    "Questionable,Hamstring,,Limited Participation in Practice\n"
    "2026,REG,REG,WAS,2,00-0037809,TE,Chig Okonkwo,Chig,Okonkwo,Hamstring,,"
    "Out,Hamstring,,Did Not Participate In Practice\n"
    # questionable, three different practice levels
    "2026,REG,REG,ATL,2,00-0031576,LB,Za'Darius Smith,Za'Darius,Smith,Shoulder,,"
    "Questionable,Shoulder,,Full Participation in Practice\n"
    "2026,REG,REG,BUF,2,00-0040192,CB,Jordan Hancock,Jordan,Hancock,Quadricep,,"
    "Questionable,Quadricep,,Limited Participation in Practice\n"
    "2026,REG,REG,KC,2,00-0033873,QB,Patrick Mahomes,Patrick,Mahomes,Ankle,Knee,"
    "Questionable,Ankle,,Did Not Participate In Practice\n"
    # doubtful
    "2026,REG,REG,KC,2,00-0036322,WR,Someone Else,Someone,Else,Knee,,"
    "Doubtful,Knee,,Did Not Participate In Practice\n"
    # on the practice report but carrying no game designation
    "2026,REG,REG,KC,2,00-0099999,RB,No Designation,No,Designation,,,"
    ",Rest,,Did Not Participate In Practice\n"
    # unusable: no player id
    "2026,REG,REG,KC,2,,WR,Ghost Player,Ghost,Player,Knee,,Out,,,\n"
)

CSV = HEADER + ROWS


def _by_name(records):
    return {r.player.full_name: r for r in records}


def test_only_designated_players_are_reported():
    names = set(_by_name(nflverse.parse_injuries(CSV)))
    assert "No Designation" not in names  # practice-only row carries no verdict
    assert "Ghost Player" not in names  # no gsis id
    assert names == {
        "Chig Okonkwo",
        "Za'Darius Smith",
        "Jordan Hancock",
        "Patrick Mahomes",
        "Someone Else",
    }


def test_latest_week_wins():
    okonkwo = _by_name(nflverse.parse_injuries(CSV))["Chig Okonkwo"]
    assert okonkwo.status == "Out"  # week 2, not the week 1 "Questionable"
    assert okonkwo.availability == "out"
    assert okonkwo.play_probability == 0.0


def test_practice_participation_refines_questionable():
    got = _by_name(nflverse.parse_injuries(CSV))
    assert got["Za'Darius Smith"].play_probability == 0.8  # full participation
    assert got["Jordan Hancock"].play_probability == 0.65  # limited
    assert got["Patrick Mahomes"].play_probability == 0.45  # did not practise
    # the designation itself is unchanged by practice
    questionable = ("Za'Darius Smith", "Jordan Hancock", "Patrick Mahomes")
    assert {got[n].availability for n in questionable} == {"questionable"}


def test_out_is_absolute():
    # a player ruled out does not get nudged upward by anything
    assert nflverse.classify_report("Out", "Full Participation in Practice") == ("out", 0.0)


def test_doubtful_is_nudged_but_stays_doubtful():
    verdict, probability = nflverse.classify_report("Doubtful", "Did Not Participate In Practice")
    assert verdict == "doubtful"
    assert probability == 0.05


def test_no_designation_is_not_a_verdict():
    assert nflverse.classify_report("", "Did Not Participate In Practice") is None
    assert nflverse.classify_report("   ", "") is None


def test_probabilities_stay_inside_zero_and_one():
    for report in ("Out", "Doubtful", "Questionable"):
        for practice in list(nflverse.PRACTICE_NUDGE) + ["", "something new"]:
            verdict = nflverse.classify_report(report, practice)
            assert verdict is not None
            assert 0.0 <= verdict[1] <= 1.0


def test_records_land_on_existing_teams_and_players():
    for record in nflverse.parse_injuries(CSV):
        # nflverse abbreviations resolve to the ESPN team ids already in the database
        assert record.team.external_id.startswith("s:20~l:28~t:")
        # player_stats uses the same gsis ids, so injuries join to players already there
        assert record.player.external_id.startswith("nflverse:00-")
        assert record.competition.slug == "nfl"


def test_injury_detail_is_carried_through():
    mahomes = _by_name(nflverse.parse_injuries(CSV))["Patrick Mahomes"]
    assert mahomes.injury_type == "Ankle"
    assert mahomes.detail == "Knee"  # secondary
    assert mahomes.comment == "Did Not Participate In Practice"
    assert mahomes.player.position == "QB"


def test_empty_input_is_harmless():
    assert nflverse.parse_injuries(HEADER) == []


def test_url_points_at_the_published_release():
    assert nflverse.injuries_url(2026) == (
        "https://github.com/nflverse/nflverse-data/releases/download/injuries/injuries_2026.csv"
    )
