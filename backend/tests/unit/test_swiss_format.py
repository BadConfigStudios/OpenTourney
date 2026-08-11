import uuid

import pytest

from app.formats.swiss import SwissFormat, _compute_standings
from app.models import Entry, Match, MatchResult, Round


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


def test_round_one_pairs_entries_sequentially_with_table_numbers():
    entries = [_entry(), _entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    assert pairings[0].entry1_id == entries[0].id
    assert pairings[0].entry2_id == entries[1].id
    assert pairings[0].table_number == 1
    assert pairings[1].entry1_id == entries[2].id
    assert pairings[1].entry2_id == entries[3].id
    assert pairings[1].table_number == 2


def test_round_one_gives_bye_to_last_entry_when_odd():
    entries = [_entry(), _entry(), _entry()]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    assert len(pairings) == 2
    bye = pairings[-1]
    assert bye.entry1_id == entries[2].id
    assert bye.entry2_id is None
    assert bye.table_number is None


def test_round_one_with_no_entries_returns_no_pairings():
    pairings = SwissFormat().generate_round(entries=[], previous_rounds=[])

    assert pairings == []


def test_compute_standings_awards_win_tie_loss_points():
    e1, e2, e3, e4 = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.TIE,
            ),
        ],
    )

    standings, bye_used = _compute_standings([e1, e2, e3, e4], [round1])

    assert standings[e1.id] == 3
    assert standings[e2.id] == 0
    assert standings[e3.id] == 1
    assert standings[e4.id] == 1
    assert bye_used == set()


def test_compute_standings_counts_bye_as_a_win():
    e1 = _entry()
    round1 = _round(
        1, [Match(id=uuid.uuid4(), round_id=uuid.uuid4(), entry1_id=e1.id, entry2_id=None)]
    )

    standings, bye_used = _compute_standings([e1], [round1])

    assert standings[e1.id] == 3
    assert bye_used == {e1.id}


def test_compute_standings_raises_on_unreported_match():
    e1, e2 = _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.UNREPORTED,
            )
        ],
    )

    with pytest.raises(ValueError, match="unreported"):
        _compute_standings([e1, e2], [round1])


def test_compute_standings_raises_on_none_result_not_yet_flushed():
    e1, e2 = _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                # no result= passed — simulates an unflushed Match where the
                # column default (default=MatchResult.UNREPORTED) hasn't
                # fired yet, so match.result is None rather than UNREPORTED.
            )
        ],
    )

    with pytest.raises(ValueError, match="unreported"):
        _compute_standings([e1, e2], [round1])


def test_round_two_pairs_within_score_groups_by_prior_results():
    e1, e2, e3, e4 = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.ENTRY1_WIN,
            ),
        ],
    )

    pairings = SwissFormat().generate_round(entries=[e1, e2, e3, e4], previous_rounds=[round1])

    pair_sets = {frozenset({p.entry1_id, p.entry2_id}) for p in pairings}
    assert pair_sets == {frozenset({e1.id, e3.id}), frozenset({e2.id, e4.id})}
    assert all(p.table_number is not None for p in pairings)


def test_round_three_avoids_rematches_across_two_prior_rounds():
    e1, e2 = _entry(), _entry()
    # Pin e3 and e4 UUIDs to ensure e3 sorts before e4 by string comparison
    # when tied on points, forcing the rematch-skip branch to always execute
    e3_id = uuid.UUID("00000000-0000-0000-0000-000000000003")
    e4_id = uuid.UUID("00000000-0000-0000-0000-000000000004")
    e3 = Entry(
        id=e3_id,
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
    )
    e4 = Entry(
        id=e4_id,
        pod_id=uuid.uuid4(),
        player_uuid=uuid.uuid4(),
        source_system="test",
        metadata_={},
    )

    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.ENTRY1_WIN,
            ),
        ],
    )
    round2 = _round(
        2,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e3.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e2.id,
                entry2_id=e4.id,
                result=MatchResult.ENTRY2_WIN,
            ),
        ],
    )

    pairings = SwissFormat().generate_round(
        entries=[e1, e2, e3, e4], previous_rounds=[round1, round2]
    )

    pair_sets = {frozenset({p.entry1_id, p.entry2_id}) for p in pairings}
    already_played = {
        frozenset({e1.id, e2.id}),
        frozenset({e3.id, e4.id}),
        frozenset({e1.id, e3.id}),
        frozenset({e2.id, e4.id}),
    }
    assert pair_sets.isdisjoint(already_played)
    assert pair_sets == {frozenset({e1.id, e4.id}), frozenset({e2.id, e3.id})}


def test_select_bye_entry_skips_lowest_ranked_if_already_used():
    from app.formats.swiss import _select_bye_entry

    e1, e2, e3 = _entry(), _entry(), _entry()
    ranked = [e1, e2, e3]  # e3 is lowest-ranked, e2 is middle
    bye_used = {e3.id}  # lowest-ranked already used

    chosen = _select_bye_entry(ranked, bye_used)

    # Must return e2 (middle entry), not e1 (top) or e3 (bottom, already used)
    assert chosen.id == e2.id


