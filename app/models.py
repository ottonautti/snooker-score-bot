import datetime
from typing import ClassVar, Literal, Optional, Union

from pydantic import BaseModel, computed_field, create_model, field_validator, model_validator
from pydantic.fields import Field


class EngMessages:
    RESULT_WIN = "{winner} won {loser} by {winner_score} frames to {loser_score}"
    RESULT_DRAW = "Match between {player1} and {player2} ended in a draw at {equal_score} frames each."
    BREAK = "(highest break {highest_break} by {break_owner})"


class FinMessages:
    RESULT_WIN = "{winner} voitti vastustajan {loser} {winner_score} - {loser_score}"
    RESULT_DRAW = "Ottelu {player1} - {player2} päättyi tasapeliin {equal_score} - {equal_score}."
    BREAK = "(korkein breikki {highest_break}, {break_owner})"


def get_messages(lang: Literal["fin", "eng"]) -> Union[FinMessages, EngMessages]:
    if lang.lower() == "fin":
        return FinMessages
    else:
        return EngMessages


class SnookerPlayer(BaseModel):
    name: str
    group: str

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
    player1_score: int
    player2_score: int

    highest_break: Optional[int] = None
    break_owner: Optional[str] = None

    valid_players: ClassVar[list[SnookerPlayer]]
    max_score: ClassVar[int] = 2

    @computed_field
    def winner(self) -> str:
        """Sets the winner based on scores"""
        if self.player1_score == self.player2_score:
            return None
        if self.player1_score > self.player2_score:
            return self.player1
        return self.player2

    @field_validator("player1_score", "player2_score")
    def valid_score(cls, score):
        """Scores must be between 0 and max_score"""
        assert score >= 0, "score must be greater than or equal to 0"
        assert score <= cls.max_score, f"score must be less than or equal to {cls.max_score}"
        return score

    @model_validator(mode="after")
    def check_players(self):
        """Players have to belong to valid players. Players have to be from the same group. Players can not be the same player."""
        # Find the player objects in the valid_players list
        player1 = next((player for player in self.valid_players if player.name == self.player1), None)
        player2 = next((player for player in self.valid_players if player.name == self.player2), None)

        # Check that both players are in the list of valid players
        assert player1 is not None, f"{self.player1} is not a valid player"
        assert player2 is not None, f"{self.player2} is not a valid player"

        # Check that both players are from the same group
        assert player1.group == player2.group, "Players are not from the same group"

        # Check that the two players are not the same
        assert player1 != player2, "Players cannot be the same player"

        return self

    @model_validator(mode="after")
    def valid_highest_break(self):
        """If there is a break, there must be a break owner. Break owner must be one of the players"""
        if self.highest_break:
            assert self.break_owner in [self.player1, self.player2], "break owner is not one of the match players."

        return self

    def summary(self, lang="eng") -> str:
        """Returns a string representation of the match.

        For example:
            'Ahonen Otto won Vainikka Olli 3-0 (break 45, Ahonen Otto)'.
        """
        loser = self.player1 if self.winner == self.player2 else self.player2
        winner_score = self.player1_score if self.winner == self.player1 else self.player2_score
        loser_score = self.player1_score if self.winner == self.player2 else self.player2_score

        messages = get_messages(lang)

        if winner_score == loser_score:
            result = messages.RESULT_DRAW.format(
                player1=self.player1,
                player2=self.player2,
                equal_score=self.player1_score,
            )
        else:
            result = messages.RESULT_WIN.format(
                winner=self.winner,
                loser=loser,
                winner_score=winner_score,
                loser_score=loser_score,
            )
        break_ = ""
        if self.highest_break:
            break_ += " " + messages.BREAK.format(
                highest_break=self.highest_break,
                break_owner=self.break_owner,
            )

        return result + break_

    @classmethod
    def get_model(cls, valid_players: list[SnookerPlayer], max_score: Optional[int] = 2) -> "SnookerMatch":
        """Returns a version of the model with valid players set at runtime."""
        return create_model(
            cls.__name__,
            __base__=cls,
            valid_players=valid_players,
            max_score=max_score,
        )
