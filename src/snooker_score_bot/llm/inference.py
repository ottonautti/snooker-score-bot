"""LLM interface."""

import json
import logging
import os

from langchain.callbacks import StdOutCallbackHandler
from langchain.chains.llm import LLMChain
from langchain_core.language_models.llms import BaseLLM

from snooker_score_bot.models import InferredMatch, SnookerPlayer
from snooker_score_bot.settings import Settings

from . import prompts

logging.basicConfig(level=logging.INFO)

stdout_handler = StdOutCallbackHandler()


class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    def __init__(self, llm: BaseLLM = None, model_name=None, prompt=None):
        """Initialize the LLM client."""
        if not issubclass(llm, BaseLLM):
            raise TypeError(f"Expected llm to be a BaseLLM instance, got {type(llm)}")
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


def get_llm_client(settings: Settings) -> SnookerScoresLLM:
    """Get the LLM client based on the settings."""
    return SnookerScoresLLM(llm=settings.LLM_PROVIDER, model_name=settings.LLM_MODEL)
