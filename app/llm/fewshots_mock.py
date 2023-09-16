import json
from functools import partial

from . import FewShotData
from ..models import SnookerPlayer

to_json = partial(json.dumps, ensure_ascii=False)


class MockFewShotData(FewShotData):
    players = [
        SnookerPlayer("Huhtala Katja", "L1"),
        SnookerPlayer("Andersson Leila", "L1"),
        SnookerPlayer("Huuskonen Alexandra", "L1"),
        SnookerPlayer("Suhonen Tanja", "L1"),
        SnookerPlayer("Laaksonen Sinikka", "L2"),
        SnookerPlayer("Tuomi Kari", "L2"),
        SnookerPlayer("Jauhiainen Mari", "L2"),
        SnookerPlayer("Lankinen Elisabet", "L2"),
        SnookerPlayer("Lahti Mika", "L3"),
        SnookerPlayer("Kari Yrjö", "L3"),
        SnookerPlayer("Sjöblom Aukusti", "L3"),
        SnookerPlayer("Kivinen Jarmo", "L3"),
        SnookerPlayer("Tähtinen Anneli", "L4"),
        SnookerPlayer("Saarela Tero", "L4"),
        SnookerPlayer("Pulkkinen Valtteri", "L4"),
        SnookerPlayer("Eskelinen Tapio", "L4"),
    ]

    @property
    def examples(self):
        return [
            {
                "existing_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
                "output": to_json(
                    {
                        "group": "L1",
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Sinikka - Joonas 2-0",
                "output": to_json(
                    {
                        "group": "L2",
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Aukusti v Yrjö 2-1 Highest break: Aukusti - 18",
                "output": to_json(
                    {
                        "group": "L3",
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
                "passage": "Anneli 2 - Tero 1, ei breikkejä",
                "output": to_json(
                    {
                        "group": "L4",
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