def test_bye_rotates_away_from_round_one_recipient_in_round_two():
    e1, e2, e3, e4, e5 = _entry(), _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(id=uuid.uuid4(), round_id=uuid.uuid4(), entry1_id=e5.id, entry2_id=None),
        ],
    )

    pairings = SwissFormat().generate_round(entries=[e1, e2, e3, e4, e5], previous_rounds=[round1])

    bye_pairings = [p for p in pairings if p.entry2_id is None]
    assert len(bye_pairings) == 1
    assert bye_pairings[0].entry1_id != e5.id  # bye must NOT repeat on e5
    assert bye_pairings[0].table_number is None
    real_pairings = [p for p in pairings if p.entry2_id is not None]
    assert sorted(p.table_number for p in real_pairings) == [1, 2]


def test_compute_standings_ranks_by_points_descending():
    e1, e2, e3, e4 = _entry(), _entry(), _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.ENTRY1_WIN,
            ),
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e3.id,
                entry2_id=e4.id,
                result=MatchResult.TIE,
            ),
        ],
    )

    standings = SwissFormat().compute_standings([e1, e2, e3, e4], [round1])

    assert [row.entry_id for row in standings][0] == e1.id
    assert [row.points for row in standings] == [3, 1, 1, 0]
    assert [row.rank for row in standings] == [1, 2, 3, 4]


def test_compute_standings_with_no_rounds_ranks_all_entries_at_zero_points():
    e1, e2 = _entry(), _entry()

    standings = SwissFormat().compute_standings([e1, e2], [])

    assert {row.points for row in standings} == {0}
    assert sorted(row.rank for row in standings) == [1, 2]


def test_compute_standings_method_raises_on_unreported_match():
    e1, e2 = _entry(), _entry()
    round1 = _round(
        1,
        [
            Match(
                id=uuid.uuid4(),
                round_id=uuid.uuid4(),
                entry1_id=e1.id,
                entry2_id=e2.id,
                result=MatchResult.UNREPORTED,
            )
        ],
    )

    with pytest.raises(ValueError, match="unreported"):
        SwissFormat().compute_standings([e1, e2], [round1])


def test_rank_entries_orders_by_points_then_tiebreak_then_uuid():
    from app.formats.swiss import _rank_entries

    e_low_points, e_high_tiebreak, e_low_tiebreak, e_tied_a, e_tied_b = (
        _entry(),
        _entry(),
        _entry(),
        _entry(),
        _entry(),
    )
    standings = {
        e_low_points.id: 0,
        e_high_tiebreak.id: 3,
        e_low_tiebreak.id: 3,
        e_tied_a.id: 6,
        e_tied_b.id: 6,
    }
    tiebreaks = {
        e_low_points.id: (0.9, 0.9),
        e_high_tiebreak.id: (0.7, 0.7),
        e_low_tiebreak.id: (0.4, 0.4),
        e_tied_a.id: (0.5, 0.5),
        e_tied_b.id: (0.5, 0.5),
    }

    ranked = _rank_entries(
        [e_low_points, e_high_tiebreak, e_low_tiebreak, e_tied_a, e_tied_b],
        standings,
        tiebreaks,
    )

    # e_tied_a/e_tied_b (6 pts) rank above e_high_tiebreak/e_low_tiebreak
    # (3 pts) despite a lower tiebreak value -- points always wins first.
    assert {r.id for r in ranked[:2]} == {e_tied_a.id, e_tied_b.id}
    # Within the 3-point group, the higher tiebreak value ranks first.
    assert ranked[2].id == e_high_tiebreak.id
    assert ranked[3].id == e_low_tiebreak.id
    # e_low_points is last regardless of its (unused) high tiebreak value.
    assert ranked[4].id == e_low_points.id
    # e_tied_a/e_tied_b are tied on both points AND tiebreak -- UUID string
    # order is the last-resort fallback.
    assert [r.id for r in ranked[:2]] == sorted([e_tied_a.id, e_tied_b.id], key=str)


def test_generate_round_excludes_dropped_entries_from_round_one():
    active = [_entry(), _entry(), _entry()]
    dropped = _entry(dropped_at_round=0)
    entries = [*active, dropped]

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[])

    paired_ids = {pairing.entry1_id for pairing in pairings} | {
        pairing.entry2_id for pairing in pairings if pairing.entry2_id is not None
    }
    assert dropped.id not in paired_ids
    assert paired_ids == {entry.id for entry in active}


def test_generate_round_excludes_dropped_entries_from_later_rounds():
    active = [_entry(), _entry(), _entry()]
    dropped = _entry(dropped_at_round=1)
    entries = [*active, dropped]

    match_r1 = Match(
        id=uuid.uuid4(),
        entry1_id=active[0].id,
        entry2_id=active[1].id,
        result=MatchResult.ENTRY1_WIN,
    )
    bye_r1 = Match(id=uuid.uuid4(), entry1_id=active[2].id, entry2_id=None)
    dropped_match_r1 = Match(id=uuid.uuid4(), entry1_id=dropped.id, entry2_id=None)
    round_1 = _round(1, [match_r1, bye_r1, dropped_match_r1])

    pairings = SwissFormat().generate_round(entries=entries, previous_rounds=[round_1])

    paired_ids = {pairing.entry1_id for pairing in pairings} | {
        pairing.entry2_id for pairing in pairings if pairing.entry2_id is not None
    }
    assert dropped.id not in paired_ids
