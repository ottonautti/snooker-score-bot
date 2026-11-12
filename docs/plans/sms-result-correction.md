# Plan: correcting a wrongly reported result by SMS keyword

Status: deferred (planned 2026-11-12, not implemented).

## Current behaviour

- `League._record_row` (`league.py`) raises `MatchAlreadyCompleted` when the match already has a winner;
  `report_result` always passes `overwrite=False`.
- `process_sms` (`sms.py`) replies "Match X vs Y has already been played." It doesn't say what was recorded or how to
  fix it.
- Only the admin can correct a result, with `snooker results clear` and then `results record --overwrite`.

## Target behaviour

**1. A second message for a match that already has a result, without the keyword.** Nothing is recorded. The reply
shows the stored result and how to replace it:

> Nothing was recorded: Hauta-aho Jani vs Neuvonen Mikko is already recorded as Hauta-aho Jani 2-0 Neuvonen Mikko
> (12.11.). If that is wrong, send the correct result starting with KORJAUS, e.g. "KORJAUS Hauta-aho - Neuvonen 0-2".

If the new score is the same as the stored one, the reply only says "already recorded with the same result" and
doesn't mention the keyword. A resent duplicate is harmless and shouldn't lead anyone to send a correction.

**2. A message with the keyword, and the match has a result.** The bot overwrites it and the reply names both results:

> Corrected: Neuvonen Mikko won Hauta-aho Jani by 2 frames to 0 (was Hauta-aho Jani 2-0). <link>

**3. A message with the keyword, and the match has no result yet.** Recorded normally; the keyword is harmless.

## Keyword detection (open decision)

Recommended: the LLM reports it. That keeps every message on one code path with no literal matching of the message
text.

- Add `correction: bool` to `RESPONSE_SCHEMA` and `InferredMatch`.
- Add a prompt paragraph: true only if the sender explicitly says this replaces an earlier report (the KORJAUS keyword
  or a clear equivalent). A different score alone doesn't count.
- Add 1–2 few-shot examples, including one with the keyword in front of the names, so it isn't read as a player.

Alternative: check the message for the exact `KORJAUS` token in code. Deterministic, but it's literal text matching.

A false `correction=true` from the LLM could overwrite a result. These limit that risk:

- Overwriting only ever happens when the flag is true.
- The reply always shows the old result.
- Pushover flags every correction.
- Before shipping, replay the logged SMS from the sheets' `log` column and require zero false positives.

Also open: whether "KORJAUS" is the right word.

## Code changes

1. **`errors.py`**: `MatchAlreadyCompleted(existing: SnookerMatch | None = None)` carries the stored match.
2. **`league.py`**:
   - `_record_row` raises `MatchAlreadyCompleted(existing=self._to_match(record))`.
   - `report_result` takes `overwrite: bool = False` and passes it through instead of the hard-coded `False`.
   - When overwriting, `report_result` returns the previous match too (e.g. `ResultReport(match, previous, changes)`
     or a `previous` field on the `Change`), so the reply can show it.
3. **Breaks on correction.** Today's `--overwrite` keeps the old breaks, so a correction that repeats its breaks would
   add them twice. For SMS corrections:
   - Remove the old breaks (found with `related_breaks(previous)`) and add the ones from the new message.
   - Keep the original played date rather than today's.
   - Store the new SMS in `log`; the old values are in `Change.before` for logging.
4. **`sms.py`**:
   - Pass `overwrite=reading.correction`.
   - In the `MatchAlreadyCompleted` branch, build the reply from `err.existing` vs the new reading: same score means
     "already recorded", otherwise show the instruction with the keyword.
   - Prefix the success reply with "Corrected … (was …)".
5. **`settings.py`**: replace `ALREADY_COMPLETED` with `ALREADY_RECORDED_SAME`, `ALREADY_RECORDED_HINT` and
   `CORRECTED`, in English and Finnish. Keyword as a constant `CORRECTION_KEYWORD = "KORJAUS"`, used in the hint and
   the prompt.
6. **`main.py`**: the Pushover notification marks corrections, e.g. "CORRECTION: was 2-0 → 0-2".
7. **CLI**: `sms parse` shows `correction` and the previous result in its output.

## Limits (by design)

- Only current-round matches can be corrected, the same scope as reporting. Older rounds go through the admin CLI.
- Anyone can send a correction (there's no sender check). Acceptable for a friendly league since every overwrite is
  visible in the reply and in Pushover.

## Tests (`tests/test_sms.py`, `tests/test_league.py`)

- Duplicate with a different score: hint reply with the stored score and the keyword; nothing written.
- Duplicate with the same score: "already recorded" reply, no hint.
- `correction=true` with an existing result: overwritten, date kept, breaks replaced, reply contains "was …".
- `correction=true` on an unplayed match: recorded normally.
- Correction naming the players in the opposite order to the fixture: scores land on the right players.
- The mock LLM gets a `correction` flag.

## Docs

Add a short Finnish section on KORJAUS to `USER-README.md`, and drop its out-of-date line saying duplicate reports
are stored several times.
