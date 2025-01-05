import datetime
from enum import Enum
from typing import Any, Optional, Union

from jinja2 import Template
from pydantic import (
    BaseModel,
    computed_field,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.fields import Field


class SnookerPlayer(BaseModel):
    name: str
    group: str

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
        if isinstance(self, str):
            return self
        return self.name

    @property
    def given_name(self) -> str:
        """In the data, names are formatted as "Lastname Firstname"."""
        return self.name.split()[-1] if len(self.name.split()) > 1 else self.name


class SnookerBreak(BaseModel):
    player: SnookerPlayer
    points: int = Field(gt=0, le=147)


class MatchFormat(BaseModel):
    bestOf: int
    reds: int


class MatchFormats(Enum):
    BEST_OF_THREE = MatchFormat(bestOf=3, reds=15)


class MatchFixture(BaseModel):
    """Match fixture i.e. an unplayed match between two players of a group"""

    f_id: Optional[str] = Field(default=None)
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
    def state(self) -> str:
        """Returns the state of the match/fixture.

        If it's a SnookerMatch with scores, the state is "completed", otherwise "unplayed".
        """
        if isinstance(self, SnookerMatch):
            return self._get_state()
        return "unplayed"

    def csv(self, headers=False, **kwargs) -> dict:
        """Returns the model as a dictionary with JSON-compatible keys."""
        include = kwargs.get("include", None)
        str_ = ""
        hdrs, values = zip(*self.model_dump(include=include, by_alias=True).items())
        if headers:
            str_ += ",".join(hdrs) + "\n"
        str_ += ",".join([str(v) for v in values])
        return str_


class MatchOutcome(BaseModel):
    """Match outcome i.e. a completed match with scores and breaks"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    player1_score: int
    player2_score: int
    breaks: list[SnookerBreak] = Field(default_factory=list)

    @computed_field
    def scoreline(self) -> str:
        return f"{self.player1_score}-{self.player2_score}"


class SnookerMatch(MatchFixture, MatchOutcome):
    """Complete snooker match with scores and breaks"""

    @model_validator(mode="after")
    @classmethod
    def breaks_are_by_match_players(cls, data: Any) -> Any:
        """Breaks have to be by one of the match players"""
        for b in data.breaks:
            assert b.player in (data.player1, data.player2), f"Break by {b.player} not in match"
        return data

    @field_serializer("date")
    def _format_date(value) -> str:
        """Formats the date for API response."""
        if isinstance(value, datetime.date):
            return value.strftime("%Y-%m-%d")
        return value

    @computed_field
    def winner(self) -> str:
        """Returns the winner of the match."""
        return self.player1 if self.player1_score > self.player2_score else self.player2

    @computed_field
    def highest_break(self) -> Optional[int]:
        """Returns the highest break"""
        return max((b.points for b in self.breaks), default=None)

    @computed_field
    def highest_break_player(self) -> Optional[SnookerPlayer]:
        """Returns the player with the highest break"""
        return max(self.breaks, key=lambda b: b.points, default=None).player if self.breaks else None

    def _get_state(self) -> str:
        """Determine the state of the snooker match."""
        # if scores are equal, the match is unplayed
        if all([self.player1_score, self.player2_score]):
            return "completed"
        return "unplayed"

    @field_validator("group")
    def valid_group(cls, group):
        """Group must be in the list of valid groups."""
        assert group in {p.group for p in cls._valid_players}, f"Group '{group}' is not a valid group"
        return group

    @model_validator(mode="after")
    def valid_score(self):
        """Scores must conform to match format"""
        frames_to_win = self.format.bestOf // 2 + 1
        if max(self.player1_score, self.player2_score) != frames_to_win:
            raise ValueError(f"Scoreline {self.scoreline} do not match the match format: {self.format}")
        return self

    # @field_validator("players")
    # def lookup_players(cls, values):
    #     """Convert player names to player objects."""
    #     for i, player in enumerate(values):
    #         if isinstance(player, str):
    #             values[i] = next((p for p in cls._valid_players if p.name == player), None)
    #     return values

    @model_validator(mode="after")
    def check_players(self):
        """Asserts for the following conditions:
        * Players match the players in the concerned fixture
        * The asserted `group` matches that of players.
        * Players can not be the same player.
        """
        fixture = next((f for f in self._fixtures if f.f_id == self.f_id), None)
        assert fixture, f"Fixture with ID {self.f_id} not found in fixtures"
        assert self.player1 != self.player2, "Players can not be the same"
        assert self.group == fixture.group, f"Group mismatch: {self.group} != {fixture.group}"
        assert fixture.player1 == self.player1 and fixture.player2 == self.player2, "Players do not match fixture"
        return self

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
            winner_score=self.winner_score,
            loser_score=self.loser_score,
        )

        return f"{summary}"

    @classmethod
    def configure_model(cls, fixtures: list[MatchFixture]):
        """Configure the model with valid players from fixtures."""
        cls._fixtures = fixtures
        cls._valid_players = {p for f in fixtures for p in (f.player1, f.player2)}
        return cls


class SnookerMatchList(BaseModel):
    round: int
    matches: list[SnookerMatch] = Field(default_factory=list)

    @computed_field(alias="matches")
    def completed(self) -> list[SnookerMatch]:
        """Filter for completed matches."""
        return [m for m in self.matches if m.state == "completed"]

    @computed_field(alias="matches")
    def unplayed(self) -> list[SnookerMatch]:
        """Filter for unplayed matches."""
        return [m for m in self.matches if m.state == "unplayed"]
