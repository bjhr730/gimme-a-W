"""Publishing props for the players anyone would look up, not the whole roster."""

from gimme_predict.markets.football_players import PlayerProp
from gimme_predict.props import PROPS_PER_TEAM, top_by_involvement


def prop(player, team, market, mean=None, probability=None, game=1):
    return PlayerProp(
        game_id=game,
        player_id=player,
        team_id=team,
        name=f"p{player}",
        position=None,
        market=market,
        mean=mean,
        probability=probability,
    )


def squad(team, game=1, size=9, base=0):
    """One quarterback and eight others, descending in projected yardage."""
    rows = [prop(base + 1, team, "passing_yards", mean=250.0, game=game)]
    for i in range(2, size + 1):
        rows.append(prop(base + i, team, "rushing_yards", mean=100.0 - i * 10, game=game))
    return rows


def players(rows):
    return {r.player_id for r in rows}


def test_only_the_top_five_players_per_team_survive():
    kept = top_by_involvement(squad(team=10))
    assert len(players(kept)) == PROPS_PER_TEAM
    assert players(kept) == {1, 2, 3, 4, 5}  # the quarterback plus the four busiest


def test_every_market_a_kept_player_has_is_kept():
    rows = [
        prop(1, 10, "rushing_yards", mean=80.0),
        prop(1, 10, "receiving_yards", mean=30.0),
        prop(1, 10, "anytime_td", probability=0.4),
        *squad(team=10, size=9, base=100),
    ]
    kept = top_by_involvement(rows)
    mine = [r.market for r in kept if r.player_id == 1]
    assert sorted(mine) == ["anytime_td", "receiving_yards", "rushing_yards"]


def test_both_sides_of_a_game_get_their_own_five():
    rows = squad(team=10) + squad(team=20, base=100)
    kept = top_by_involvement(rows)
    assert len({r.player_id for r in kept if r.team_id == 10}) == PROPS_PER_TEAM
    assert len({r.player_id for r in kept if r.team_id == 20}) == PROPS_PER_TEAM


def test_each_game_is_capped_separately():
    rows = squad(team=10, game=1) + squad(team=10, game=2)
    kept = top_by_involvement(rows)
    for game in (1, 2):
        assert len({r.player_id for r in kept if r.game_id == game}) == PROPS_PER_TEAM


def test_a_short_roster_is_kept_whole():
    rows = [prop(1, 10, "rushing_yards", mean=50.0), prop(2, 10, "rushing_yards", mean=20.0)]
    assert len(top_by_involvement(rows)) == 2
    assert top_by_involvement([]) == []


def test_touchdown_probability_does_not_outrank_yardage():
    """A goal-line back with a high touchdown chance and no yards is not more
    involved than a starter; probability is on a different scale and is ignored
    when ranking."""
    rows = [
        *squad(team=10, size=5),  # five genuine starters
        prop(99, 10, "anytime_td", probability=0.95),  # goal-line specialist only
    ]
    kept = top_by_involvement(rows)
    assert 99 not in players(kept)
    assert len(players(kept)) == PROPS_PER_TEAM


def test_a_player_with_no_projection_sorts_last_without_crashing():
    rows = [
        *squad(team=10, size=5),
        prop(98, 10, "rushing_yards", mean=None),
        prop(97, 10, "receiving_yards", mean=0.0),
    ]
    kept = top_by_involvement(rows)
    assert players(kept) == {1, 2, 3, 4, 5}
