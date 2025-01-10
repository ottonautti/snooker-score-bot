import datetime
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
            fixtures.append(
                MatchFixture(
                    round=1,
                    group=player1.group,
                    player1=SnookerPlayer(name=player1.name, group=player1.group),
                    player2=SnookerPlayer(name=player2.name, group=player2.group),
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
        round=1,
        group="L1",
        player1=SnookerPlayer(name="Doe John", group="L1"),
        player2=SnookerPlayer(name="Doe Jane", group="L1"),
    )
    md = fixture.model_dump()
    assert md["round"] == 1
    assert md["group"] == "L1"
    assert md["player1"] == "Doe John"
    assert md["player2"] == "Doe Jane"

    # match_id can't be mutated
    with pytest.raises(ValidationError):
        fixture.match_id = "foobar"

    # match_id can't be set manually
    with pytest.raises(ValidationError):
        fixture_with_manual_id = MatchFixture(
            match_id="foobar",
            round=1,
            group="L1",
            player1=SnookerPlayer(name="Doe John", group="L1"),
            player2=SnookerPlayer(name="Doe Jane", group="L1"),
        )

    # ... except when done via `_existing_match_id`
    existing_fixture = MatchFixture(
        _existing_match_id="foobar",
        round=1,
        group="L1",
        player1=SnookerPlayer(name="Doe John", group="L1"),
        player2=SnookerPlayer(name="Doe Jane", group="L1"),
    )
    assert existing_fixture.match_id == "foobar"


def test_snooker_match(mock_fixtures):
    fixture: MatchFixture = mock_fixtures[0]
    assert fixture.completed is False
    outcome = MatchOutcome(player1_score=2, player2_score=1, date=datetime.date(2025, 1, 1))
    match = SnookerMatch(
        _existing_match_id=fixture.match_id,
        player1=fixture.player1.name,
        player2=fixture.player2.name,
        group=fixture.group,
        round=fixture.round,
        format=MatchFormats.BEST_OF_THREE.value,
        outcome=outcome,
    )
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
