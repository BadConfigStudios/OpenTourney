import pytest
from pydantic import ValidationError

from app.schemas.match import MatchResultUpdate


def test_match_result_update_accepts_raw_json_string():
    # Regression pin for 937bcad: MatchResult must be a str enum so that
    # Literal[MatchResult.ENTRY1_WIN, ...] validates raw JSON strings like "entry1_win"
    # instead of only accepting MatchResult enum instances.
    update = MatchResultUpdate.model_validate({"result": "entry1_win"})
    assert update.result == "entry1_win"


def test_match_result_update_rejects_unreported():
    with pytest.raises(ValidationError):
        MatchResultUpdate.model_validate({"result": "unreported"})


def test_match_result_update_rejects_unknown_value():
    with pytest.raises(ValidationError):
        MatchResultUpdate.model_validate({"result": "not_a_real_result"})
