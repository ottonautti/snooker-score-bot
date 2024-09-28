import datetime
from typing import ClassVar, Literal, Optional, Union

from jinja2 import Template
from pydantic import (
    BaseModel,
    computed_field,
    field_validator,
    model_serializer,
    model_validator,
)
from pydantic.fields import Field

from .settings import get_settings

settings = get_settings(sixred24=False)  # TODO: DRY


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


class SnookerBreak(BaseModel):
    """Snooker break"""

    player: SnookerPlayer = Field(default_factory=SnookerPlayer)
    points: int = Field(gt=0, le=147)


class MatchOutcome(BaseModel):
    """Base match class with common attributes"""

    date: Optional[datetime.date] = Field(default_factory=datetime.date.today)
    group: str
    player1: Union[SnookerPlayer, str]
    player2: Union[SnookerPlayer, str]
    player1_score: Optional[int] = Field(default=None)
    player2_score: Optional[int] = Field(default=None)
    breaks: list[SnookerBreak] = Field(default_factory=list)

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

    @model_validator(mode="after")
    def breaks_are_by_match_players(self):
        """Breaks have to be by one of the match players"""
        for b in self.breaks:
            assert b.player in [
                self.player1,
                self.player2,
            ], f"{b.player} is not a player in this match"
        return self


class SnookerMatch(MatchOutcome):
    """Snooker match with additional validators for LLM-inferred data."""

    # model configuration at runtime
    valid_players: ClassVar[list[SnookerPlayer]]
    max_score: ClassVar[int] = 2

    passage_language: Optional[Literal["fin", "eng"]] = "fin"

    @field_validator("player1_score", "player2_score")
    def valid_score(cls, score):
        """Scores must be between 0 and max_score"""
        assert score >= 0, "score must be greater than or equal to 0"
        assert score <= cls.max_score, f"score must be less than or equal to {cls.max_score}"
        return score

    @field_validator("player1", "player2")
    def lookup_players(cls, player):
        """
        Convert player names to player objects.

        Args:
            player (str or SnookerPlayer): The player name or object.

        Returns:
            SnookerPlayer: The matched player object.

        Raises:
            ValueError: If the player name is not found in valid players.
        """
        if isinstance(player, str):
            matched_player = next((p for p in cls.valid_players if p.name == player), None)
            if matched_player is None:
                raise ValueError(f"Player '{player}' not found in valid players.")
            return matched_player
        return player

    @model_validator(mode="after")
    def check_players(self):
        """Asserts for the following conditions:
        * Players belong to valid players.
        * The asserted `group` matches that of players.
        * Players can not be the same player.
        """

        # Check that both players are in the list of valid players
        assert self.player1 in self.valid_players, f"Player '{self.player1}' is not a valid player"
        assert self.player2 in self.valid_players, f"Player '{self.player2}' is not a valid player"

        # Check that the group of the match is the same as the group of the players
        assert self.group == self.player1.group, f"Player '{self.player1}' is not in group {self.group}"
        assert self.group == self.player2.group, f"Player '{self.player2}' is not in group {self.group}"
        assert self.player1.group == self.player2.group

        # Check that the two players are not the same
        assert self.player1 != self.player2, "Players cannot be the same player"

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
    def configure_model(cls, valid_players: list[SnookerPlayer], max_score: Optional[int] = 2):
        cls.valid_players = valid_players
        cls.max_score = max_score


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
    SnookerMatch.configure_model(valid_players, max_score)

    breaks = []
    for b in inputs.get("breaks", []):
        player = next((player for player in valid_players if player.name == b.get("player")), None)
        breaks.append(SnookerBreak(player=player, points=b.get("points")))

    return SnookerMatch(
        group=inputs.get("group"),
        player1=inputs.get("player1"),
        player2=inputs.get("player2"),
        player1_score=inputs.get("player1_score"),
        player2_score=inputs.get("player2_score"),
        breaks=breaks,
        passage_language=inputs.get("language"),
    )
