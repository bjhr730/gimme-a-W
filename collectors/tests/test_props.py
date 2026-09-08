"""Player and team markets on synthetic histories."""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

import numpy as np

from gimme_predict.data import Game
from gimme_predict.markets import football_players, soccer_props
from gimme_predict.models import PoissonGLM
from gimme_predict.players import PlayerGame, Rolling, walk_football


def _game(i: int, home: int, away: int, days: int, sport: str = "american_football") -> Game:
    return Game(
        id=i,
        competition="x",
        sport=sport,
        season_id=1,
        season_label="2025",
        kickoff=datetime(2025, 9, 7, tzinfo=UTC) + timedelta(days=days),
        home_id=home,
        away_id=away,
        home_name=f"T{home}",
        away_name=f"T{away}",
        home_abbr=None,
        away_abbr=None,
        status="final",
        home_score=24,
        away_score=20,
        neutral=False,
        week=None,
        market={"spread_home_line": -3.0, "total_over_line": 45.0},
    )


def test_poisson_glm_and_over_probabilities():
    rng = random.Random(3)
    x = np.array([[rng.uniform(-1, 1)] for _ in range(400)])
    mu = np.exp(1.2 + 0.8 * x[:, 0])
    y = np.array([sum(rng.random() < m / 20 for _ in range(20)) for m in mu], dtype=float)
    glm = PoissonGLM(alpha=0.01).fit(x, y)
    assert abs(glm.intercept_ - 1.2) < 0.15 and abs(glm.coef_[0] - 0.8) < 0.25
    p = glm.prob_over(4.0, 3.5)
    assert 0.4 < p < 0.8
    assert glm.prob_over(4.0, 0.5) > glm.prob_over(4.0, 6.5)


def _football_history(weeks: int = 20) -> tuple[list[PlayerGame], dict[int, Game]]:
    rng = random.Random(4)
    rows: list[PlayerGame] = []
    games: dict[int, Game] = {}
    gid = 0
    # 4 teams, each with a QB (id t*10+1), RB (t*10+2), WR (t*10+3)
    for week in range(weeks):
        pairs = [(1, 2), (3, 4)] if week % 2 == 0 else [(1, 3), (2, 4)]
        for home, away in pairs:
            gid += 1
            g = _game(gid, home, away, week * 7)
            games[gid] = g
            for team, opp, is_home in ((home, away, True), (away, home, False)):
                qb, rb, wr = team * 10 + 1, team * 10 + 2, team * 10 + 3
                pass_yds = max(0, round(rng.gauss(230 + 15 * team, 50)))
                rush_yds = max(0, round(rng.gauss(70 + 10 * team, 25)))
                rec_yds = max(0, round(rng.gauss(80 + 10 * team, 30)))
                for pid, pos, stats in (
                    (
                        qb,
                        "QB",
                        {
                            "passingAttempts": 33,
                            "passingYards": pass_yds,
                            "passingTouchdowns": 2 if pass_yds > 240 else 1,
                            "categories": ["passing"],
                        },
                    ),
                    (
                        rb,
                        "RB",
                        {
                            "rushingAttempts": 16,
                            "rushingYards": rush_yds,
                            "rushingTouchdowns": 1 if rush_yds > 80 else 0,
                            "targets": 3,
                            "receivingYards": 15,
                            "categories": ["rushing", "receiving"],
                        },
                    ),
                    (
                        wr,
                        "WR",
                        {
                            "targets": 9,
                            "receptions": 6,
                            "receivingYards": rec_yds,
                            "receivingTouchdowns": 1 if rec_yds > 95 else 0,
                            "categories": ["receiving"],
                        },
                    ),
                ):
                    rows.append(
                        PlayerGame(
                            game_id=gid,
                            kickoff=g.kickoff,
                            season_id=1,
                            team_id=team,
                            opp_id=opp,
                            home=is_home,
                            player_id=pid,
                            name=f"P{pid}",
                            position=pos,
                            stats=stats,
                        )
                    )
    return rows, games


def test_football_props_walk_and_predict():
    rows, games = _football_history()
    history, players, teams, allowed = walk_football(rows, games)
    assert len(history) == len(rows)
    # the first row of every player has no history; later rows do
    assert history[0].player.games == 0
    late = [h for h in history if h.pg.player_id == 41][-1]
    assert late.player.games == Rolling().n
    assert late.team.mean("attempts") == 33
    assert late.opp_allowed.games > 0
    model = football_players.train(history)
    assert model is not None and "passing" in model.yards and model.td is not None
    upcoming = _game(999, 4, 1, 200)
    upcoming.status = "scheduled"
    preds = football_players.predict_player(
        model,
        game=upcoming,
        home=True,
        player_id=41,
        team_id=4,
        name="P41",
        position="QB",
        player=players[41],
        team=teams[4],
        allowed=allowed[1],
    )
    passing = next(p for p in preds if p.market == "passing_yards")
    assert passing.mean is not None and 200 < passing.mean < 340
    assert (
        passing.p25 is not None
        and passing.p75 is not None
        and passing.p25 < passing.mean < passing.p75
    )
    assert not any(p.market == "anytime_td" for p in preds)  # a QB with no touches
    rb_preds = football_players.predict_player(
        model,
        game=upcoming,
        home=True,
        player_id=42,
        team_id=4,
        name="P42",
        position="RB",
        player=players[42],
        team=teams[4],
        allowed=allowed[1],
    )
    td = next(p for p in rb_preds if p.market == "anytime_td")
    assert td.probability is not None and 0 < td.probability < 1
    rush = next(p for p in rb_preds if p.market == "rushing_yards")
    assert rush.mean is not None and 60 < rush.mean < 150


