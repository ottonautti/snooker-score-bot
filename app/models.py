import datetime
from typing import Literal, Optional, Union

from pydantic import BaseModel, create_model, root_validator, validator
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
    winner: Optional[str]

    highest_break: Optional[int]
    break_owner: Optional[str]

    _valid_players: list[SnookerPlayer] = []
    _max_score: int = 2

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

    @validator("player1_score", "player2_score")
    def valid_score(cls, score, values):
        """Scores must be between 0 and max_score"""
        assert score >= 0, "score must be greater than or equal to 0"
        assert score <= cls._max_score, f"score must be less than or equal to {cls._max_score}"
        return score

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
    def get_model(cls, valid_players: list[SnookerPlayer], max_score: Optional[int] = None):
        """Returns a SnookerMatch model with valid players set as a class attribute at runtime."""
        return create_model(
            cls.__name__,
            __base__=cls,
            _valid_players=valid_players,
            _max_score=max_score,
        )
