import datetime
from typing import ClassVar, Literal, Optional, Union

from jinja2 import Template
from pydantic import (
    BaseModel,
    computed_field,
    create_model,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.fields import Field

from .settings import settings


class SnookerPlayer(BaseModel):
    name: str
    group: str

    def __repr__(self):
        return f"SnookerPlayer(name={self.name}, group={self.group})"

    def __str__(self):
        return self.name

    @model_serializer
    def serialize_as_name(self):
        """Returns only the name when serializing the model"""
        return self.name

    @property
    def first_name(self) -> str:
        """Returns the first name if there is one, otherwise returns the full name.

        In the data, names are formatted as "Last First".
        """
        return self.name.split()[-1] if len(self.name.split()) > 1 else self.name

    @property
    def _gn(self) -> str:
        """Returns the group and name in the format "Group: Name".

        This is used in LLM prompts."""
        return f"{self.group}: {self.name}"


class SnookerBreak(BaseModel):
    """Snooker break"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    player: SnookerPlayer = Field(default_factory=SnookerPlayer)
    points: int = Field(gt=0, le=147)


class SnookerMatch(BaseModel):
    """Snooker match"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    group: str
    player1: SnookerPlayer
    player2: SnookerPlayer
    player1_score: int
    player2_score: int
    breaks: list[SnookerBreak] = Field(default_factory=list)

    # model configuration at runtime
    valid_players: ClassVar[list[SnookerPlayer]]
    max_score: ClassVar[int] = 2

    passage_language: Optional[Literal["fin", "eng"]] = "fin"

    @computed_field
    def winner(self) -> str:
        if self.player1_score == self.player2_score:
            return None
        if self.player1_score > self.player2_score:
            return self.player1
        return self.player2

    @computed_field
    def highest_break(self) -> Optional[int]:
        """Returns the highest break"""
        return max((b.points for b in self.breaks), default=None)

    @computed_field
    def highest_break_player(self) -> Optional[SnookerPlayer]:
        """Returns the player with the highest break"""
        return max(self.breaks, key=lambda b: b.points, default=None).player if self.breaks else None

    @field_validator("player1_score", "player2_score")
    def valid_score(cls, score):
        """Scores must be between 0 and max_score"""
        assert score >= 0, "score must be greater than or equal to 0"
        assert score <= cls.max_score, f"score must be less than or equal to {cls.max_score}"
        return score

    @model_validator(mode="after")
    def check_players(self):
        """Players have to belong to valid players. Players have to be from the same group. Players can not be the same player."""

        # Check that both players are in the list of valid players
        assert self.player1 in self.valid_players, f"{self.player1} is not a valid player"
        assert self.player2 in self.valid_players, f"{self.player2} is not a valid player"

        # Check that both players are from the same group
        assert self.player1.group == self.player2.group, "Players are not from the same group"

        # Check that the two players are not the same
        assert self.player1 != self.player2, "Players cannot be the same player"

        return self

    @model_validator(mode="after")
    def breaks_are_by_match_players(self):
        """Breaks have to be by one of the match players"""
        for b in self.breaks:
            assert b.player in [self.player1, self.player2], f"{b.player} is not a player in this match"
        return self

    def summary(self, lang="fin") -> str:
        """Returns a string representation of the match."""

        winner = self.winner
        loser = self.player1 if self.player1_score < self.player2_score else self.player2
        winner_score = self.player1_score if self.player1_score > self.player2_score else self.player2_score
        loser_score = self.player1_score if self.player1_score < self.player2_score else self.player2_score

        TEMPLATES = {
            "eng": Template(
                """
{%- if match.player1_score == match.player2_score -%}
    Match between {{ player1 }} and {{ player2 }} ended in a draw at {{ player1_score }} frames each.
{%- else -%}
    {{ winner }} won {{ loser }} by {{ winner_score }} frames to {{ loser_score }}.
{% endif -%} {%- if match.breaks -%}
    Breaks: {% for b in match.breaks -%} {{ b.player.first_name }} {{ b.points }} {%- if not
    loop.last %}, {% endif %}{%- endfor -%}.
{%- endif -%}"""
            ),
            "fin": Template(
                """
{%- if match.player1_score == match.player2_score -%}
    {{ player1 }} ja {{ player2 }} pelasivat tasan {{ player1_score }}-{{ player2_score }}.
{%- else -%}
    {{ winner }} voitti vastustajan {{ loser }} {{ winner_score }}-{{ loser_score }}.
{% endif -%} {%- if match.breaks -%}
    Breikit: {% for b in match.breaks -%} {{ b.player.first_name }} {{ b.points }} {%- if not
    loop.last %}, {% endif %}{%- endfor -%}.
{%- endif -%}"""
            ),
        }

        # Choose the template based language of the original passage
        summary = TEMPLATES[lang].render(
            match=self,
            player1=self.player1,
            player2=self.player2,
            winner=winner,
            loser=loser,
            winner_score=winner_score,
            loser_score=loser_score,
        )

        sheet_url = settings.SHEET_SHORTLINK
        link_line = {
            "eng": f"League standings: {sheet_url}",
            "fin": f"Sarjataulukko: {sheet_url}",
        }
        return f"{summary}\n{link_line[lang]}"

    @classmethod
    def configure_model(cls, valid_players: list[SnookerPlayer], max_score: Optional[int] = 2) -> "SnookerMatch":
        """Returns a version of the model with valid players set at runtime."""
        return create_model(
            cls.__name__,
            __base__=cls,
            valid_players=valid_players,
            max_score=max_score,
        )


def get_match_model(valid_players: list[SnookerPlayer], max_score: Optional[int] = 2, **inputs) -> "SnookerMatch":
    """Returns a version of the model with valid players set at runtime.

    Inputs are inferred from the passage and should follow:
    {
        "group": "L4",
        "player1": "Paavola Tuomas",
        "player2": "Marko Ossi",
        "player1_score": 2,
        "player2_score": 0,
        "breaks": [{"player": "Paavola Tuomas", "points": 16}, {"player": "Paavola Tuomas", "points": 22}],
        "language": "eng",
    }
    """

    # configure the match model given valid players and max score
    match_model = SnookerMatch.configure_model(
        valid_players=valid_players,
        max_score=max_score,
    )

    # compose the players, breaks and finally the match from the inputs
    player1 = next((player for player in valid_players if player.name == inputs.get("player1")), None)
    player2 = next((player for player in valid_players if player.name == inputs.get("player2")), None)
    breaks = []
    for b in inputs.get("breaks", []):
        player = next((player for player in valid_players if player.name == b.get("player")), None)
        breaks.append(SnookerBreak(player=player, points=b.get("points")))
    return match_model(
        group=inputs.get("group"),
        player1=player1,
        player2=player2,
        player1_score=inputs.get("player1_score"),
        player2_score=inputs.get("player2_score"),
        breaks=breaks,
        passage_language=inputs.get("language"),
    )
