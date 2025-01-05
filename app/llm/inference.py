"""LLM interface."""

import json
import logging
import os
from typing import Literal

from langchain.callbacks import StdOutCallbackHandler
from langchain.chains.llm import LLMChain
from langchain_google_vertexai import VertexAI

from . import prompts

logging.basicConfig(level=logging.INFO)

stdout_handler = StdOutCallbackHandler()


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    llms = {
        "vertexai": VertexAI,
    }

    def __init__(
        self,
        llm = "vertexai",
        model_name=None,
        prompt=None,
    ):
        if model_name is None:
            self.llm = self.llms[llm]()
        else:
            self.llm = self.llms[llm](model_name=model_name)
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))
        if not prompt:
            prompt = prompts.get_prompt()
        self.prompt = prompt

    def infer(self, passage: str, valid_players_txt: str) -> dict:
        chain = LLMChain(llm=self.llm, prompt=self.prompt, verbose=self.verbose, callbacks=[stdout_handler])
        output = chain.invoke(
            {
                "passage": passage,
                "players_list": valid_players_txt,
            }
        )
        try:
            logging.info(f"{self.llm.__class__.__name__} output: {output['text']}")
            deserialized = json.loads(output["text"])
        except KeyError as e:
            raise RuntimeError(f"Unexpected output from LLM: {output}") from e
        return deserialized
