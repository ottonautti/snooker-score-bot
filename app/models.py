import datetime
import random
import string
from enum import Enum
from typing import Any, Optional, Union

from jinja2 import Template
from pydantic import BaseModel, computed_field, model_serializer, model_validator
from pydantic_core import PydanticCustomError

from pydantic.fields import Field


class MatchFixtureMismatchError(ValueError):
    pass


class SnookerPlayer(BaseModel):
    name: str
    group: Optional[str] = None

    def __repr__(self):
        return f"SnookerPlayer(name={self.name}, group={self.group})"

    def __str__(self):
        return self.name

    def __llm_str__(self) -> str:
        """Returns the group and name in the format "Group: Name".

        This is used in LLM prompts."""
        return f"{self.group}: {self.name}"

    def __eq__(self, value: object) -> bool:
        """A string matching name is enough for equality."""
        return self.name == str(value)

    def __hash__(self) -> int:
        return hash(self.name)

    @model_serializer
    def serialize_as_name(self) -> str:
        """Returns only the name when serializing the model"""
        return self.name

    @property
    def given_name(self) -> str:
        """In the data, names are formatted as "Lastname Firstname"."""
        return self.name.split()[-1] if len(self.name.split()) > 1 else self.name


class SnookerBreak(BaseModel):
    player: SnookerPlayer
    points: int = Field(gt=0, le=147)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SnookerBreak":
        """Create a SnookerBreak object from JSON data."""
        player = SnookerPlayer(name=data.pop("player"))
        return cls(player=player, **data)


class MatchFormat(BaseModel):
    best_of: int
    num_reds: int = 15

    @property
    def frames_to_win(self) -> int:
        return self.best_of // 2 + 1


class MatchFormats(Enum):
    BEST_OF_THREE = MatchFormat(best_of=3, num_reds=15)


class MatchFixture(BaseModel):
    """Match fixture i.e. an unplayed match between two players of a group"""

    match_id: str = Field(min_length=5, max_length=5, serialization_alias="id")
    round: Optional[int] = Field(alias="round", default=None)
    group: str
    player1: Union[SnookerPlayer, str]
    player2: Union[SnookerPlayer, str]
    format: MatchFormat = Field(default_factory=lambda: MatchFormats.BEST_OF_THREE.value)

    @model_validator(mode="before")
    def convert_players(self):
        """Convert player names to player objects."""
        if isinstance(self["player1"], str):
            self["player1"] = SnookerPlayer(name=self["player1"], group=self["group"])
            self["player2"] = SnookerPlayer(name=self["player2"], group=self["group"])
        return self

    @computed_field
    def completed(self) -> bool:
        if isinstance(self, SnookerMatch):
            return self.state == "completed"
        return False

    def csv(self, headers=False, **kwargs) -> dict:
        """Returns the model as a dictionary with JSON-compatible keys."""
        include = kwargs.get("include", None)
        str_ = ""
        hdrs, values = zip(*self.model_dump(include=include, by_alias=True).items())
        if headers:
            str_ += ",".join(hdrs) + "\n"
        str_ += ",".join([str(v) for v in values])
        return str_

    @classmethod
    def create(cls, **kwargs) -> "MatchFixture":
        """Create a MatchFixture for the first time."""
        # provision a match_id
        if "match_id" in kwargs:
            raise ValueError("match_id should not be provided for new match fixtures")
        match_id = "".join(random.choices(string.ascii_lowercase + string.digits, k=5))
        kwargs["match_id"] = str(match_id)
        return cls(**kwargs)


