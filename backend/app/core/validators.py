"""Validation for what customers type during sign-in."""

from __future__ import annotations

import unicodedata

import phonenumbers

NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 40
NAME_PUNCTUATION = frozenset(" -'’")


def validate_phone(raw: str, default_region: str) -> str | None:
    """Return the phone number in E.164 format, or ``None`` if it isn't a valid number.

    Args:
        raw: The number as the customer typed it, with or without a country code.
        default_region: Region code (``UA``, ``PL``, ...) for numbers without one.
    """
    try:
        number = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(number):
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def validate_name(raw: str) -> str | None:
    """Return the cleaned-up name, or ``None`` if it isn't a plausible first name.

    A name is 2–40 characters of letters in any script, spaces, hyphens and
    apostrophes, with at least one letter. Runs of whitespace collapse to one space.
    The name goes into Zoomer's instructions, so nothing else is allowed.
    """
    name = " ".join(unicodedata.normalize("NFC", raw).split())
    if not NAME_MIN_LENGTH <= len(name) <= NAME_MAX_LENGTH:
        return None
    if not any(char.isalpha() for char in name):
        return None
    if not all(char.isalpha() or char in NAME_PUNCTUATION for char in name):
        return None
    return name
