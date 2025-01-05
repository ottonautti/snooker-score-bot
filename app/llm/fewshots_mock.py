import json
from functools import partial

from ..models import SnookerPlayer
from . import FewShotData

to_json = partial(json.dumps, ensure_ascii=False)


class MockFewShotData(FewShotData):
    players = [
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

    @property
    def examples(self):
        return [
            {
                "valid_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
                "output": to_json(
                    {
                        "group": "L1",
                        "player1": "Huhtala Katja",
                        "player2": "Andersson Leila",
                        "player1_score": 2,
                        "player2_score": 1,
                        "winner": "Huhtala Katja",
                        "breaks": [
                            {
                                "player": "Huhtala Katja",
                                "points": 45,
                            }
                        ],
                        "language": "fin"
                    }
                ),
            },
            {
                "valid_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Sinikka - Joonas 2-0",
                "output": to_json(
                    {
                        "group": "L2",
                        "player1": "Laaksonen Sinikka",
                        "player2": "Tuomi Joonas",
                        "player1_score": 2,
                        "player2_score": 0,
                        "winner": "Laaksonen Sinikka",
                        "breaks": [],
                        "language": "fin"
                    }
                ),
            },
            {
                "valid_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Valtteri v Anneli 2-1, breaks: Anneli 107, 101, Valtteri 52",
                "output": to_json(
                    {
                        "group": "L4",
                        "player1": "Pulkkinen Valtteri",
                        "player2": "Tähtinen Anneli",
                        "player1_score": 2,
                        "player2_score": 1,
                        "winner": "Pulkkinen Valtteri",
                        "breaks": [
                            {
                                "player": "Tähtinen Anneli",
                                "points": 107,
                            },
                            {
                                "player": "Tähtinen Anneli",
                                "points": 101,
                            },
                            {
                                "player": "Pulkkinen Valtteri",
                                "points": 52,
                            },
                        ],
                        "language": "eng"
                    }
                ),
            },
            {
                "valid_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Aukusti v Yrjö 2-1, breikit Aukusti 25, Yrjö 18",
                "output": to_json(
                    {
                        "group": "L3",
                        "player1": "Sjöblom Aukusti",
                        "player2": "Väisänen Yrjö",
                        "player1_score": 2,
                        "player2_score": 1,
                        "winner": "Sjöblom Aukusti",
                        "breaks": [
                            {
                                "player": "Sjöblom Aukusti",
                                "points": 25,
                            },
                            {
                                "player": "Väisänen Yrjö",
                                "points": 18,
                            },
                        ],
                        "language": "fin"
                    }
                ),
            },
            {
                "valid_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Ahonen 2 - Tero 1, ei breikkejä",
                "output": to_json(
                    {
                        "group": "L4",
                        "player1": "Tähtinen Anneli",
                        "player2": "Saarela Tero",
                        "player1_score": 2,
                        "player2_score": 1,
                        "winner": "Tähtinen Anneli",
                        "breaks": [],
                        "language": "fin"
                    }
                ),
            },
        ]
