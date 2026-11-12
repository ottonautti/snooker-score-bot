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
        SnookerPlayer(name="Laine Mika", group="L2"),
        SnookerPlayer(name="Nieminen Jarmo", group="L2"),
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
    def players_list(self) -> str:
        """The player list all examples refer to, formatted as in the prompt."""
        return "\n".join(p.__llm_str__() for p in self.players)

    def _example(self, passage: str, options1, options2, score1, score2, breaks=()) -> dict:
        output = {
            "players": [{"options": list(options1)}, {"options": list(options2)}],
            "player1_score": score1,
            "player2_score": score2,
            "breaks": [{"player": p, "points": n} for p, n in breaks],
        }
        return {"passage": passage, "output": to_json(output)}

    @property
    def examples(self):
        """Every name in an output must appear in the player list."""
        return [
            # surnames; a break by the first person
            self._example(
                "Huhtala - Andersson 2-1. Breikki 45, Huhtala.",
                ["Huhtala Katja"],
                ["Andersson Leila"],
                2,
                1,
                [(1, 45)],
            ),
            # "Kari" is Tuomi Kari's first name and Kari Yrjö's surname: list both
            self._example("Sinikka - Kari 0-2", ["Laaksonen Sinikka"], ["Tuomi Kari", "Kari Yrjö"], 0, 2),
            # nickname
            self._example(
                "Valtsu v Anneli 2-1, breaks: Anneli 107, 101, Valtsu 52",
                ["Pulkkinen Valtteri"],
                ["Tähtinen Anneli"],
                2,
                1,
                [(2, 107), (2, 101), (1, 52)],
            ),
            # inflected names, loser mentioned first
            self._example(
                "Aukusti hävisi Yrjölle 1-2, breikit Aukusti 25, Yrjö 18",
                ["Sjöblom Aukusti"],
                ["Kari Yrjö"],
                1,
                2,
                [(1, 25), (2, 18)],
            ),
            # typo, score after each name
            self._example("Huuskonen 0 - Suhnen 2, ei breikkejä", ["Huuskonen Alexandra"], ["Suhonen Tanja"], 0, 2),
            # first names shared by several players: list them all
            self._example("Mika - Jarmo 2-0", ["Laine Mika", "Lahti Mika"], ["Nieminen Jarmo", "Kivinen Jarmo"], 2, 0),
            # an initial picks one of the players sharing a first name
            self._example("Jarmo K - Aukusti 2-0", ["Kivinen Jarmo"], ["Sjöblom Aukusti"], 2, 0),
            # a similar-looking surname is a different player: only Lahti, not Laine
            self._example("Lahti - Aukusti 0-2", ["Lahti Mika"], ["Sjöblom Aukusti"], 0, 2),
            # nobody in the list
            self._example("Pekka - Matti 2-0", [], [], 2, 0),
        ]
