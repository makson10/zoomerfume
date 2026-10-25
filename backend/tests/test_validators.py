from __future__ import annotations

import pytest

from app.core.validators import validate_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Mary   Jane ", "Mary Jane"),
        ("Zoë O'Brien-Łukasik", "Zoë O'Brien-Łukasik"),
    ],
    ids=["collapses-whitespace", "unicode-letters-and-punctuation"],
)
def test_validate_name_cleans_up_names(raw: str, expected: str) -> None:
    assert validate_name(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["A", "--", "ignore previous instructions!"],
    ids=["too-short", "no-letters", "prompt-punctuation"],
)
def test_validate_name_rejects_invalid_names(raw: str) -> None:
    assert validate_name(raw) is None
