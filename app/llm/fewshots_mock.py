"""This module serves two purposes:

1) Example data for LLM few-shot prompting used in production invocations
2) TTD scaffolding for testing LLM prompting
"""

import random
from dataclasses import asdict, dataclass
from typing import Optional

from app.llm.inference import FixtureCollection, SnookerScoresLLM
from app.models import MatchFixture, SnookerBreak, SnookerMatch, SnookerPlayer


def generate_match_id(length: int = 5) -> str:
    """Generate a random ID for the fixture."""
    #                             exclude ambiguous characters
    return "".join(random.choices("abcdefghjkmnpqrstuvwxyz23456789", k=length))


MOCK_PLAYERS = [
    SnookerPlayer(name="Huhtala Katja", group="L1"),
    SnookerPlayer(name="Andersson Leila", group="L1"),
    SnookerPlayer(name="Huuskonen Alexandra", group="L1"),
    SnookerPlayer(name="Suhonen Tanja", group="L1"),
    SnookerPlayer(name="Laaksonen Sinikka", group="L2"),
    SnookerPlayer(name="Tuomi Kari", group="L2"),
    SnookerPlayer(name="Jauhiainen Mari", group="L2"),
    SnookerPlayer(name="Lankinen Elisabet", group="L2"),
    SnookerPlayer(name="Lahti Mika", group="L3"),
    SnookerPlayer(name="Kari Yrjö", group="L3"),
    SnookerPlayer(name="Sjöblom Aukusti", group="L3"),
    SnookerPlayer(name="Kivinen Jarmo", group="L3"),
    SnookerPlayer(name="Tähtinen Anneli", group="L4"),
    SnookerPlayer(name="Saarela Tero", group="L4"),
    SnookerPlayer(name="Pulkkinen Valtteri", group="L4"),
    SnookerPlayer(name="Eskelinen Tapio", group="L4"),
]

FIXTURES = FixtureCollection.from_players(MOCK_PLAYERS)
LLM = SnookerScoresLLM(
    target_model=SnookerMatch,
    fixtures=FIXTURES.fixtures,
)


@dataclass
class InferenceExample:
    _llm = LLM

    passage: str
    match: SnookerMatch

    def fixtures_csv(self) -> str:
        return FIXTURES.as_csv()

    @property
    def llm_expected(self) -> dict:
        """The example JSON output for the LLM is derived from this."""
        f_id = FIXTURES.get_fixture_id_by_players(self.match.players)
        return {
            "f_id": f_id,
            "group": self.match.group,
            "players": self.match.players,
            "scores": self.match.scores,
            "breaks": [SnookerBreak(**brk).model_dump() for brk in self.match.breaks],
        }

    @property
    def expected(self) -> dict:
        """The expected output from the LLM."""
        m = self.match
        return self.llm_expected | {
            "winner": m.winner,
            "loser": m.players[0] if m.players[1] == m.winner else m.players[1],
            "winner_score": m.scores[0] if m.players[0] == m.winner else m.scores[1],
            "loser_score": m.scores[1] if m.players[0] == m.winner else m.scores[0],
        }

    def infer(self) -> SnookerMatch:
        """Run inference based on the passage."""
        # can't include self in examples, that would be cheating.
        apriori_examples = [e for e in EXAMPLES if e != self]
        return self._llm.infer_match(
            passage=self.passage,
            examples=[e.dict() for e in apriori_examples],
        )

    def test(self):
        inferred: SnookerMatch = self.infer()
        assert inferred.f_id == self.expected["f_id"]
        assert inferred.group == self.expected["group"]
        assert inferred.player1 in self.expected["players"]
        assert inferred.player2 in self.expected["players"]
        assert inferred.winner == self.expected["winner"]
        assert inferred.loser == self.expected["loser"]
        assert inferred.winner_score == self.expected["winner_score"]
        assert inferred.loser_score == self.expected["loser_score"]
        assert inferred.breaks == self.expected["breaks"]

    def dict(self):
        """Return dataclass as dictionary"""
        # TODO: clean this structure up
        return {"passage": self.passage} | {"expected": self.llm_expected, "fixtures": self.fixtures_csv()}


EXAMPLES = [
    InferenceExample(
        match=SnookerMatch(
            passage="Aukusti v Yrjö 2-1, breikit Aukusti 25, Yrjö 18",
            group="L3",
            players=("Sjöblom Aukusti", "Kari Yrjö"),
            scores=(2, 1),
            winner="Sjöblom Aukusti",
            breaks=[
                {"player": "Sjöblom Aukusti", "points": 25},
                {"player": "Kari Yrjö", "points": 18},
            ],
        )
    ),
    InferenceExample(
        match=SnookerMatch(
            passage="Huhtala - Andersson 2-0. Breikki 45, Huhtala.",
            group="L1",
            players=("Huhtala Katja", "Andersson Leila"),
            scores=(2, 0),
            winner="Huhtala Katja",
            breaks=[{"player": "Huhtala Katja", "points": 45}],
        )
    ),
    InferenceExample(
        match=SnookerMatch(
            passage="Kari 0 - 2 Sinikka",
            group="L2",
            players=("Laaksonen Sinikka", "Tuomi Kari"),
            scores=(2, 0),
            winner="Laaksonen Sinikka",
            breaks=[],
        )
    ),
    InferenceExample(
        match=SnookerMatch(
            passage="Tähtinen 1 - Tero 2, ei breikkejä",
            group="L4",
            players=("Saarela Tero", "Tähtinen Anneli"),
            scores=(2, 1),
            winner="Tähtinen Anneli",
            breaks=[],
        )
    ),
]


def examples_asdicts() -> list[dict]:
    return [ex.dict() for ex in EXAMPLES]


if __name__ == "__main__":
    for example in EXAMPLES:
        example.test()
