"""Prompt and few-shot example generation."""

import logging

from langchain.prompts.few_shot_with_templates import FewShotPromptWithTemplates
from langchain.prompts.prompt import PromptTemplate

try:
    from . import fewshots_groove
    few_shot_data = fewshots_groove.GrooveFewShotData()
except ImportError:
    logging.warning("Could not import real player names, using fake few-shot data instead.")
    from . import fewshots_mock
    few_shot_data = fewshots_mock.MockFewShotData()



def get_prompt():
    """Generates prompt to LLM containing instruction, few-shot examples and placeholder for user input."""

    prompt_prefix = """The following passage contains the outcome of a snooker match.
    The passage is about a match between two players containing frames won by each player and, optionally, the highest break
    between the two players. Extract said information from the passage in JSON format.

    The passage should only ever contain information pertaining to valid players. Below is a list of full names of
    valid players and their associated groups. Only ever return names of players that are included in the list of
    valid players. Only ever return names as they appear in the list of valid players. Players belong to different
    groups. A match should only ever be between players in the same group. If there is a player with the same name in a
    different group, assume that the player in the passage is the one in the same group as the other player in the match.

    If a break is not explicitly mentioned in the passage, return null values for the `highest_break` and `break_owner`.
    """

    return FewShotPromptWithTemplates(
        examples=few_shot_data.examples,
        example_prompt=PromptTemplate(
            template="Valid players:\n{{ players_blob }}\n\nPassage: {{ passage }}\n\nJSON: {{ output }}\n",
            input_variables=["players_blob", "passage", "output"],
            template_format="jinja2",
        ),
        input_variables=["players_blob", "passage"],
        prefix=PromptTemplate(template=prompt_prefix, input_variables=[], template_format="jinja2"),
        suffix=PromptTemplate(
            template="Valid players:\n{{ players_blob }}\n\nPassage: {{ passage }}\n\nJSON:",
            input_variables=["players_blob", "passage"],
            template_format="jinja2",
        ),
        template_format="jinja2",
    )


if __name__ == "__main__":
    # test prompt generation
    print(get_prompt().format(players_blob="foo", passage="bar"))
