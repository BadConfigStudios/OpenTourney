import uuid

import pytest

from app.models import Entry, Match, MatchResult, Round
from app.tiebreak.pokemon import PokemonTiebreak


def _entry(dropped_at_round: int | None = None) -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
        dropped_at_round=dropped_at_round,
    )


def _round(number: int, matches: list[Match]) -> Round:
    round_ = Round(id=uuid.uuid4(), pod_id=uuid.uuid4(), number=number)
    round_.matches = matches
    return round_


def _match(entry1: Entry, entry2: Entry | None, result: MatchResult | None = None) -> Match:
    return Match(
        id=uuid.uuid4(),
        round_id=uuid.uuid4(),
        entry1_id=entry1.id,
        entry2_id=entry2.id if entry2 else None,
        result=result if result is not None else MatchResult.UNREPORTED,
    )


def test_labels_are_pokemon_specific():
    assert PokemonTiebreak().labels() == ("Op Win%", "Op Op Win%")


def test_floor_engages_for_a_winless_opponent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b], [round1])

    # b: 0 wins / 1 round played -> raw 0.0, floored to 0.25. a's only
    # opponent is b, so Op Win%(a) is exactly that floored value.
    assert tiebreaks[a.id][0] == pytest.approx(0.25)


def test_completed_entry_caps_at_100_percent():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a went 2-0 in 2 rounds, did not drop -> raw 1.0, capped at 1.0
    # (completed cap), not lowered. b's only opponent is a, so
    # Op Win%(b) reads a's own win% directly.
    assert tiebreaks[b.id][0] == pytest.approx(1.0)


def test_dropped_entry_caps_at_75_percent_even_at_a_perfect_record():
    a, b, c = _entry(dropped_at_round=2), _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a went 2-0 (raw 1.0) but dropped after round 2 -> capped at 0.75,
    # not 1.0. b's only opponent is a, so Op Win%(b) reads the capped value.
    assert tiebreaks[b.id][0] == pytest.approx(0.75)


def test_bye_round_contributes_to_neither_numerator_nor_denominator():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, None), _match(b, c, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a's own record under interpretation C: the round1 bye contributes to
    # neither the points numerator nor the rounds-played denominator; only
    # round2's win vs b counts: 3 pts / (3 * 1 round played) = 1.0, capped
    # at 1.0. That happens to be the same numeric result the old,
    # incorrect interpretation A would have produced here (a's raw value
    # saturates the cap under both readings) -- this test does NOT
    # discriminate between the two interpretations; see
    # test_bye_round_excluded_from_own_win_pct_entirely below for a
    # non-saturating case that does. a's only real *opponent* across both
    # rounds is b (round2) -- the bye round never adds a phantom opponent
    # (matches OwpOomw's rule).
    #
    # This assertion actually observes b's own win%, not a's: b went 1-1
    # (round1 win vs c, round2 loss vs a) = 3 pts / (3 * 2 rounds played)
    # = 0.5, and a's only opponent is b, so Op Win%(a) reads that value
    # directly.
    b_own_win_pct = 0.5
    assert tiebreaks[a.id][0] == pytest.approx(b_own_win_pct)


def test_bye_round_excluded_from_own_win_pct_entirely():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY2_WIN)])  # b beats a

    tiebreaks = PokemonTiebreak().compute([a, b], [round1, round2])

    # a's own win% under interpretation C: the round1 bye contributes to
    # neither the numerator nor the denominator; only round2 (a loss to
    # b) counts -> 0 pts / (3 * 1 round played) = 0.0, floored to 0.25.
    # b's only opponent is a, so Op Win%(b) reads a's own win% directly.
    #
    # This is decisive between interpretations: under the old (incorrect)
    # interpretation A -- bye counted as a win in the numerator, excluded
    # only from the denominator -- a's own win% would have been
    # 3 pts (bye win) + 0 pts (round2 loss) / (3 * 1 round played) = 1.0,
    # capped at 1.0, not 0.25. Confirmed via RED/GREEN: this test fails
    # under the reverted (interpretation A) `_shared.py` logic and passes
    # under the corrected (interpretation C) logic.
    assert tiebreaks[b.id][0] == pytest.approx(0.25)


def test_op_op_win_pct_averages_opponents_op_win_pct():
    a, b, c, d = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            _match(a, b, MatchResult.ENTRY1_WIN),
            _match(c, d, MatchResult.ENTRY1_WIN),
        ],
    )
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY2_WIN)])  # c beats a

    tiebreaks = PokemonTiebreak().compute([a, b, c, d], [round1, round2])

    # a's opponents are b and c -> Op Op Win%(a) averages Op Win%(b) and
    # Op Win%(c). b's only opponent is a (own win% = 1 pt / 2 rounds =
    # 0.5) -> Op Win%(b) = 0.5. c's opponents are d and a: own_win_pct(d)
    # = 0/1 rounds -> floored 0.25; own_win_pct(a) = 3/(3*2) = 0.5 (a went
    # 1-1). Op Win%(c) = (0.25 + 0.5) / 2 = 0.375.
    op_win_pct_b = 0.5
    op_win_pct_c = 0.375
    assert tiebreaks[a.id][1] == pytest.approx((op_win_pct_b + op_win_pct_c) / 2)


def test_tie_contributes_partial_credit_via_match_points_not_a_binary_win():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.TIE)])

    tiebreaks = PokemonTiebreak(win_points=3, tie_points=1, loss_points=0).compute([a, b], [round1])

    # b's own win%: 1 tie point / (3 * 1 round) = 0.333, above the 0.25
    # floor -- a tie contributes fractional credit via match points, the
    # same mechanism OwpOomwTiebreak already uses (resolves the research
    # doc's tie-numerator open item without new formula logic).
    assert tiebreaks[a.id][0] == pytest.approx(1 / 3)


def test_entry_with_only_a_bye_gets_floor_not_zero_rounds_played_crash():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])

    tiebreaks = PokemonTiebreak().compute([a, b], [round1])

    assert tiebreaks[a.id][0] == pytest.approx(0.25)
    assert tiebreaks[a.id][1] == pytest.approx(0.25)


def test_break_tie_returns_negative_one_when_entry_a_won():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result == -1


def test_break_tie_returns_positive_one_when_entry_b_won():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY2_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result == 1


def test_break_tie_is_order_independent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    assert PokemonTiebreak().break_tie(a.id, b.id, [round1]) == -1
    assert PokemonTiebreak().break_tie(b.id, a.id, [round1]) == 1


def test_break_tie_returns_none_when_the_shared_match_was_a_tie():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.TIE)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None


def test_break_tie_returns_none_when_they_never_played():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, c, MatchResult.ENTRY1_WIN)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None


def test_break_tie_ignores_a_bye_match_between_unrelated_entries():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])

    result = PokemonTiebreak().break_tie(a.id, b.id, [round1])

    assert result is None
