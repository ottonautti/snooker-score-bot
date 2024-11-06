import json
from dataclasses import asdict, dataclass
from itertools import combinations
from typing import Optional, Union

from app.llm.inference import SnookerScoresLLM
from app.models import MatchFixture, SnookerPlayer

LLM = SnookerScoresLLM(llm="vertexai")


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


class FixtureCollection:
    def __init__(self, players):
        self.players = players
        self.fixtures = self.make_fixtures()

    def make_fixtures(self) -> list[MatchFixture]:
        groups = {plr.group for plr in self.players}
        fixtures = []

        for group in groups:
            for p1, p2 in combinations([plr for plr in MOCK_PLAYERS if plr.group == group], 2):
                fixtures.append(MatchFixture(group=group, player1=p1.name, player2=p2.name))

        return fixtures

    def get_fixture_id_by_players(self, *players: Union[str, list[str]]) -> Optional[str]:
        if len(players) == 1 and isinstance(players[0], (list, tuple)):
            players = players[0]
        for fixture in self.fixtures:
            if fixture.player1 in players and fixture.player2 in players:
                return fixture.id_
        return None


FIXTURES = FixtureCollection(MOCK_PLAYERS)


@dataclass
class InferenceExample:
    _llm = LLM

    passage: str

    player1: str
    player2: str
    group: str
    player1_score: int
    player2_score: int
    winner: str
    breaks: list[dict]

    expected: dict = None

    def __post_init__(self):
        self.expected = {
            "id": FIXTURES.get_fixture_id_by_players([self.player1, self.player2]),
            "group": self.group,
            "player1": self.player1,
            "player2": self.player2,
            "player1_score": self.player1_score,
            "player2_score": self.player2_score,
            "winner": self.winner,
            "breaks": self.breaks,
        }

    def infer(self):
        apriori_examples = [ex for ex in EXAMPLES if ex != self]
        return self._llm.infer(
            passage=self.passage,
            fixtures=json.dumps(FIXTURES.fixtures, default=lambda x: x.__dict__, ensure_ascii=False),
            examples=[ex.dict() for ex in apriori_examples],
        )

    def test(self):
        output = self.infer()
        # the expected keys and values are present (at least)
        assert all(output[k] == v for k, v in self.expected.items())

    def dict(self):
        """Return dataclass as dictionary, icnluding `fixtures` and `expected` attribute"""
        return asdict(self) | {"fixtures": FIXTURES.fixtures}


EXAMPLES = [
    InferenceExample(
        passage="Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
        player1="Huhtala Katja",
        player2="Andersson Leila",
        group="L1",
        player1_score=2,
        player2_score=1,
        winner="Huhtala Katja",
        breaks=[{"player": "Huhtala Katja", "points": 45}],
    ),
    InferenceExample(
        passage="Sinikka - Joonas 2-0",
        player1="Laaksonen Sinikka",
        player2="Tuomi Kari",
        group="L2",
        player1_score=2,
        player2_score=0,
        winner="Laaksonen Sinikka",
        breaks=[],
    ),
    InferenceExample(
        passage="Valtteri v Anneli 2-1, breaks: Anneli 107, 101, Valtteri 52",
        player1="Pulkkinen Valtteri",
        player2="Tähtinen Anneli",
        group="L4",
        player1_score=2,
        player2_score=1,
        winner="Pulkkinen Valtteri",
        breaks=[
            {"player": "Tähtinen Anneli", "points": 107},
            {"player": "Tähtinen Anneli", "points": 101},
            {"player": "Pulkkinen Valtteri", "points": 52},
        ],
    ),
    InferenceExample(
        passage="Aukusti v Yrjö 2-1, breikit Aukusti 25, Yrjö 18",
        player1="Sjöblom Aukusti",
        player2="Kari Yrjö",
        group="L3",
        player1_score=2,
        player2_score=1,
        winner="Sjöblom Aukusti",
        breaks=[
            {"player": "Sjöblom Aukusti", "points": 25},
            {"player": "Kari Yrjö", "points": 18},
        ],
    ),
    InferenceExample(
        passage="Tähtinen 2 - Tero 1, ei breikkejä",
        player1="Tähtinen Anneli",
        player2="Saarela Tero",
        group="L4",
        player1_score=2,
        player2_score=1,
        winner="Tähtinen Anneli",
        breaks=[],
    ),
]


if __name__ == "__main__":
    for example in EXAMPLES:
        example.test()
