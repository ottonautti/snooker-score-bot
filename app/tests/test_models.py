import pytest
from app.models import SnookerBreak, SnookerMatch, SnookerPlayer

from pydantic import ValidationError

players = [SnookerPlayer(name="Player 1", group="L1"), SnookerPlayer(name="Player 2", group="L1")]
MatchModel = SnookerMatch.get_model(valid_players=players, max_score=2)


def test_winner():
    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=2, player2_score=1, breaks=[])
    assert match.winner == "Player 1"

    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=1, player2_score=2, breaks=[])
    assert match.winner == "Player 2"

    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=1, player2_score=1, breaks=[])
    assert match.winner == None

def test_match_without_breaks():
    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=2, player2_score=1)
    assert match.breaks == []

def test_highest_break():
    breaks = [SnookerBreak(player="Player 1", points=50), SnookerBreak(player="Player 2", points=60)]
    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=2, player2_score=1, breaks=breaks)
    assert match.highest_break == 60


def test_highest_break_player():
    breaks = [SnookerBreak(player="Player 1", points=50), SnookerBreak(player="Player 2", points=60)]
    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=2, player2_score=1, breaks=breaks)
    assert match.highest_break_player == "Player 2"


def test_breaks_are_by_match_players():
    breaks = [SnookerBreak(player="Player 1", points=50), SnookerBreak(player="Player 2", points=60)]
    match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=2, player2_score=1, breaks=breaks)
    assert match.breaks_are_by_match_players() == match


def test_invalid_match_score_raises():
    with pytest.raises(ValidationError):
        match = MatchModel(group="L1", player1="Player 1", player2="Player 2", player1_score=3, player2_score=1, breaks=[])
        match.valid_score(match.player1_score)


def test_breaks_are_by_match_players_raises():
    with pytest.raises(ValidationError):
        breaks = [SnookerBreak(player="Player 1", points=50), SnookerBreak(player="Player 2", points=60)]
        match = MatchModel(group="L1", player1="Player 1", player2="Player 3", player1_score=2, player2_score=1, breaks=breaks)
        match.breaks_are_by_match_players()
