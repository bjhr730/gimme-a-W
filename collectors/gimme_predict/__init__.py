"""gimme-a-W prediction engine.

Every market is a small, explainable model trained on our own `game` rows and
scored against the bookmaker's closing line. Features are built by walking games
in kickoff order, so a prediction only ever sees what was known before kickoff.
"""

__version__ = "0.1.0"
