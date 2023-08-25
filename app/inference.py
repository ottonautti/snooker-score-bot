"""LLM interface."""

import json
import logging
import os
from typing import Literal

from langchain import LLMChain
from langchain.llms import OpenAI, VertexAI
from pydantic import ValidationError

from .models import SnookerMatch, SnookerPlayer, get_model
from .prompts import prompt_template


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    llms = {
        "openai": OpenAI,
        "vertexai": VertexAI,
    }

    def __init__(
        self,
        players: list[SnookerPlayer],
        llm: Literal["openai", "vertexai"] = "openai",
        prompt=prompt_template,
    ):
        self.llm = self.llms[llm]()
        self.prompt = prompt
        self.players = players
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))

    @property
    def player_names(self):
        return [plr.name for plr in self.players]

    @property
    def player_names_and_groups(self):
        """Returns a text represenation of player names and groups."""
        return "\n".join(map(str, self.players))


    def infer_match(self, passage: str) -> SnookerMatch:
        """Extracts scores from input"""
        match_obj = {"passage": passage}
        llm_chain = LLMChain(llm=self.llm, prompt=self.prompt, verbose=self.verbose)
        llm_output = llm_chain.run(existing_players=self.player_names_and_groups, passage=passage)
        try:
            llm_output_json = json.loads(llm_output) or {}
            match_obj.update(llm_output_json)
        except json.JSONDecodeError as e:
            raise ValueError(f"Could not decode JSON: {llm_output}") from e
        try:
            sm = get_model(valid_players=self.players)(**match_obj)
        except ValidationError as e:
            logging.error(f"Could not validate match: {match_obj}")
            raise
        return sm
