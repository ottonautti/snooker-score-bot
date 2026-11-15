"""Prompt with instructions and few-shot examples."""

from .fewshots_mock import MockFewShotData

few_shot_data = MockFewShotData()

INSTRUCTIONS = """\
The passage is a text message reporting the result of a snooker match between two players: the frames each
player won and, optionally, breaks. After the instructions comes the list of valid players as "group: full name"
(full names are "Surname Firstname").

Find the two people the passage mentions and, for each of them, list in "options" the players in the list that the
mention refers to, using names EXACTLY as they appear in the list. People refer to players by surname, first name,
both, an initial ("Jarmo K"), a nickname or short form (e.g. "Valtsu" for Valtteri), with typos, and with Finnish
inflections ("Neuvosen", "Yrjölle").

Be precise. Include a player only if the mention really is a way of writing that player's name: a different name
that merely looks similar is a different player ("Lahti" is not "Laine"), and an initial must match. If the mention
identifies one player (a full name, a surname only one player has, a name plus initial), list only that one. If it
fits several players equally (e.g. a first name several players share), list all of them and don't choose. If
nobody in the list fits, give an empty list.

"players" has the two people in the order the passage mentions them. A scoreline such as "2-0" gives the frames in
that same order: player1_score is the first person's, player2_score the second's. Breaks the passage mentions go in
"breaks", each with "player": 1 or 2 (which of the two people made it) and "points".
"""


def build_prompt(players_list: str, passage: str) -> str:
    """Instructions, examples (all using one example player list) and the passage to read."""
    examples = "\n\n".join(f"Passage: {e['passage']}\nJSON: {e['output']}" for e in few_shot_data.examples)
    return (
        f"{INSTRUCTIONS}\n"
        f"EXAMPLES\n\nValid players:\n{few_shot_data.players_list}\n\n{examples}\n\n"
        f"YOUR TASK\n\nValid players:\n{players_list}\n\nPassage: {passage}\nJSON:"
    )


if __name__ == "__main__":
    print(build_prompt(players_list="L1: Doe John\nL1: Roe Jane", passage="John - Jane 2-0"))
