import json
from functools import partial

from . import FewShotData
from ..models import SnookerPlayer

to_json = partial(json.dumps, ensure_ascii=False)


class MockFewShotData(FewShotData):
    players = [
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

    @property
    def examples(self):
        return [
            {
                "existing_players": "\n".join([str(plr) for plr in self.players]),
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
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
                "existing_players": "\n".join([str(plr) for plr in self.players]),
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
