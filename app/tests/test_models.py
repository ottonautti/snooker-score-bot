import datetime
from itertools import permutations
import uuid
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
    InferredMatch
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
                MatchFixture.create(
                    round=1,
                    group=player1.group,
                    player1=player1.name,
                    player2=player2.name,
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


def test_create_match_fixture():
    match = MatchFixture.create(
        player1="Player One",
        player2="Player Two",
        group="L1",
    )
    assert match.player1.name == "Player One"
    assert match.player2.name == "Player Two"
    assert match.group == "L1"
    assert match.format == MatchFormats.BEST_OF_THREE.value


def test_deserialize_match_fixture():
    existing_match_id = "123e4567-e89b-12d3-a456-426614174000"
    match = MatchFixture.from_storage(
        match_id=existing_match_id,
        player1=SnookerPlayer(name="Player One", group="L1"),
        player2=SnookerPlayer(name="Player Two", group="L1"),
        group="L1",
        format=MatchFormat(best_of=5, num_reds=15),
    )
    assert match.match_id == existing_match_id
    assert match.player1.name == "Player One"
    assert match.player2.name == "Player Two"
    assert match.group == "L1"
    assert match.format.best_of == 5


def test_setting_match_id_raises():
    match = MatchFixture.create(player1="Player One", player2="Player Two", group="L1")
    with pytest.raises(AttributeError):
        match.match_id = uuid.uuid4()


def test_deserialize_match_fixture_invalid_players_raises():
    with pytest.raises(ValueError):
        MatchFixture.from_storage(
            match_id="123e4567-e89b-12d3-a456-426614174000",
            player1=SnookerPlayer(name="Player One", group="L1"),
            player2=SnookerPlayer(name="Player Two", group="L2"),
            group="L1",
            format=MatchFormat(best_of=5, num_reds=15),
        )


def test_snooker_match(mock_fixtures):
    fixture: MatchFixture = mock_fixtures[0]
    assert fixture.completed is False
    outcome = MatchOutcome(player1_score=2, player2_score=1, date=datetime.date(2025, 1, 1))
    match = SnookerMatch.from_storage(
        match_id=fixture.match_id,
        player1=fixture.player1,
        player2=fixture.player2,
        group=fixture.group,
        round=fixture.round,
        format=MatchFormats.BEST_OF_THREE.value,
        outcome=outcome,
    )
    md = match.model_dump()
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
