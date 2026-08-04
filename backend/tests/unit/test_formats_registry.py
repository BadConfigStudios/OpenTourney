import pytest

from app.formats.registry import get_tournament_format
from app.formats.swiss import SwissFormat


def test_get_tournament_format_returns_swiss_format():
    format_ = get_tournament_format("swiss")

    assert isinstance(format_, SwissFormat)


def test_get_tournament_format_raises_for_unknown_slug():
    with pytest.raises(ValueError, match="unknown tournament format slug"):
        get_tournament_format("single-elim")
