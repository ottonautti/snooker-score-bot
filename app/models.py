import datetime
import uuid
from enum import Enum
from typing import Any, Optional, Union

from jinja2 import Template
from pydantic import BaseModel, computed_field, field_validator, model_serializer, model_validator
from pydantic.fields import Field, PrivateAttr
from pydantic_core import PydanticCustomError
from typing import Literal


class BreakRequest(BaseModel):
    player: Literal["player1", "player2"]
    points: int


class ScoreRequest(BaseModel):
    breaks: Optional[list[BreakRequest]]
    player1_score: int
    player2_score: int


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
    LEAGUE = MatchFormat(best_of=3, num_reds=15)
    SIXRED = MatchFormat(best_of=5, num_reds=6)


class MatchOutcome(BaseModel):
    """Match outcome i.e. a completed match with scores and breaks"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    player1_score: int = Field(default=None)
    player2_score: int = Field(default=None)
    breaks: list[SnookerBreak] = Field(default_factory=list)

    @property
    def scoreline(self) -> str:
        return f"{self.player1_score}–{self.player2_score}"

    @field_validator("breaks")
    def sort_breaks(cls, breaks: list[SnookerBreak]) -> list[SnookerBreak]:
        """Sort breaks by points in descending order."""
        return sorted(breaks, key=lambda b: b.points, reverse=True)


class MatchFixture(BaseModel):
    """Match fixture i.e. an unplayed match between two players of a group"""

    _match_id: uuid.UUID = PrivateAttr(default_factory=lambda: uuid.uuid4())
    round: Optional[int] = Field(default=None)
    group: str
    player1: SnookerPlayer
    player2: SnookerPlayer
    format: Optional[MatchFormat] = None

    @property
    def match_id(self) -> str:
        return str(self._match_id)

    @computed_field
    def id(self) -> str:
        """Included in API responses."""
        return self.match_id

    @model_validator(mode="before")
    def convert_players(self):
        """Convert player names to player objects."""
        if isinstance(self["player1"], str):
            self["player1"] = SnookerPlayer(name=self["player1"], group=self["group"])
        if isinstance(self["player2"], str):
            self["player2"] = SnookerPlayer(name=self["player2"], group=self["group"])
        return self

    @model_validator(mode="after")
    def groups_agree(self):
        """Players must belong in the same group."""
        if not (self.group == self.player1.group == self.player2.group):
            raise PydanticCustomError("group_mismatch", "Mismatch in group")
        return self

    @computed_field
    def completed(self) -> bool:
        if isinstance(self, SnookerMatch):
            return self.state == "completed"
        return False

    @classmethod
    def create(cls, player1: str, player2: str, group: str, **kwargs) -> "MatchFixture":
        """Create a match fixture from player names, provisioning a match ID.

        Validates the model before returning."""
        instance = cls.model_construct(
            player1=SnookerPlayer(name=player1, group=group),
            player2=SnookerPlayer(name=player2, group=group),
            group=group,
            **kwargs,
        )
        return cls.model_validate(instance)

    @classmethod
    def from_storage(cls, match_id: str, **data) -> Union["MatchFixture", "SnookerMatch"]:
        """Create a match fixture from storage or inferred data, using existing match ID.

        Validates the model before returning."""

        instance = cls.model_construct(_match_id=match_id, **data)
        return cls.model_validate(instance)


class SnookerMatch(MatchFixture, validate_assignment=True):
    """Complete snooker match with scores and breaks"""

    outcome: Optional[MatchOutcome] = None

    def __str__(self):
        return f"{self.player1} vs {self.player2}"

    @computed_field
    def state(self) -> str:
        """Returns the state of the match."""
        return "completed" if self.outcome else "unplayed"

    @model_validator(mode="after")
    def breaks_are_by_match_players(self):
        """Breaks have to be by one of the match players"""
        if self.outcome:
            for b in self.outcome.breaks:
                assert b.player in (
                    self.player1,
                    self.player2,
                ), f"Break by player not participating in match {b.player}"
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

        if self.outcome:
            winning_score = max(self.outcome.player1_score, self.outcome.player2_score)
            losing_score = min(self.outcome.player1_score, self.outcome.player2_score)
            if self.outcome.player1_score is None or self.outcome.player2_score is None:
                raise PydanticCustomError("match_scoreline_error", "Incomplete outcome")
            if isinstance(self.format, MatchFormat):
                if any([winning_score != self.format.frames_to_win, not 0 <= losing_score < winning_score]):
                    raise PydanticCustomError(
                        "match_scoreline_error",
                        f"Scoreline {self.outcome.scoreline} does not match the match format "
                        + f"(best of {self.format.best_of} frames)",
                    )
        return self

    def summary(self, lang="eng", link=None) -> str:
        """Returns a string representation of the match."""

        TEMPLATES = {
            "eng": Template(
                """
            {{ winner }} won {{ loser }} by {{ winner_score }} frames to {{ loser_score }}.
            {%- if breaks %} Breaks: {% for b in breaks -%} {{ b.player.given_name }} {{ b.points }}{%- if not loop.last %}, {% endif %}{%- endfor -%}.
            {%- endif -%}
            """
            ),
        }

        summary = (
            TEMPLATES[lang]
            .render(
                winner=self.winner.name,
                loser=self.loser.name,
                winner_score=self.outcome.player1_score if self.winner == self.player1 else self.outcome.player2_score,
                loser_score=self.outcome.player2_score if self.winner == self.player1 else self.outcome.player1_score,
                breaks=self.outcome.breaks,
            )
            .strip()
        )

        if link:
            summary += f"\n\nLeague standings: {link}"
        return summary


class SnookerMatchList(BaseModel):
    round: int
    matches: list[SnookerMatch] = []


class InferredMatch(BaseModel):
    group: str
    player1: str
    player2: str
    player1_score: int
    player2_score: int
    winner: str
    breaks: Optional[list[dict]] = Field(default_factory=list)
