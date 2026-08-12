import pytest

from app.formats.round_target import recommended_rounds


@pytest.mark.parametrize(
    ("active_entry_count", "expected"),
    [
        (0, 0),
        (1, 0),
        (2, 1),
        (3, 2),
        (4, 2),
        (5, 3),
        (8, 3),
        (9, 4),
    ],
)
def test_recommended_rounds(active_entry_count, expected):
    assert recommended_rounds(active_entry_count) == expected
