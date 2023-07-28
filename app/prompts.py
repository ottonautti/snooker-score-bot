"""Prompt and few-shot example generation."""

import json
import logging
from functools import partial

from .models import SnookerPlayer
from langchain.prompts.few_shot_with_templates import FewShotPromptWithTemplates
from langchain.prompts.prompt import PromptTemplate

to_json = partial(json.dumps, ensure_ascii=False)
try:
    from .prompts_realnames import few_shot_examples, few_shot_players
except ImportError:
    logging.warning("Could not import prompts_realnames, using fake few-shot data instead.")
    few_shot_players = [
        SnookerPlayer(name="Huhtala Katja", group=1),
        SnookerPlayer(name="Andersson Leila", group=1),
        SnookerPlayer(name="Huuskonen Alexandra", group=1),
        SnookerPlayer(name="Suhonen Tanja", group=1),
        SnookerPlayer(name="Laaksonen Sinikka", group=2),
        SnookerPlayer(name="Tuomi Joonas", group=2),
        SnookerPlayer(name="Jauhiainen Mari", group=2),
        SnookerPlayer(name="Lankinen Elisabet", group=2),
        SnookerPlayer(name="Lahti Mika", group=3),
        SnookerPlayer(name="Väisänen Yrjö", group=3),
        SnookerPlayer(name="Sjöblom Aukusti", group=3),
        SnookerPlayer(name="Kivinen Jarmo", group=3),
        SnookerPlayer(name="Tähtinen Anneli", group=4),
        SnookerPlayer(name="Saarela Tero", group=4),
        SnookerPlayer(name="Pulkkinen Valtteri", group=4),
        SnookerPlayer(name="Eskelinen Tapio", group=4),
    ]

    few_shot_examples = [
        {
            "existing_players": "\n".join([str(plr) for plr in few_shot_players]),
            "passage": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
            "output": to_json(
                {
                    "group": "1",
                    "player1": "Huhtala Katja",
                    "player2": "Andersson Leila",
                    "player1_score": 2,
                    "player2_score": 1,
                    "winner": "Huhtala Katja",
                    "highest_break": 45,
                    "break_owner": "Huhtala Katja",
                }
            ),
        },
        {
            "existing_players": "\n".join([str(plr) for plr in few_shot_players]),
            "passage": "Sinikka - Joonas 2-0",
            "output": to_json(
                {
                    "group": "2",
                    "player1": "Laaksonen Sinikka",
                    "player2": "Tuomi Joonas",
                    "player1_score": 2,
                    "player2_score": 0,
                    "winner": "Laaksonen Sinikka",
                    "highest_break": None,
                    "break_owner": None,
                }
            ),
        },
        {
            "existing_players": "\n".join([str(plr) for plr in few_shot_players]),
            "passage": "Aukusti v Yrjö 2-1 Highest break: Aukusti - 18",
            "output": to_json(
                {
                    "group": "3",
                    "player1": "Sjöblom Aukusti",
                    "player2": "Väisänen Yrjö",
                    "player1_score": 2,
                    "player2_score": 1,
                    "winner": "Sjöblom Aukusti",
                    "highest_break": 18,
                    "break_owner": "Sjöblom Aukusti",
                }
            ),
        },
        {
            "existing_players": "\n".join([str(plr) for plr in few_shot_players]),
            "passage": "Anneli 2 - Tero 1, ei breikkejä",
            "output": to_json(
                {
                    "group": "4",
                    "player1": "Tähtinen Anneli",
                    "player2": "Saarela Tero",
                    "player1_score": 2,
                    "player2_score": 1,
                    "winner": "Tähtinen Anneli",
                    "highest_break": None,
                    "break_owner": None,
                }
            ),
        },
    ]


prompt_prefix = """The following passage contains the outcome of a snooker match.
The passage is about a match between two players containing frames won by each player and, optionally, the highest break
between the two players. Extract said information from the passage in JSON format.

The passage should only ever contain information pertaining to existing players. Below is a list of full names of
existing players and their associated groups. Only ever return names of players that are included in the list of
existing players. Only ever return names as they appear in the list of existing players. Players belong to different
groups. A match should only ever be between players in the same group.

If a break is not explicitly mentioned in the passage, return null values for the `highest_break` and `break_owner`.
"""

prompt_template = FewShotPromptWithTemplates(
    examples=few_shot_examples,
    example_prompt=PromptTemplate(
        template="Existing players:\n{{ existing_players }}\n\nPassage: {{ passage }}\n\nJSON: {{ output }}\n",
        input_variables=["existing_players", "passage", "output"],
        template_format="jinja2",
    ),
    input_variables=["existing_players", "passage"],
    prefix=PromptTemplate(template=prompt_prefix, input_variables=[], template_format="jinja2"),
    suffix=PromptTemplate(
        template="Existing players:\n{{ existing_players }}\n\nPassage: {{ passage }}\n\nJSON:",
        input_variables=["existing_players", "passage"],
        template_format="jinja2",
    ),
    template_format="jinja2",
)

if __name__ == "__main__":
    # test prompt generation
    print(prompt_template.format(existing_players="foo", passage="bar"))
