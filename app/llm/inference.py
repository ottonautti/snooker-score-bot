"""LLM interface."""

import json
import os
from typing import Literal

from langchain import LLMChain
from langchain.llms import OpenAI, VertexAI

from ..models import SnookerPlayer
from . import prompts


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    llms = {
        "openai": OpenAI,
        "vertexai": VertexAI,
    }

    def __init__(
        self,
        players: list[SnookerPlayer],  # list of valid players
        llm: Literal["openai", "vertexai"] = "openai",
        prompt=None,
    ):
        self.llm = self.llms[llm]()
        self.players = players
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))
        if not prompt:
            prompt = prompts.get_prompt()
        self.prompt = prompt

    @property
    def player_names_and_groups(self):
        """Returns a text represenation of player names and groups."""
        return "\n".join(map(str, self.players))

    def run(self, passage: str) -> dict:
        llm_chain = LLMChain(llm=self.llm, prompt=self.prompt, verbose=self.verbose)
        llm_output_raw = llm_chain.run(valid_players=self.player_names_and_groups, passage=passage)
        try:
            llm_output = json.loads(llm_output_raw) or {}
            output = {"passage": passage, **llm_output}
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM did not output valid JSON: {llm_output_raw}") from e
        return output
