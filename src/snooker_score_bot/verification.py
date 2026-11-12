"""Turning the LLM's reading of a score message into one match.

The LLM identifies the players: for each of the two people a message mentions, it lists every player in the list
that the mention could refer to (people write nicknames, abbreviations, first names, surnames and typos). The
message text is never matched against names here. This module only combines the LLM's answer with league data:
pairs from the two lists that are in the same group and have a match this round. One pair is the match; more than
one means the message is ambiguous; none means the players could not be identified.
"""

from typing import Optional

from .errors import AmbiguousPlayersError, InferenceMismatchError, MatchNotFound, UnknownPlayersError
from .models import InferredMatch, SnookerPlayer

Pair = tuple[SnookerPlayer, SnookerPlayer]


def resolve_match(
    reading: InferredMatch, players: list[SnookerPlayer], round_pairs: Optional[set[frozenset[str]]]
) -> Pair:
    """The match's two players, in the order the message mentions them.

    round_pairs: name pairs that have a match in the current round, or None if any same-group pair may play (leagues
    without prepared fixtures). Raises UnknownPlayersError or AmbiguousPlayersError (both carry the reply for the
    sender), MatchNotFound, or InferenceMismatchError when the answer doesn't hold together."""
    if len(reading.players) != 2:
        raise InferenceMismatchError(f"LLM read {len(reading.players)} people from the message, expected 2")
    by_name = {p.name: p for p in players}
    first, second = ([by_name[n] for n in mention.options if n in by_name] for mention in reading.players)
    if not first or not second:
        raise UnknownPlayersError()

    pairs = [(a, b) for a in first for b in second if a.group == b.group and a.name != b.name]
    if not pairs:
        raise UnknownPlayersError()
    if round_pairs is not None:
        pairs = [(a, b) for a, b in pairs if frozenset((a.name, b.name)) in round_pairs]
        if not pairs:
            raise MatchNotFound()

    scores = (reading.player1_score, reading.player2_score)
    if len(pairs) > 1:
        raise AmbiguousPlayersError(pairs, scores if None not in scores else None)
    if None in scores or scores[0] == scores[1]:
        raise InferenceMismatchError(f"LLM scores {scores[0]}-{scores[1]} do not give a winner")
    if any(b.player not in (1, 2) for b in reading.breaks):
        raise InferenceMismatchError("LLM attributed a break to neither player")
    return pairs[0]
