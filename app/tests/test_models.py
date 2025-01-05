import datetime
from itertools import permutations

import pytest

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
        SnookerPlayer(name="Doe John", group="A"),
        SnookerPlayer(name="Doe Jane", group="A"),
        SnookerPlayer(name="Beam Jim", group="A"),
        SnookerPlayer(name="Smith Alice", group="B"),
        SnookerPlayer(name="Brown Bob", group="B"),
        SnookerPlayer(name="Black Charlie", group="B"),
    ]


@pytest.fixture
def mock_fixtures(mock_players):
    """return a list of MatchFixture objects, all permutaions of the mock players (noting groups)"""
    fixtures = []
    for player1, player2 in permutations(mock_players, 2):
        if player1.group == player2.group:
            fixtures.append(
                MatchFixture(
                    f_id=f"{player1.name} vs {player2.name}",
                    round=1,
                    group=player1.group,
                    player1=player1,
                    player2=player2,
                    format=MatchFormats.BEST_OF_THREE.value,
                )
            )
    return fixtures


@pytest.fixture
def match_model(mock_fixtures):
    return SnookerMatch.configure_model(fixtures=mock_fixtures)


def test_snooker_player(mock_players):
    player = mock_players[0]
    assert player.name == "Doe John"
    assert player.group == "A"
    assert str(player) == "Doe John"
    assert player.given_name == "John"


def test_snooker_break(mock_players):
    player = mock_players[0]
    snooker_break = SnookerBreak(player=player, points=100)
    assert snooker_break.player == player
    assert snooker_break.points == 100


def test_match_format():
    format = MatchFormats.BEST_OF_THREE.value
    assert format.bestOf == 3
    assert format.reds == 15


def test_match_fixture(mock_players):
    fixture = MatchFixture(
        f_id="1",
        round=1,
        group="A",
        player1=mock_players[0],
        player2=mock_players[1],
    )
    assert fixture.f_id == "1"
    assert fixture.round == 1
    assert fixture.group == "A"
    assert fixture.player1.name == "Doe John"
    assert fixture.player2.name == "Doe Jane"
    assert fixture.format.bestOf == 3
    assert fixture.format.reds == 15


def test_snooker_match(match_model, mock_players):
    fixture = match_model._fixtures[0]
    outcome = MatchOutcome(player1_score=2, player2_score=1, date=datetime.date(2025, 1, 1))
    match = SnookerMatch(**fixture.model_dump(), **outcome.model_dump())
    assert match.player1 == fixture.player1
    assert match.player2 == fixture.player2
    assert match.format.bestOf == 3
    assert match.format.reds == 15
    assert match.player1_score == 2
    assert match.player2_score == 1
    assert match.date == datetime.date(2025, 1, 1)

def test_snooker_match_invalid_outcome(match_model):
    fixture = match_model._fixtures[0]
    with pytest.raises(ValueError):
        outcome = MatchOutcome(player1_score=1, player2_score=1, date=datetime.date(2025, 1, 1))
        match = SnookerMatch(**fixture.model_dump(), **outcome.model_dump())
