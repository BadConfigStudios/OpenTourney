import uuid

import pytest

from app.models import Entry, Match, MatchResult, Round
from app.tiebreak.owp_oomw import OwpOomwTiebreak


def _entry() -> Entry:
    return Entry(
        id=uuid.uuid4(),
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
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


def test_floor_engages_for_a_weak_opponent():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak().compute([a, b], [round1])

    # b has 0 points from 1 round played -> own MWP would be 0.0, floored to 0.33.
    # a's only opponent is b, so a's OMW% is exactly that floored value.
    assert tiebreaks[a.id][0] == pytest.approx(0.33)


def test_bye_counts_toward_own_denominator_but_is_never_an_opponent():
    a, b, c = _entry(), _entry(), _entry()
    round1 = _round(1, [_match(a, None), _match(b, c, MatchResult.ENTRY1_WIN)])
    round2 = _round(2, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak().compute([a, b, c], [round1, round2])

    # a's own record includes the bye: 2 wins (bye + round2 vs b) / 2 rounds
    # played = own MWP 1.0 -- the bye counts toward a's own denominator.
    # But a's only *opponent* across both rounds is b (round2) -- the bye
    # round never adds a phantom opponent, so OMW%(a) is exactly b's own
    # MWP, averaged over a single opponent, not two.
    b_own_mwp = max(3 / (3 * 2), 0.33)  # b: round1 win (3) + round2 loss (0) / 2 rounds
    assert tiebreaks[a.id][0] == pytest.approx(b_own_mwp)


def test_oomw_averages_opponents_omw_percentages():
    a, b, c, d = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            _match(a, b, MatchResult.ENTRY1_WIN),
            _match(c, d, MatchResult.ENTRY1_WIN),
        ],
    )
    round2 = _round(2, [_match(a, c, MatchResult.ENTRY2_WIN)])  # c beats a

    tiebreaks = OwpOomwTiebreak().compute([a, b, c, d], [round1, round2])

    # a: 3 pts / 2 rounds = 0.5 own MWP. c: 6 pts / 2 rounds = 1.0 own MWP.
    # b's only opponent is a -> OMW%(b) = 0.5. c's opponents are d and a,
    # so OMW%(c) averages their own MWPs: own_mwp(d) and own_mwp(a).
    # a's opponents are b and c -> OOMW%(a) averages OMW%(b) and OMW%(c).
    omw_b = 0.5
    own_mwp_d = max(0 / (3 * 1), 0.33)  # d's own MWP (0 pts / 1 round played)
    omw_c = (own_mwp_d + 0.5) / 2  # OMW%(c) = avg(own_mwp[d], own_mwp[a])
    assert tiebreaks[a.id][1] == pytest.approx((omw_b + omw_c) / 2)


def test_bye_only_entry_gets_floor_omw_not_zero():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, None)])  # a receives a bye, no real opponent yet

    tiebreaks = OwpOomwTiebreak().compute([a, b], [round1])

    # a has zero real opponents faced -- OMW%/OOMW% must floor to 0.33,
    # not silently drop to 0.0 and rank a below entries with a real
    # (even weak) opponent.
    assert tiebreaks[a.id][0] == pytest.approx(0.33)
    assert tiebreaks[a.id][1] == pytest.approx(0.33)


def test_custom_point_values_and_floor_are_respected():
    a, b = _entry(), _entry()
    round1 = _round(1, [_match(a, b, MatchResult.ENTRY1_WIN)])

    tiebreaks = OwpOomwTiebreak(floor=0.5, win_points=2, tie_points=1, loss_points=-1).compute(
        [a, b], [round1]
    )

    # b's own MWP with these constants: -1 / (2 * 1) = -0.5, floored to 0.5.
    assert tiebreaks[a.id][0] == pytest.approx(0.5)
