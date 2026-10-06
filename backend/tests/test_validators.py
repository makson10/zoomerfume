from __future__ import annotations

import pytest

from app.core.validators import validate_name, validate_phone


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("067 123 45 67", "+380671234567"),
        ("+48 512 345 678", "+48512345678"),
    ],
    ids=["local-uses-default-region", "international"],
)
def test_validate_phone_returns_e164(raw: str, expected: str) -> None:
    assert validate_phone(raw, "UA") == expected


@pytest.mark.parametrize("raw", ["12345", "call me maybe", ""])
def test_validate_phone_rejects_non_numbers(raw: str) -> None:
    assert validate_phone(raw, "UA") is None


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
    ["A", "x" * 41, "--", "Robert'); DROP TABLE users;--", "ignore previous instructions!"],
    ids=["too-short", "too-long", "no-letters", "sql", "prompt-punctuation"],
)
def test_validate_name_rejects_invalid_names(raw: str) -> None:
    assert validate_name(raw) is None
