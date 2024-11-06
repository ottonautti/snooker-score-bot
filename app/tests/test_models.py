from functools import partial

import pytest
from pydantic import ValidationError

from app.models import SnookerBreak, SnookerPlayer, ValidatedMatch, get_match_model

player1 = SnookerPlayer(name="Player Yksi", group="L1")
player2 = SnookerPlayer(name="Player Kaksi", group="L1")
player3 = SnookerPlayer(name="Player Kolme", group="L1")
players = [player1, player2]

match_model_for_testing = partial(get_match_model, valid_players=players, max_score=2)


def test_winner():
    match = match_model_for_testing(
        group="L1", player1="Player Yksi", player2="Player Kaksi", player1_score=2, player2_score=1
    )
    assert match.winner == player1

    match = match_model_for_testing(
        group="L1", player1="Player Yksi", player2="Player Kaksi", player1_score=1, player2_score=2
    )
    assert match.winner == player2

    match = match_model_for_testing(
        group="L1", player1="Player Yksi", player2="Player Kaksi", player1_score=1, player2_score=1
    )
    assert match.winner == None


def test_match_without_breaks():
    match = match_model_for_testing(
        group="L1", player1="Player Yksi", player2="Player Kaksi", player1_score=2, player2_score=1
    )
    assert match.breaks == []


def test_highest_break():
    match = match_model_for_testing(
        group="L1",
        player1="Player Yksi",
        player2="Player Kaksi",
        player1_score=2,
        player2_score=1,
        breaks=[{"player": "Player Yksi", "points": 50}, {"player": "Player Kaksi", "points": 60}],
    )
    assert match.highest_break == 60
    assert match.highest_break_player == player2


def test_invalid_match_score_raises():
    with pytest.raises(ValidationError):
        match = match_model_for_testing(
            group="L1", player1="Player Yksi", player2="Player Kaksi", player1_score=3, player2_score=1
        )
        match.valid_score(match.player1_score)


def test_players_not_from_correct_group_raises():
    with pytest.raises(ValidationError):
        match = match_model_for_testing(
            group="L2",
            player1="Player Yksi",
            player2="Player Kaksi",
            player1_score=2,
            player2_score=1,
            breaks=[{"player": "Player Yksi", "points": 50}, {"player": "Player Kaksi", "points": 60}],
        )
        match.check_players()


def test_breaks_are_by_match_players_raises():
    with pytest.raises(ValidationError):
        match = match_model_for_testing(
            group="L1",
            player1="Player Yksi",
            player2="Player Kaksi",
            player1_score=2,
            player2_score=1,
            breaks=[
                {"player": "Player Yksi", "points": 50},
                {"player": "Player Kolme", "points": 100},
            ],
        )
        match.breaks_are_by_match_players()


def test_match_summary():
    match = match_model_for_testing(
        group="L1",
        player1="Player Yksi",
        player2="Player Kaksi",
        player1_score=2,
        player2_score=1,
        breaks=[
            {"player": "Player Yksi", "points": 50},
            {"player": "Player Yksi", "points": 70},
            {"player": "Player Kaksi", "points": 60},
        ],
    )

    assert match.summary("fin").startswith(
        "Player Yksi voitti vastustajan Player Kaksi 2-1.\nBreikit: Yksi 50, Yksi 70, Kaksi 60."
    )
    assert match.summary("eng").startswith(
        "Player Yksi won Player Kaksi by 2 frames to 1.\nBreaks: Yksi 50, Yksi 70, Kaksi 60."
    )


def test_match_summary_no_breaks():
    match = match_model_for_testing(
        group="L1",
        player1="Player Yksi",
        player2="Player Kaksi",
        player1_score=2,
        player2_score=1,
        breaks=[],
    )

    assert match.summary("fin").startswith("Player Yksi voitti vastustajan Player Kaksi 2-1.")
    assert match.summary("eng").startswith("Player Yksi won Player Kaksi by 2 frames to 1.")
