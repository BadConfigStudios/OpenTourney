# backend/tests/acceptance/test_pokemon_tom_cross_validation.py
from pathlib import Path

from app.formats.swiss import SwissFormat
from app.tiebreak.pokemon import PokemonTiebreak
from tests.acceptance.tom_fixtures import load_tom_pod, load_tom_standings

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = REPO_ROOT / "docs" / "superpowers" / "fixtures" / "tom-tournaments"


def test_round_rock_final_ranking_matches_tom_standings():
    """Primary fixture: 23->18 players, 1 bye (round 1), 5 drops, no ties.
    Covers the bye-exclusion rule (interpretation C: a bye contributes to
    neither the numerator nor the denominator of the own-win% figure used
    as an input to other competitors' Op Win%/Op Op Win%) and the
    floor/cap end to end.

    Dropped entries are excluded from the strict ordering comparison (see
    below) -- TOM's dropped-player placement doesn't appear to be a pure
    function of the final-round tiebreak formula."""
    xml_path = FIXTURES_DIR / "round-rock-summer-2026-06-20.xml"
    entries, rounds, id_map = load_tom_pod(xml_path, pod_category="0")
    expected_order = load_tom_standings(xml_path, standings_category="0", id_map=id_map)

    standings = SwissFormat(tiebreak=PokemonTiebreak()).compute_standings(entries, rounds)

    # Adjudicated finding (Phase 18 Task 10): TOM ranks one dropped entry
    # (userid 5829175, Op Win% 0.333) above two active entries with nearly
    # double its Op Win% (0.593, 0.556) -- a result no tiebreak-formula
    # variant explains. The leading hypothesis is that TOM freezes a
    # dropped competitor's standing at drop-time (e.g. using only the
    # rounds played before dropping) rather than recomputing against the
    # final-round dataset -- a fundamentally different, point-in-time
    # computation that OpenTourney doesn't and shouldn't try to replicate
    # here. This is out of scope for a pure tiebreak-formula validation,
    # so dropped entries (`Entry.dropped_at_round is not None`) are
    # excluded entirely from the ordering comparison below; only entries
    # that completed the tournament are strictly compared.
    active_ids = {entry.id for entry in entries if entry.dropped_at_round is None}
    actual_active_order = [row.entry_id for row in standings if row.entry_id in active_ids]
    expected_active_order = [entry_id for entry_id in expected_order if entry_id in active_ids]

    assert actual_active_order == expected_active_order


def test_cg_league_night_masters_subset_ranking_matches_tom_standings():
    """Secondary fixture: 16-player age-combined pod (category 10), no bye,
    2 drops (one testing the floor, one testing the cap from the other
    direction), and one genuine tie (round 2) -- closes the tie-numerator
    open item from docs/pokemon-tiebreak-research.md. Op Win%/Op Op Win%
    are computed over the full 16-player pod (opponents can be outside the
    Masters division under age-combined pairing), then filtered down to
    the 12-player Masters (category 2) subset for the ranking comparison,
    since TOM only publishes final standings per division."""
    xml_path = FIXTURES_DIR / "cg-league-night-2026-07-28.xml"
    entries, rounds, id_map = load_tom_pod(xml_path, pod_category="10")
    expected_masters_order = load_tom_standings(xml_path, standings_category="2", id_map=id_map)

    standings = SwissFormat(tiebreak=PokemonTiebreak()).compute_standings(entries, rounds)

    masters_ids = set(expected_masters_order)
    actual_masters_order = [row.entry_id for row in standings if row.entry_id in masters_ids]

    assert actual_masters_order == expected_masters_order
