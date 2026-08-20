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


def test_bye_round_excluded_from_denominator_but_counts_as_a_win():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, None), _match(b, c, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = PokemonTiebreak().compute([a, b, c], [round1, round2])

    # a's own record: bye (win, round excluded from denominator) + round2
    # win vs b = 2 wins / 1 round played (only round2 counts) = 1.0, capped
    # at 1.0. a's only *opponent* across both rounds is b (round2) -- the
    # bye round never adds a phantom opponent (matches OwpOomw's rule).
    # b's own win%: 0 wins (round1 win vs c, round2 loss vs a) = 1 win / 2
    # rounds played = 0.5.
    b_own_win_pct = 0.5
    assert tiebreaks[a.id][0] == pytest.approx(b_own_win_pct)


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
