"""LLM interface."""

import json
import logging
import os
from typing import Literal

from langchain.callbacks import StdOutCallbackHandler
from langchain.chains.llm import LLMChain
from langchain.prompts.few_shot_with_templates import FewShotPromptWithTemplates
from langchain.prompts.prompt import PromptTemplate
from langchain_google_vertexai.llms import VertexAI

logging.basicConfig(level=logging.INFO)

stdout_handler = StdOutCallbackHandler()

VERTEX_AI = VertexAI()

class SnookerScoresLLM:
    """LLM client for extracting snooker scores from messages"""

    def __init__(
        self,
    ):
        self.llm = VERTEX_AI
        self.verbose = bool(os.getenv("LANGCHAIN_VERBOSE", False))

    def infer(self, passage: str, fixtures: str, examples) -> dict:
        chain = LLMChain(
            llm=self.llm,
            prompt=self.get_prompt(examples),
            verbose=self.verbose,
            callbacks=[stdout_handler],
        )
        output = chain.invoke({"passage": passage, "fixtures": fixtures})
        try:
            logging.info(f"{self.llm.__class__.__name__} output: {output['text']}")
            deserialized = json.loads(output["text"])
        except KeyError as e:
            raise RuntimeError(f"Unexpected output from LLM: {output}") from e
        return deserialized

    def get_prompt(self, examples):
        """Generates prompt to LLM containing instruction, few-shot examples and placeholder for user input."""

        prompt_prefix = """
        The following passage contains the outcome of a snooker match. The passage is about a match between two players
        containing frames won by each player and, optionally, any notable breaks.

        The passage should only ever contain information pertaining to possible match fixtures, which are listed below for
        each group. Return names EXACTLY as they appear in the list of valid match fixtures including order of last and
        first name.

        If a break is not explicitly mentioned in the passage, return an empty list for breaks.
        """

        return FewShotPromptWithTemplates(
            examples=examples,
            example_prompt=PromptTemplate(
                template="Possible match fixtures:\n{{ fixtures }}\n\nPassage: {{ passage }}\n\nJSON: {{ expected | tojson }}\n",
                input_variables=["fixtures", "passage", "expected"],
                template_format="jinja2",
            ),
            input_variables=["fixtures", "passage"],
            prefix=PromptTemplate(template=prompt_prefix, input_variables=[], template_format="jinja2"),
            suffix=PromptTemplate(
                template="Possible match fixtures:\n{{ fixtures }}\n\nPassage: {{ passage }}\n\nJSON:",
                input_variables=["fixtures", "passage"],
                template_format="jinja2",
            ),
            template_format="jinja2",
        )
