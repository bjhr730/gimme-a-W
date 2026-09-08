"""Match a source's team name ("Man United", "Ath Bilbao") to an ESPN team name.

Strategy, in order: explicit alias, exact normalized match, token containment
("Celta" in "Celta Vigo"), then a conservative fuzzy ratio. Anything below the
threshold is returned as None so the caller can report it instead of guessing.
"""

from __future__ import annotations

import difflib
import unicodedata

# source name -> ESPN display name (only where normalization alone would fail)
ALIASES: dict[str, str] = {
    "man united": "Manchester United",
    "man city": "Manchester City",
    "nott'm forest": "Nottingham Forest",
    "spurs": "Tottenham Hotspur",
    "wolves": "Wolverhampton Wanderers",
    "sheffield united": "Sheffield United",
    "sheffield weds": "Sheffield Wednesday",
    "west brom": "West Bromwich Albion",
    "qpr": "Queens Park Rangers",
    "ath madrid": "Atletico Madrid",
    "ath bilbao": "Athletic Club",
    "betis": "Real Betis",
    "sociedad": "Real Sociedad",
    "vallecano": "Rayo Vallecano",
    "espanol": "Espanyol",
    "celta": "Celta Vigo",
    "alaves": "Alavés",
    "cadiz": "Cádiz",
    "leganes": "Leganés",
    "inter": "Internazionale",
    "milan": "AC Milan",
    "roma": "AS Roma",
    "verona": "Hellas Verona",
    "bayern munich": "Bayern Munich",
    "dortmund": "Borussia Dortmund",
    "leverkusen": "Bayer Leverkusen",
    "rb leipzig": "RB Leipzig",
    "ein frankfurt": "Eintracht Frankfurt",
    "m'gladbach": "Borussia Mönchengladbach",
    "fc koln": "FC Cologne",
    "mainz": "Mainz",
    "hoffenheim": "TSG Hoffenheim",
    "stuttgart": "VfB Stuttgart",
    "wolfsburg": "VfL Wolfsburg",
    "freiburg": "SC Freiburg",
    "augsburg": "FC Augsburg",
    "werder bremen": "Werder Bremen",
    "union berlin": "Union Berlin",
    "st pauli": "FC St. Pauli",
    "heidenheim": "1. FC Heidenheim",
    "paris sg": "Paris Saint-Germain",
    "st etienne": "Saint-Étienne",
    "psv eindhoven": "PSV Eindhoven",
    "sp lisbon": "Sporting CP",
    "porto": "FC Porto",
    "sp braga": "SC Braga",
    "guimaraes": "Vitória de Guimarães",
}


def normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).lower()
    text = text.replace("&", "and").replace("'", "").replace(".", " ").replace("-", " ")
    tokens = [
        t
        for t in text.split()
        if t
        not in {
            "fc",
            "cf",
            "afc",
            "sc",
            "ac",
            "as",
            "ss",
            "us",
            "club",
            "de",
            "cd",
            "sd",
            "ud",
            "rcd",
            "bsc",
            "vfl",
            "vfb",
            "tsg",
            "sv",
            "fsv",
            "1",
            "the",
        }
    ]
    return " ".join(tokens)


def match_team(source_name: str, candidates: dict[str, int], *, cutoff: float = 0.86) -> int | None:
    """Return the id of the best candidate for `source_name`.

    `candidates` maps ESPN display names (and optionally short names) to team ids.
    """
    key = source_name.strip().lower()
    alias = ALIASES.get(key)
    norm_candidates = {normalize(name): team_id for name, team_id in candidates.items()}
    if alias:
        hit = norm_candidates.get(normalize(alias))
        if hit is not None:
            return hit
    wanted = normalize(alias or source_name)
    if wanted in norm_candidates:
        return norm_candidates[wanted]
    # token containment, both directions, when the shorter side has >= 4 chars
    contained = [
        team_id
        for name, team_id in norm_candidates.items()
        if len(wanted) >= 4 and (wanted in name.split() or wanted in name or name in wanted)
    ]
    if len(set(contained)) == 1:
        return contained[0]
    close = difflib.get_close_matches(wanted, list(norm_candidates), n=2, cutoff=cutoff)
    if len(close) == 1 or (
        len(close) > 1
        and difflib.SequenceMatcher(None, wanted, close[0]).ratio()
        > difflib.SequenceMatcher(None, wanted, close[1]).ratio() + 0.05
    ):
        return norm_candidates[close[0]]
    return None
