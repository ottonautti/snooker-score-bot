"""LLM interface."""

import json
import logging
import os

from langchain.callbacks import StdOutCallbackHandler
from langchain.chains.llm import LLMChain
from langchain_google_vertexai import VertexAI
from pydantic import BaseModel
from app.models import SnookerPlayer, InferredMatch

from . import prompts

logging.basicConfig(level=logging.INFO)

stdout_handler = StdOutCallbackHandler()


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    def __init__(
        self,
        llm=VertexAI,  # default to VertexAI (Google)
        model_name=None,
        prompt=None,
    ):
        self.llm = llm(model_name=model_name)
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))
        if not prompt:
            prompt = prompts.get_prompt()
        self.prompt = prompt

    def infer(self, passage: str, known_players: list[SnookerPlayer]) -> InferredMatch:
        """Infer snooker scores from a passage of text and a list of known players."""
        logging.info(f"Calling LLM with passage: {passage}")
        known_players_txt = "\n".join([plr.__llm_str__() for plr in known_players])
        chain = LLMChain(llm=self.llm, prompt=self.prompt, verbose=self.verbose, callbacks=[stdout_handler])
        output = chain.invoke(
            {
                "passage": passage,
                "players_list": known_players_txt,
            }
        )
        try:
            text = output["text"]
            logging.info(f"{self.llm.__class__.__name__} output: {text}")
            # FIXME: Use JsonOutputParser instead of this hack
            text = text.replace("```json", "").replace("```", "")
            match = InferredMatch(**json.loads(text))
        except KeyError as e:
            raise RuntimeError(f"Unexpected output from LLM: {output}") from e
        return match
