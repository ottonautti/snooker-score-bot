import datetime
from typing import Optional

from pydantic import BaseModel, create_model, root_validator, validator
from pydantic.fields import Field


class SnookerPlayer:
    def __init__(self, name, group):
        self.name = name
        self.group = group

    def __repr__(self):
        return f"SnookerPlayer(name={self.name}, group={self.group})"

    def __str__(self):
        return f"{self.name} ({self.group})"


class SnookerMatch(BaseModel):
    """Snooker match"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    group: str
    player1: str
    player2: str
    player1_score: int = Field(ge=0, le=3)
    player2_score: int = Field(ge=0, le=3)
    winner: Optional[str]

    highest_break: Optional[int]
    break_owner: Optional[str]

    _valid_players: list[SnookerPlayer] = []

    class Config:
        extra = "allow"  # for passing `passage`

    @validator("break_owner", always=True)
    def valid_highest_break(cls, name, values):
        """Break owner must be one of the players,

        If there is a break, there must be a break owner."""
        if values["highest_break"]:
            assert name in [values["player1"], values["player2"]], "break owner is not one of the match players."

        return name

    @validator("winner", always=True)
    def set_winner(cls, v, values):
        """Sets the winner based on scores"""
        if values.get("player1_score") == values.get("player2_score"):
            return None
        if values.get("player1_score") > values.get("player2_score"):
            return values.get("player1")
        return values.get("player2")

    @root_validator
    def check_players(cls, values):
        """Players have to be from the same group.
        Players can not be the same player."""
        player1_match = next((plr for plr in cls._valid_players if plr.name == values.get("player1")), None)
        player2_match = next((plr for plr in cls._valid_players if plr.name == values.get("player2")), None)

        assert player1_match, f"Player {values.get('player1')} not found in valid players."
        assert player2_match, f"Player {values.get('player2')} not found in valid players."

        assert (
            player1_match.group == player2_match.group
        ), f"Players {values.get('player1')} and {values.get('player2')} are not from the same group."

        assert values.get("player1") != values.get(
            "player2"
        ), f"Players {values.get('player1')} and {values.get('player2')} are the same player."

        return values

    @property
    def summary(self):
        """Returns a string representation of the match e.g. "Ahonen Otto won Vainikka Olli 3-0 (break 45, Ahonen Otto)"""
        loser = self.player1 if self.winner == self.player2 else self.player2
        winner_score = self.player1_score if self.winner == self.player1 else self.player2_score
        loser_score = self.player1_score if self.winner == self.player2 else self.player2_score

        if winner_score == loser_score:
            return f"Match between {self.player1} and {self.player2} ended in a draw at {winner_score} frames each."
        else:
            scoreline_str = f"{self.winner} won {loser} by {winner_score} frames to {loser_score}"
        break_str = f" (highest break {self.highest_break}, {self.break_owner})" if self.highest_break else "."
        return scoreline_str + break_str


def get_model(valid_players):
    return create_model(
        "SnookerMatch",
        __base__=SnookerMatch,
        _valid_players=valid_players,
    )
