"""A source that matches teams by name must not then rename them.

football-data.org publishes formal registered names -- "Arsenal FC", "Sporting
Clube de Braga". Those are how it identifies a club, not how this app should
display one, and writing them left the Premier League list reading half formal
and half not. A source that finds a team by matching its name is by construction
matching into someone else's naming, so it does not get to overwrite it.
"""

import pathlib
import re

DB = pathlib.Path(__file__).resolve().parents[1] / "gimme_collectors" / "pipeline" / "db.py"


def test_the_team_update_preserves_the_name_for_a_name_matched_source():
    source = DB.read_text(encoding="utf-8")
    update = re.search(r"UPDATE team SET.*?WHERE id = %s", source, re.S)
    assert update, "could not find the team update statement"
    body = update.group(0)
    # the name is written only when the source is not name-matched
    assert "name = CASE WHEN %s THEN name ELSE %s END" in body, (
        "upsert_team is overwriting team.name unconditionally again"
    )


def test_match_by_name_is_the_first_parameter_of_that_update():
    """The CASE reads the first bound parameter; if the argument order drifts,
    the flag and the name swap and every team gets renamed to 'true'."""
    source = DB.read_text(encoding="utf-8")
    call = re.search(r"UPDATE team SET.*?\n\s*\(\n(.*?)\n\s*\),", source, re.S)
    assert call, "could not find the parameters passed to the team update"
    first = call.group(1).strip().splitlines()[0].strip().rstrip(",")
    assert first == "t.match_by_name", f"first parameter is {first!r}, expected t.match_by_name"
