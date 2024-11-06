import datetime
import random
from typing import Any, ClassVar, Literal, Optional, Union

from jinja2 import Template
from pydantic import (
    BaseModel,
    FieldSerializationInfo,
    computed_field,
    field_serializer,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.fields import Field

from .settings import get_settings

SETTINGS = get_settings()


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
    def first_name(self) -> str:
        """Returns the first name if there is one, otherwise returns the full name.

        In the data, names are formatted as "Last First".
        """
        return self.name.split()[-1] if len(self.name.split()) > 1 else self.name


class SnookerBreak(BaseModel):
    player: Union[SnookerPlayer, str] = Field(default_factory=SnookerPlayer)
    points: int = Field(gt=0, le=147)


class MatchFixture(BaseModel):
    """Match fixture i.e. an unplayed match between two players of a group"""

    f_id: Optional[str] = None
    round: Optional[int] = Field(alias="round", default=None)
    group: str
    players: list[Union[SnookerPlayer, str], Union[SnookerPlayer, str]]

    @model_validator(mode="before")
    def convert_players(self):
        """Convert player names to player objects."""
        players = self.get("players", [])
        for i, player in enumerate(players):
            if isinstance(player, str):
                players[i] = SnookerPlayer(name=player, group=self["group"])
        return self

    @field_serializer("players")
    def serialize_players(self, value: Any, info: FieldSerializationInfo) -> str:
        """Returns the player names when serializing the model."""
        return " vs. ".join([p.name for p in value])

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
    scores: tuple[int, int]  # with respect to MatchFixture.players
    breaks: list[SnookerBreak] = Field(default_factory=list)


class SnookerMatch(MatchFixture, MatchOutcome):
    """Complete snooker match with scores and breaks"""

    player1: Union[SnookerPlayer, str]
    player2: Union[SnookerPlayer, str]
    player1_score: int
    player2_score: int

    def __eq_score__(self, value: object) -> bool:
        """The order of players can be reversed, if the scores are also reversed."""
        if isinstance(value, MatchOutcome):
            if self.breaks != value.breaks:
                return False
            elif self.scores == value.scores and self.players == value.players:
                return True
            # if the scores are reversed, the players should also be reversed
            elif self.scores == value.scores[::-1] and self.players == value.players[::-1]:
                return True
        return False

    @model_validator(mode="before")
    @classmethod
    def assign_players_and_scores(cls, data: Any) -> Any:
        """Assign players to player1 and player2."""
        data["player1"] = data["players"][0]
        data["player2"] = data["players"][1]
        data["player1_score"] = data["scores"][0]
        data["player2_score"] = data["scores"][1]
        return data

    @model_validator(mode="after")
    @classmethod
    def lookup_fixture(cls, data: Any) -> Any:
        """If fixture id not explicitly passed, lookup the fixture for the match."""
        if not data.f_id:
            fixture = next((f for f in cls._fixtures if all(p in f.players for p in cls.players)), None)
            assert fixture, f"Fixture not found for players {cls.players}"
            data.f_id = fixture.f_id
        return data

    @model_validator(mode="after")
    @classmethod
    def breaks_are_by_match_players(cls, data: Any) -> Any:
        """Breaks have to be by one of the match players"""
        for b in data.breaks:
            assert b.player in data.players, f"Break by {b.player}, not a player in this match"
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
        if self.scores[0] == self.scores[1]:
            return None
        return self.players[0] if self.scores[0] > self.scores[1] else self.players[1]

    @computed_field
    def winner_score(self) -> int:
        """Returns the winner's score."""
        return self.scores[0] if self.players[0] == self.winner else self.scores[1]

    @computed_field
    def loser_score(self) -> int:
        """Returns the loser's score."""
        return self.scores[0] if self.players[0] == self.loser else self.scores

    @computed_field
    def loser(self) -> str:
        """Returns the winner of the match."""
        if self.scores[0] == self.scores[1]:
            return None
        return self.players[0] if self.scores[0] < self.scores[1] else self.players[1]

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
        if self.scores[0] != self.scores[1]:
            return "completed"
        return "unplayed"

    @field_validator("group")
    def valid_group(cls, group):
        """Group must be in the list of valid groups."""
        assert group in {p.group for p in cls._valid_players}, f"Group '{group}' is not a valid group"
        return group

    @field_validator("scores")
    def valid_score(cls, score):
        """Scores must be between 0 and max_score"""
        assert all(0 <= s <= cls._max_score for s in score), f"Scores must be between 0 and {cls._max_score}"
        return score

    @field_validator("players")
    def lookup_players(cls, values):
        """Convert player names to player objects."""
        for i, player in enumerate(values):
            if isinstance(player, str):
                values[i] = next((p for p in cls._valid_players if p.name == player), None)
        return values

    @model_validator(mode="after")
    def check_players(self):
        """Asserts for the following conditions:
        * Players match the players in the concerned fixture
        * The asserted `group` matches that of players.
        * Players can not be the same player.
        """
        fixture = next((f for f in self._fixtures if f.f_id == self.f_id), None)
        assert fixture, f"Fixture with ID {self.f_id} not found in fixtures"
        assert self.group == fixture.group, f"Group mismatch: {self.group} != {fixture.group}"
        assert all(p in fixture.players for p in self.players), f"Players not in fixture"
        assert self.players[0] != self.players[1], "Players can not be the same"
        return self

    def summary(self, lang="eng") -> str:
        """Returns a string representation of the match."""

        TEMPLATES = {
            "eng": Template(
                #                 """
                # {%- if match.player1_score == match.player2_score -%}
                #     Match between {{ player1 }} and {{ player2 }} ended in a draw at {{ player1_score }} frames each.
                # {%- else -%}
                #     {{ winner }} won {{ loser }} by {{ winner_score }} frames to {{ loser_score }}.
                # {% endif -%} {%- if match.breaks -%}
                #     Breaks: {% for b in match.breaks -%} {{ b.player.first_name }} {{ b.points }} {%- if not
                #     loop.last %}, {% endif %}{%- endfor -%}.
                # {%- endif -%}"""
                """
{{ self.winner }} won {{ loser }} by {{ winner_score }} frames to {{ loser_score }}.
{%- if match.breaks -%}
    Breaks: {% for b in match.breaks -%} {{ b.player.first_name }} {{ b.points }} {%- if not
    loop.last %}, {% endif %}{%- endfor -%}.
{%- endif -%}
"""
            ),
        }

        # Choose the template based language of the original passage
        # summary = TEMPLATES[lang].render(
        #     match=self,
        #     player1=self.player1,
        #     player2=self.player2,
        #     winner=winner,
        #     loser=loser,
        #     winner_score=winner_score,
        #     loser_score=loser_score,
        # )
        summary = TEMPLATES[lang].render(
            match=self,
            winner=self.winner,
            loser=self.loser,
            winner_score=self.winner_score,
            loser_score=self.loser_score,
        )

        sheet_url = SETTINGS.SHEET_SHORTLINK
        link_line = {
            "eng": f"League standings: {sheet_url}",
            "fin": f"Sarjataulukko: {sheet_url}",  # TODO
        }
        return f"{summary}\n{link_line[lang]}"

    @classmethod
    def configure_model(cls, fixtures: list[MatchFixture], max_score: Optional[int] = 2):
        cls._max_score = max_score
        cls._fixtures = fixtures
        cls._valid_players = {player for fixture in fixtures for player in fixture.players}
        return cls


# def get_match_model(valid_players: list[SnookerPlayer], max_score: Optional[int] = 2, **inputs) -> ValidatedMatch:
#     """Returns a version of the model with valid players set at runtime.

#     Inputs are inferred from the passage and should follow:
#     {
#         "group": "L4",
#         "player1": "Paavola Tuomas",
#         "player2": "Marko Ossi",
#         "player1_score": 2,
#         "player2_score": 0,
#         "breaks": [{"player": "Paavola Tuomas", "points": 16}, {"player": "Paavola Tuomas", "points": 22}],
#         "language": "eng",
#     }
#     """

#     # configure the match model given valid players and max score
#     ValidatedMatch.configure_model(valid_players, max_score)

#     breaks = []
#     for b in inputs.get("breaks", []):
#         player = next((player for player in valid_players if player.name == b.get("player")), None)
#         breaks.append(SnookerBreak(player=player, points=b.get("points")))

#     return ValidatedMatch(
#         group=inputs.get("group"),
#         player1=inputs.get("player1"),
#         player2=inputs.get("player2"),
#         player1_score=inputs.get("player1_score"),
#         player2_score=inputs.get("player2_score"),
#         breaks=breaks,
#         passage_language=inputs.get("language"),
#     )


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
