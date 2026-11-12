import pytest

from snooker_score_bot.errors import AmbiguousPlayersError, InferenceMismatchError, MatchNotFound, UnknownPlayersError
from snooker_score_bot.models import InferredMatch, SnookerPlayer
from snooker_score_bot.verification import resolve_match

P = SnookerPlayer
PLAYERS = [
    P(name="Lundgren Mikko", group="L3"),
    P(name="Nurmi Jani", group="L3"),
    P(name="Nikula Jani", group="L4"),
    P(name="Bäck Mikko", group="L4"),
    P(name="Neuvonen Mikko", group="L7"),
    P(name="Nevala Jyrki", group="L7"),
    P(name="Hauta-aho Jani", group="L7"),
]
# matches of the current round (L4's Jani and Mikko have none)
ROUND = {
    frozenset(("Nurmi Jani", "Lundgren Mikko")),
    frozenset(("Neuvonen Mikko", "Nevala Jyrki")),
    frozenset(("Neuvonen Mikko", "Hauta-aho Jani")),
    frozenset(("Nevala Jyrki", "Hauta-aho Jani")),
}
JANIS = ["Nurmi Jani", "Nikula Jani", "Hauta-aho Jani"]
MIKKOS = ["Lundgren Mikko", "Bäck Mikko", "Neuvonen Mikko"]


def reading(first, second, s1=2, s2=0, breaks=()):
    return InferredMatch(
        players=[{"options": first}, {"options": second}],
        player1_score=s1,
        player2_score=s2,
        breaks=[{"player": p, "points": n} for p, n in breaks],
    )


def names(pair):
    return tuple(p.name for p in pair)


def test_one_pair_with_a_match_this_round():
    assert names(resolve_match(reading(["Hauta-aho Jani"], ["Neuvonen Mikko"]), PLAYERS, ROUND)) == (
        "Hauta-aho Jani",
        "Neuvonen Mikko",
    )


def test_several_options_narrowed_by_group_and_round():
    """E.g. "Hauta-aho voitti Neuvosen, breikki Jani": the LLM may list several players for a mention."""
    pair = resolve_match(reading(["Nurmi Jani", "Hauta-aho Jani"], ["Neuvonen Mikko"]), PLAYERS, ROUND)
    assert names(pair) == ("Hauta-aho Jani", "Neuvonen Mikko")


def test_ambiguous_message():
    """Regression: "Jani - Mikko 2-0" was recorded as Neuvonen Mikko beating Nevala Jyrki."""
    with pytest.raises(AmbiguousPlayersError) as exc:
        resolve_match(reading(JANIS, MIKKOS), PLAYERS, ROUND)
    lines = exc.value.reply.splitlines()
    assert "Nurmi Jani - Lundgren Mikko (L3)" in lines and "Hauta-aho Jani - Neuvonen Mikko (L7)" in lines
    assert not any("Nikula" in line for line in lines)  # no match this round
    assert "Jyrki" not in exc.value.reply


def test_ambiguous_reply_keeps_mention_order():
    with pytest.raises(AmbiguousPlayersError) as exc:
        resolve_match(reading(MIKKOS, JANIS, 0, 2), PLAYERS, ROUND)
    assert "Neuvonen Mikko - Hauta-aho Jani (L7)" in exc.value.reply.splitlines()


def test_any_same_group_pair_without_prepared_fixtures():
    pair = resolve_match(reading(["Nikula Jani"], ["Bäck Mikko"]), PLAYERS, round_pairs=None)
    assert names(pair) == ("Nikula Jani", "Bäck Mikko")


@pytest.mark.parametrize(
    "first, second",
    [([], ["Neuvonen Mikko"]), (["Pekka"], ["Neuvonen Mikko"]), (["Nurmi Jani"], ["Neuvonen Mikko"])],
    ids=["nobody", "not in list", "different groups"],
)
def test_unknown_players(first, second):
    with pytest.raises(UnknownPlayersError):
        resolve_match(reading(first, second), PLAYERS, ROUND)


def test_same_group_but_no_match_this_round():
    with pytest.raises(MatchNotFound):
        resolve_match(reading(["Nikula Jani"], ["Bäck Mikko"]), PLAYERS, ROUND)


@pytest.mark.parametrize(
    "answer",
    [
        reading(["Hauta-aho Jani"], ["Neuvonen Mikko"], 1, 1),  # draw
        reading(["Hauta-aho Jani"], ["Neuvonen Mikko"], None, None),  # no scores
        reading(["Hauta-aho Jani"], ["Neuvonen Mikko"], breaks=[(3, 40)]),  # break by a third person
        InferredMatch(players=[{"options": ["Hauta-aho Jani"]}], player1_score=2, player2_score=0),  # one person
    ],
    ids=["draw", "no scores", "break by nobody", "one person"],
)
def test_incoherent_answers(answer):
    with pytest.raises(InferenceMismatchError):
        resolve_match(answer, PLAYERS, ROUND)