class MatchOutcome(BaseModel):
    """Match outcome i.e. a completed match with scores and breaks"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    player1_score: int = Field(default=None)
    player2_score: int = Field(default=None)
    breaks: list[SnookerBreak] = Field(default_factory=list)

    @property
    def scoreline(self) -> str:
        return f"{self.player1_score}–{self.player2_score}"


class SnookerMatch(MatchFixture, validate_assignment=True):
    """Complete snooker match with scores and breaks"""

    _fixtures: list[MatchFixture] = []
    outcome: Optional[MatchOutcome] = None

    @computed_field
    def state(self) -> str:
        """Returns the state of the match."""
        return "completed" if self.outcome else "unplayed"

    @model_validator(mode="after")
    def breaks_are_by_match_players(self):
        """Breaks have to be by one of the match players"""
        if self.outcome:
            for b in self.outcome.breaks:
                assert b.player in (self.player1, self.player2), f"Break by {b.player} not in match"
        return self

    @computed_field
    def winner(self) -> str:
        """Returns the winner of the match."""
        if not self.outcome:
            return None
        return self.player1 if self.outcome.player1_score > self.outcome.player2_score else self.player2

    @property
    def loser(self) -> str:
        """Returns the loser of the match."""
        if not self.outcome:
            return None
        return self.player1 if self.winner == self.player2 else self.player2

    @computed_field
    def highest_break(self) -> Optional[int]:
        """Returns the highest break"""
        if self.outcome:
            return max([b.points for b in self.outcome.breaks], default=None)

    @computed_field
    def highest_break_player(self) -> Optional[SnookerPlayer]:
        """Returns the player with the highest break"""
        if self.outcome:
            return next((b.player for b in self.outcome.breaks if b.points == self.highest_break), None)

    @model_validator(mode="after")
    def validate_players_and_outcome(self):
        """Asserts the following conditions:
        * Players must be different players
        * Players must belong in the same group
        * Outcome must be complete
        """
        if self.player1 == self.player2:
            raise PydanticCustomError("match_players_error", "Players can not be the same")
        if self.group != self.player1.group != self.player2.group:
            raise PydanticCustomError("match_players_error", "Players do not belong in the same group")

        if self.outcome:
            winning_score = max(self.outcome.player1_score, self.outcome.player2_score)
            losing_score = min(self.outcome.player1_score, self.outcome.player2_score)
            if self.outcome.player1_score is None or self.outcome.player2_score is None:
                raise PydanticCustomError("match_scoreline_error", "Incomplete outcome")
            if any([winning_score != self.format.frames_to_win, not 0 <= losing_score < winning_score]):
                raise PydanticCustomError(
                    "match_scoreline_error",
                    f"Scoreline {self.outcome.scoreline} does not match the match format "
                    + f"(best of {self.format.best_of} frames)",
                )
        return self

    def validate_against_fixture(self, fixture) -> "SnookerMatch":
        """Asserts the following conditions:
        * Match ID matches the fixture.
        * Group matches the group in the fixture.
        * Players match the players in the concerned fixture (by ID).
            * If the inferred player1 is actually player2 and vice versa, reverse the players.
        * Players can not be the same player.

        Returns the match if all conditions are met.
        """
        if self.match_id != fixture.match_id:
            raise MatchFixtureMismatchError(f"Match ID {self.match_id} doesn't match fixture")
        if self.group != fixture.group:
            raise MatchFixtureMismatchError(f"Group mismatch: {self.group} != {fixture.group}")
        # reverse the players if the inferred player1 is actually player2
        # this can be the case depending on LLM's quirks
        if self.player2 == fixture.player1 and self.player1 == fixture.player2:
            self.player1, self.player2 = self.player2, self.player1
            self.outcome.player1_score, self.outcome.player2_score = (
                self.outcome.player2_score,
                self.outcome.player1_score,
            )
        # if players still not matching, raise
        if self.player1 != fixture.player1 or self.player2 != fixture.player2:
            raise MatchFixtureMismatchError("Players do not match those in fixture")
        return self

    @classmethod
    def create_without_validating(cls, **kwargs) -> "SnookerMatch":
        """Create a match without performing validations."""
        return cls.model_construct(**kwargs)

    def summary(self, lang="eng") -> str:
        """Returns a string representation of the match."""

        TEMPLATES = {
            "eng": Template(
                """
{{ self.winner }} won {{ loser }} by {{ winner_score }} frames to {{ loser_score }}.
{%- if match.breaks -%}
    Breaks: {% for b in match.breaks -%} {{ b.player.given_name }} {{ b.points }} {%- if not
    loop.last %}, {% endif %}{%- endfor -%}.
{%- endif -%}
"""
            ),
        }

        summary = TEMPLATES[lang].render(
            match=self,
            winner=self.winner,
            loser=self.loser,
            winner_score=self.outcome.player1_score if self.winner == self.player1 else self.outcome.player2_score,
            loser_score=self.outcome.player2_score if self.winner == self.player1 else self.outcome.player1_score,
        )

        return f"{summary}"


class SnookerMatchList(BaseModel):
    round: int
    matches: list[Union[SnookerMatch, MatchFixture]] = Field(default_factory=list)

    @computed_field(alias="matches")
    def filter_completed(self) -> list[SnookerMatch]:
        """Filter for completed matches."""
        return [m for m in self.matches if m.completed]

    @computed_field(alias="matches")
    def filter_unplayed(self) -> list[SnookerMatch]:
        """Filter for unplayed matches."""
        return [m for m in self.matches if not m.completed]
