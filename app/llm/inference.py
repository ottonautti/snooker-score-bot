"""LLM interface."""

import json
import logging
import os
import textwrap
from itertools import combinations
from typing import Literal, Optional, Union

from langchain.callbacks import StdOutCallbackHandler
from langchain.chains.llm import LLMChain
from langchain.prompts.few_shot_with_templates import FewShotPromptWithTemplates
from langchain.prompts.prompt import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_vertexai.llms import VertexAI
from pydantic import BaseModel
import random
from app.models import MatchFixture, SnookerMatch, SnookerPlayer

logging.basicConfig(level=logging.INFO)

stdout_handler = StdOutCallbackHandler()

VERTEX_AI = VertexAI()


def generate_fixture_id(length: int = 5) -> str:
    """Generate a random ID for the fixture."""
    #                             exclude ambiguous characters
    return "".join(random.choices("abcdefghjkmnpqrstuvwxyz23456789", k=length))


class FixtureCollection:
    def __init__(self, fixtures: list[MatchFixture]):
        self.fixtures = fixtures

    @property
    def players(self) -> set[str]:
        return {plr for fixture in self.fixtures for plr in fixture.players}

    @classmethod
    def from_players(cls, players: list[SnookerPlayer]) -> "FixtureCollection":
        groups = {plr.group for plr in players}
        fixtures = []

        for group in groups:
            for p1, p2 in combinations([plr for plr in players if plr.group == group], 2):
                fixtures.append(
                    MatchFixture(
                        f_id=generate_fixture_id(),
                        group=group,
                        players=(p1, p2),
                    )
                )

        return FixtureCollection(fixtures)

    def get_fixture_id_by_players(self, *players: Union[str, list[str]]) -> Optional[str]:
        if len(players) == 1 and isinstance(players[0], (list, tuple)):
            players = players[0]
        for fixture in self.fixtures:
            if all(plr in fixture.players for plr in players):
                return fixture.f_id
        return None

    def as_csv(self) -> str:
        """Return all fixtures as CSV"""

        def csv_generator():
            first_pass = True
            for fixture in self.fixtures:
                csv_line = fixture.csv(headers=first_pass, include=("f_id", "group", "players"))
                yield csv_line
                first_pass = False

        return "\n".join(csv_generator())


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    def __init__(self, target_model, fixtures: list[MatchFixture]):
        self.llm = VERTEX_AI
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))
        self.model: SnookerMatch = target_model.configure_model(fixtures=fixtures)
        self._fixture_coll = FixtureCollection(fixtures)

    def run(self, passage: str, examples) -> dict:
        chain = LLMChain(
            llm=self.llm,
            prompt=self._get_prompt(examples),
            verbose=self.verbose,
            callbacks=[stdout_handler],
            output_parser=JsonOutputParser(pydantic_object=SnookerMatch),
        )
        fixtures_csv = self._fixture_coll.as_csv()
        output = chain.invoke({"passage": passage, "fixtures": fixtures_csv})
        try:
            logging.info(f"{self.llm.__class__.__name__} output: {output['text']}")
            out_object = output["text"]
        except KeyError as e:
            raise RuntimeError(f"Unexpected output from LLM: {output}") from e
        return out_object

    def infer_match(self, passage: str, examples) -> SnookerMatch:
        """Infer match outcome from passage"""
        output = self.run(passage, examples=examples)
        # match player order with fixture player order
        match = self.model(**output)
        if not match.f_id:
            fixture_lookup = self._fixture_coll.get_fixture_id_by_players(match.player1, match.player2)
            if not fixture_lookup:
                raise ValueError(f"Could not find fixture for players: {match.player1}, {match.player2}")
            match.f_id = fixture_lookup.f_id
        return match

    # TODO: store examples in class attribute or static method?
    def _get_prompt(self, examples):
        """Generates prompt to LLM containing instruction, few-shot examples and placeholder for user input."""

        # fmt: off
        prompt_prefix = textwrap.dedent("""\
            The following passage contains the
            outcome of a snooker match. The passage is about a match between two players containing
            frames won by each player and, optionally, any notable breaks by said players.

            The passage should only ever contain information pertaining to one of the rows in the
            table of possible match fixtures, which precedes the passage. Each row in the fixtures
            table represents a valid match fixture between two players. The names in the passage
            determine the appropriate `f_id`. Value of `players` in the output should exactly match
            the player names in the matched fixture row. Order of `scores` should match the order of
            `players`, ie. `scores[0]` should correspond to `players[0]`.

            Breaks are always made by match players. In other words, player names in breaks must
            always match either player1 or player2. If a break is not explicitly mentioned in the
            passage, return an empty list for breaks.
            """)

        example_header = textwrap.dedent("""\
            === EXAMPLES ===
            Possible match fixtures (common for all examples)
            {{ example_fixtures }}
            """)
        # fmt: on

        return FewShotPromptWithTemplates(
            examples=examples,
            example_prompt=PromptTemplate(
                template="Passage: {{ passage }}\nJSON: {{ expected | tojson }}\n",
                input_variables=["fixtures", "passage", "expected"],
                template_format="jinja2",
            ),
            input_variables=["fixtures", "passage"],
            # these are common for all examples, only including once to save tokens
            partial_variables={"example_fixtures": examples[0].get("fixtures")},
            prefix=PromptTemplate(
                template=prompt_prefix + example_header,
                input_variables=["example_fixtures"],
                template_format="jinja2",
            ),
            suffix=PromptTemplate(
                template=str(
                    "=== END OF EXAMPLES ===\n\n"
                    "Possible match fixtures:\n{{ fixtures }}\n\nPassage: {{ passage }}\nJSON:",
                ),
                input_variables=["example_fixture", "fixtures", "passage"],
                template_format="jinja2",
            ),
            template_format="jinja2",
        )
