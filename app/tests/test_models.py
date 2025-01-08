import datetime
import random
import string
from itertools import permutations

import pytest
from pydantic import ValidationError

from app.models import (
    MatchFixture,
    MatchFormat,
    MatchFormats,
    MatchOutcome,
    SnookerBreak,
    SnookerMatch,
    SnookerPlayer,
)


@pytest.fixture
def mock_players():
    return [
        SnookerPlayer(name="Doe John", group="L1"),
        SnookerPlayer(name="Doe Jane", group="L1"),
        SnookerPlayer(name="Beam Jim", group="L1"),
        SnookerPlayer(name="Smith Alice", group="L2"),
        SnookerPlayer(name="Brown Bob", group="L2"),
        SnookerPlayer(name="Black Charlie", group="L2"),
    ]


@pytest.fixture
def mock_fixtures(mock_players):
    """return a list of MatchFixture objects, all permutations of the mock players (noting groups)"""
    fixtures = []
    perms = permutations(mock_players, 2)
    for i, (player1, player2) in list(enumerate(perms)):
        if player1.group == player2.group:
            # 5 lower case ascii characters
            new_id = "".join(random.choices(string.ascii_lowercase, k=5))
            fixtures.append(
                MatchFixture(
                    match_id=new_id,
                    round=1,
                    group=player1.group,
                    player1=player1,
                    player2=player2,
                    format=MatchFormats.BEST_OF_THREE.value,
                )
            )
    return fixtures


def test_snooker_player(mock_players):
    player = mock_players[0]
    assert player.name == "Doe John"
    assert player.group == "L1"
    assert str(player) == "Doe John"
    assert player.given_name == "John"


def test_snooker_break(mock_players):
    player = mock_players[0]
    snooker_break = SnookerBreak(player=player, points=100)
    assert snooker_break.player == player
    assert snooker_break.points == 100


def test_match_format():
    format = MatchFormats.BEST_OF_THREE.value
    assert format.best_of == 3
    assert format.num_reds == 15


def test_match_fixture(mock_players):
    fixture = MatchFixture(
        match_id="abc12",
        round=1,
        group="L1",
        player1=mock_players[0],
        player2=mock_players[1],
    )
    md = fixture.model_dump()
    assert md["match_id"] == "abc12"
    assert md["round"] == 1
    assert md["group"] == "L1"
    assert md["player1"] == "Doe John"
    assert md["player2"] == "Doe Jane"


def test_snooker_match(mock_fixtures):
    fixture = mock_fixtures[0]
    assert fixture.completed is False
    outcome = MatchOutcome(player1_score=2, player2_score=1, date=datetime.date(2025, 1, 1))
    match = SnookerMatch(**fixture.model_dump(), outcome=outcome)
    md = match.model_dump()
    assert match.validate_against_fixture(fixture)
    assert md["completed"] is True
    assert md["player1"] == "Doe John"
    assert md["player2"] == "Doe Jane"
    assert md["format"]["best_of"] == 3
    assert md["format"]["num_reds"] == 15
    assert md["outcome"] == {
        "date": datetime.date(2025, 1, 1),
        "player1_score": 2,
        "player2_score": 1,
        "breaks": [],
    }


def test_snooker_match_invalid_scorelines():
    """Test that a match outcome with an invalid scoreline raises a ValueError"""
    # with pytest.raises(ValueError):
    match = SnookerMatch(
        match_id="abc12",
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