def test_soccer_props_counts_and_scorers():
    rng = random.Random(5)
    team_rows = []
    gid = 0
    rates = {1: 6.0, 2: 5.0, 3: 4.0, 4: 3.0}
    for rnd in range(20):
        pairs = [(1, 2), (3, 4)] if rnd % 2 == 0 else [(1, 4), (2, 3)]
        for home, away in pairs:
            gid += 1
            kickoff = datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=rnd * 7)
            for team, opp, is_home in ((home, away, True), (away, home, False)):
                sot = sum(rng.random() < rates[team] / 20 for _ in range(20))
                corners = sum(rng.random() < 5.5 / 20 for _ in range(20))
                team_rows.append(
                    {
                        "game_id": gid,
                        "kickoff": kickoff,
                        "season_id": 1,
                        "team_id": team,
                        "opp_id": opp,
                        "home": is_home,
                        "stats": {"shotsOnTarget": sot, "wonCorners": corners, "totalGoals": 1},
                    }
                )
    model = soccer_props.train(team_rows)
    assert model is not None and "shots_on_target" in model.counts
    g = _game(999, 1, 4, 200, sport="soccer")
    counts = soccer_props.predict_counts(model, g)
    home_sot = next(c for c in counts if c.market == "shots_on_target" and c.team_id == 1)
    away_sot = next(c for c in counts if c.market == "shots_on_target" and c.team_id == 4)
    assert home_sot.mean > away_sot.mean
    assert 0 < home_sot.lines["over 4.5"] < 1
    match = next(c for c in counts if c.market == "match_corners")
    assert match.team_id is None and match.mean > 5

    # players: the striker scores most, the playmaker assists most.
    # A full lineup is used so the squad is completely on record; see the thin
    # squad case below for what happens when it is not.
    squad = [
        # id, goals, shots, shots on target, assists, starter
        (11, 1, 4, 2, 0, 1),
        (12, 0, 1, 0.5, 1, 1),
        (13, 0, 0.5, 0.25, 0, 0),
    ]
    squad += [(20 + i, 0, 0.5, 0.25, 0, 1) for i in range(9)]
    lineup_rows = []
    for k in range(8):
        for pid, goals, shots, sot, assists, start in squad:
            lineup_rows.append(
                PlayerGame(
                    game_id=k + 1,
                    kickoff=datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=k * 7),
                    season_id=1,
                    team_id=1,
                    opp_id=2,
                    home=True,
                    player_id=pid,
                    name=f"P{pid}",
                    position="F",
                    stats={
                        "totalGoals": goals if pid != 11 or k % 2 == 0 else 0,
                        "totalShots": shots,
                        "shotsOnTarget": sot,
                        "goalAssists": assists,
                        "starter": bool(start),
                        "subbedIn": not start,
                    },
                )
            )
    threat = soccer_props.player_threat(lineup_rows)
    roster = [{"player_id": pid, "full_name": f"P{pid}", "position": "F"} for pid, *_ in squad]
    players = soccer_props.predict_players(
        g,
        team_id=1,
        team_xg=1.8,
        team_sot=4.5,
        roster=roster,
        threat=threat,
        team_games_window=8,
    )
    assert players[0].player_id == 11 and 0.2 < players[0].probability < 0.9
    # with the whole squad on record the parts add back to the team totals
    assert abs(sum(s.expected_goals for s in players) - 1.8) < 0.25
    assert abs(sum(s.expected_sot for s in players) - 4.5) < 0.25
    assert abs(sum(s.expected_assists for s in players) - 1.8 * soccer_props.ASSIST_RATE) < 0.25
    striker = next(s for s in players if s.player_id == 11)
    playmaker = next(s for s in players if s.player_id == 12)
    assert striker.expected_sot > playmaker.expected_sot
    assert playmaker.expected_assists > striker.expected_assists
    # two or more shots on target is never likelier than one or more
    assert striker.sot_probability > striker.sot_two_probability > 0
    assert striker.explanation["squad_covered"] == 1.0

    # a player reported out takes no share; the rest of the squad absorbs it
    without = soccer_props.predict_players(
        g,
        team_id=1,
        team_xg=1.8,
        team_sot=4.5,
        roster=roster,
        threat=threat,
        team_games_window=8,
        play_probability={11: 0.0},
    )
    assert all(s.player_id != 11 for s in without)
    assert next(s for s in without if s.player_id == 12).expected_goals > playmaker.expected_goals

    # only three players on record: the unknown rest of the squad still takes a
    # share, so nobody is credited with the whole team's goals
    thin = soccer_props.predict_players(
        g,
        team_id=1,
        team_xg=1.8,
        team_sot=4.5,
        roster=roster[:3],
        threat=threat,
        team_games_window=8,
    )
    assert sum(s.expected_goals for s in thin) < 0.9
    thin_striker = next(s for s in thin if s.player_id == 11)
    assert thin_striker.probability < striker.probability
    assert thin_striker.explanation["squad_covered"] < 0.5
