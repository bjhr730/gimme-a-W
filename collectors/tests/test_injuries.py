"""ESPN injury feed parsing and the availability verdicts the models read."""

from __future__ import annotations

import json
from pathlib import Path

from gimme_collectors.sources import espn, espn_injuries

FIXTURES = Path(__file__).parent / "fixtures" / "espn"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_classify_maps_wording_to_a_verdict() -> None:
    assert espn_injuries.classify("Out") == ("out", 0.0)
    assert espn_injuries.classify("Injured Reserve")[0] == "out"
    assert espn_injuries.classify("Suspension")[0] == "out"
    assert espn_injuries.classify("Active") == ("available", 1.0)
    verdict, probability = espn_injuries.classify("Questionable")
    assert verdict == "questionable" and 0 < probability < 1
    doubtful = espn_injuries.classify("Doubtful")
    assert doubtful[0] == "doubtful" and doubtful[1] < probability
    # wording nobody has seen before is a doubt, never a clearance
    assert espn_injuries.classify("Limited participant")[0] == "questionable"


def test_parse_league_injuries() -> None:
    lg = espn.league("nfl")
    rows = espn_injuries.parse_league_injuries(load("nfl-injuries.json"), lg)
    assert rows, "fixture should carry injuries"

    # every row is keyed by the same external id the roster collector writes,
    # so an injury lands on the existing player instead of creating a new one
    for row in rows:
        assert row.player.external_id.startswith("s:20~l:28~a:")
        assert row.team.external_id.startswith("s:20~l:28~t:")
        assert row.availability in {"available", "questionable", "doubtful", "out"}
        assert row.play_probability is not None
        assert row.competition.slug == "nfl"

    out_rows = [r for r in rows if r.availability == "out"]
    if out_rows:
        assert all(r.play_probability == 0.0 for r in out_rows)

    detailed = [r for r in rows if r.injury_type]
    if detailed:
        assert detailed[0].status
        # 'Not Specified' is ESPN's way of saying it has nothing, not a body side
        assert all(r.side != "Not Specified" for r in rows)


def test_athlete_ref_recovers_the_id_from_links() -> None:
    lg = espn.league("nfl")
    athlete = {
        "displayName": "Puka Nacua",
        "position": {"abbreviation": "WR"},
        "links": [
            {
                "href": "sportscenter://x-callback-url/showClubhouse"
                "?uid=s:20~l:28~a:4426515&section=stats"
            }
        ],
    }
    ref = espn_injuries.athlete_ref(athlete, lg)
    assert ref is not None
    assert ref.external_id == "s:20~l:28~a:4426515"
    assert ref.position == "WR"

    # falls back to the web player-card link when the app link is missing
    ref = espn_injuries.athlete_ref(
        {
            "displayName": "Puka Nacua",
            "links": [{"href": "https://www.espn.com/nfl/player/_/id/4426515/puka-nacua"}],
        },
        lg,
    )
    assert ref is not None and ref.external_id == "s:20~l:28~a:4426515"

    # nothing to key on: skipped rather than guessed
    assert espn_injuries.athlete_ref({"displayName": "Nobody"}, lg) is None


def test_summary_injuries_use_the_team_on_the_block() -> None:
    lg = espn.league("nfl")
    payload = {
        "injuries": [
            {
                "team": {"id": "14", "uid": "s:20~l:28~t:14", "displayName": "Los Angeles Rams"},
                "injuries": [
                    {
                        "status": "Questionable",
                        "date": "2026-09-06T21:02Z",
                        "details": {
                            "type": "Groin",
                            "location": "Groin",
                            "detail": "Soreness",
                            "side": "Not Specified",
                            "returnDate": "2026-09-10",
                        },
                        "athlete": {
                            "id": "4426515",
                            "uid": "s:20~l:28~a:4426515",
                            "displayName": "Puka Nacua",
                            "position": {"abbreviation": "WR"},
                        },
                    }
                ],
            }
        ]
    }
    rows = espn_injuries.parse_summary_injuries(payload, lg)
    assert len(rows) == 1
    row = rows[0]
    assert row.player.external_id == "s:20~l:28~a:4426515"
    assert row.team.external_id == "s:20~l:28~t:14"
    assert row.availability == "questionable"
    assert row.injury_type == "Groin" and row.detail == "Soreness"
    assert row.side is None  # 'Not Specified' dropped
    assert row.return_date is not None and row.return_date.isoformat() == "2026-09-10"
