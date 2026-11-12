import datetime

import pytest
from pydantic import ValidationError

from snooker_score_bot.models import (
    MatchFixture,
    MatchFormat,
    MatchFormats,
    MatchOutcome,
    SnookerBreak,
    SnookerMatch,
    SnookerPlayer,
)


def test_deserialize_match_fixture_invalid_players_raises():
    with pytest.raises(ValueError):
        MatchFixture.from_storage(
            match_id="123e4567-e89b-12d3-a456-426614174000",
            player1=SnookerPlayer(name="Player One", group="L1"),
            player2=SnookerPlayer(name="Player Two", group="L2"),
            group="L1",
            format=MatchFormat(best_of=5, num_reds=15),
        )


def test_snooker_match_invalid_scorelines():
    """Test that a match outcome with an invalid scoreline raises a ValueError"""
    # with pytest.raises(ValueError):
    match = SnookerMatch(
        player1="Doe John",
        player2="Doe Jane",
        group="L1",
        round=1,
        format=MatchFormat(best_of=3, num_reds=15),
    )
    with pytest.raises(ValidationError):
        match.outcome = MatchOutcome(player1_score=1, player2_score=1)
    with pytest.raises(ValidationError):
        match.outcome = MatchOutcome(player1_score=2, player2_score=2)
    with pytest.raises(ValidationError):
        match.outcome = MatchOutcome(player1_score=3, player2_score=2)
    with pytest.raises(ValidationError):
        match.outcome = MatchOutcome(player1_score=2, player2_score=-1)


def test_snooker_match_break_by_non_match_player():
    match = SnookerMatch(
        player1="Doe John",
        player2="Doe Jane",
        group="L1",
        round=1,
        format=MatchFormat(best_of=3, num_reds=15),
    )
    with pytest.raises(ValidationError):
        match.outcome = MatchOutcome(
            player1_score=2,
            player2_score=1,
            breaks=[SnookerBreak(player=SnookerPlayer(name="Beam Jim", group="L1"), points=100)],
        )


def test_snooker_match_summary_with_breaks():
    player1 = SnookerPlayer(name="Trump Judd", group="L1")
    player2 = SnookerPlayer(name="Selby Mark", group="L1")

    # Create a valid outcome that gives a win to player1 (frames_to_win is 2 for best-of-3)
    outcome = MatchOutcome(
        player1_score=1,
        player2_score=2,
        date=datetime.date(2025, 1, 1),
        breaks=[
            SnookerBreak(player=player2, points=50),
            SnookerBreak(player=player1, points=100),
            SnookerBreak(player=player1, points=30),
        ],
    )
    match = SnookerMatch.from_storage(
        match_id="123e4567-e89b-12d3-a456-426614174000",
        player1=player1,
        player2=player2,
        group=player1.group,
        round=1,
        format=MatchFormats.LEAGUE.value,
        outcome=outcome,
    )

    summary_text = match.summary(lang="eng")
    assert "Selby Mark won Trump Judd by 2 frames to 1" in summary_text
    assert "Breaks: Judd 100, Mark 50, Judd 30." in summary_text
