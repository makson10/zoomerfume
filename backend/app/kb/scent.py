"""Turn product notes into the two vectors the similar perfume search compares, and rank
products by them.

The note vector is sparse: one coordinate per note in the dictionary, weighted by how rare
the note is in the catalog (IDF) and by its level in the pyramid. The accord vector is
dense: one coordinate per accord, the sum of the accords the product's notes bring in. Both
are normalized to length 1, so their dot product is the cosine similarity.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.kb.corpus import RecordHeader

logger = logging.getLogger(__name__)

DICTIONARY_PATH = Path(__file__).with_name("notes.yaml")
# How much a note counts by its place in the pyramid. Top notes fade within half an hour,
# the heart and the base carry the scent for hours.
LEVEL_WEIGHTS = {"top": 0.6, "heart": 1.0, "base": 1.0, "key": 1.0}
# The hybrid score. The overall character counts a bit more than the exact ingredients.
ACCORDS_WEIGHT = 0.6
NOTES_WEIGHT = 0.4


class _NoteEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aliases: list[str] = []
    accords: dict[str, float] = Field(min_length=1)


class _DictionaryFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accords: list[str] = Field(min_length=1)
    notes: dict[str, _NoteEntry]


@dataclass(frozen=True)
class NoteDictionary:
    """Every known note: its spellings and the accords it brings in, from ``notes.yaml``."""

    accords: list[str]
    # Canonical note names, sorted. A note's position is its coordinate in the note vector.
    notes: list[str]
    note_accords: dict[str, dict[str, float]]
    # Every spelling of every note, normalized, mapped to the note's canonical name.
    spellings: dict[str, str]

    @classmethod
    def load(cls, path: Path = DICTIONARY_PATH) -> NoteDictionary:
        """Read and check the dictionary file.

        Raises:
            ValueError: The file is malformed, a note names an accord that isn't in the
                list, or one spelling belongs to two notes.
        """
        data = _DictionaryFile.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        spellings: dict[str, str] = {}
        for name, entry in data.notes.items():
            if unknown := set(entry.accords) - set(data.accords):
                raise ValueError(f"{name}: unknown accords {', '.join(sorted(unknown))}")
            for spelling in [name, *entry.aliases]:
                owner = spellings.setdefault(_normalize(spelling), name)
                if owner != name:
                    raise ValueError(f"{spelling!r} is a spelling of both {owner} and {name}")
        return cls(
            accords=data.accords,
            notes=sorted(data.notes),
            note_accords={name: entry.accords for name, entry in data.notes.items()},
            spellings=spellings,
        )

    def canonical(self, note: str) -> str | None:
        """Return the canonical name of a note as a product card writes it, or None when the
        dictionary doesn't know it."""
        return self.spellings.get(_normalize(note))


@dataclass(frozen=True)
class ScentVector:
    """A product's two vectors, each normalized to length 1."""

    accords: list[float]
    # Note coordinate → weight. Notes the product doesn't have are left out.
    notes: dict[int, float]


@dataclass(frozen=True)
class Candidate:
    """A product to rank against the reference."""

    record_id: str
    line: str
    vector: ScentVector


@dataclass(frozen=True)
class Match:
    """A ranked candidate: the hybrid score and the two similarities it is made of."""

    candidate: Candidate
    accords: float
    notes: float

    @property
    def score(self) -> float:
        return ACCORDS_WEIGHT * self.accords + NOTES_WEIGHT * self.notes


def build_vectors(
    products: list[RecordHeader], dictionary: NoteDictionary
) -> dict[str, ScentVector]:
    """Return the vectors of every product, by record id.

    IDF is counted over the products passed in, so pass the whole catalog. A note that every
    product has gets no weight. Notes the dictionary doesn't know are skipped with a
    warning, and so is a product left with no known notes.
    """
    levels: dict[str, dict[str, float]] = {}
    for product in products:
        if notes := _note_levels(product, dictionary):
            levels[product.id] = notes
        else:
            logger.warning("product skipped, no known notes | record=%s", product.id)
    counts = Counter(note for notes in levels.values() for note in notes)
    index = {name: position for position, name in enumerate(dictionary.notes)}
    vectors = {}
    for record_id, notes in levels.items():
        note_weights = {
            index[name]: math.log(len(levels) / counts[name]) * weight
            for name, weight in notes.items()
            if counts[name] < len(levels)
        }
        accords = [
            sum(
                weight * dictionary.note_accords[name].get(accord, 0.0)
                for name, weight in notes.items()
            )
            for accord in dictionary.accords
        ]
        vectors[record_id] = ScentVector(
            accords=_unit(accords),
            notes=dict(zip(note_weights, _unit(list(note_weights.values())), strict=True)),
        )
    return vectors


def similarity(a: ScentVector, b: ScentVector) -> tuple[float, float]:
    """Return the cosine similarity of two products' accord vectors and of their note vectors."""
    accords = sum(x * y for x, y in zip(a.accords, b.accords, strict=True))
    notes = sum(weight * b.notes.get(i, 0.0) for i, weight in a.notes.items())
    return accords, notes


def rank(reference: ScentVector, candidates: list[Candidate], k: int) -> list[Match]:
    """Score the candidates against the reference and return the best ``k``.

    At most one product per line makes it into the result, so three flankers of one
    perfume don't fill it.
    """
    matches = sorted(
        (Match(candidate, *similarity(reference, candidate.vector)) for candidate in candidates),
        key=lambda match: match.score,
        reverse=True,
    )
    picked: list[Match] = []
    lines: set[str] = set()
    for match in matches:
        if len(picked) == k:
            break
        if match.candidate.line not in lines:
            lines.add(match.candidate.line)
            picked.append(match)
    return picked


def shared_notes(
    a: ScentVector, b: ScentVector, dictionary: NoteDictionary, limit: int = 5
) -> list[str]:
    """The notes both products have, the ones that add most to their similarity first."""
    common = sorted(a.notes.keys() & b.notes.keys(), key=lambda i: a.notes[i] * b.notes[i])
    return [dictionary.notes[i] for i in reversed(common[-limit:])]


def shared_accords(
    a: ScentVector, b: ScentVector, dictionary: NoteDictionary, limit: int = 3
) -> list[str]:
    """The accords that are strong in both products, strongest first."""
    strength = {
        accord: min(x, y)
        for accord, x, y in zip(dictionary.accords, a.accords, b.accords, strict=True)
        if min(x, y) > 0
    }
    return sorted(strength, key=strength.__getitem__, reverse=True)[:limit]


def _note_levels(product: RecordHeader, dictionary: NoteDictionary) -> dict[str, float]:
    """Map each known note of a product to its level weight, the higher one when a note is
    on two levels."""
    weights: dict[str, float] = {}
    if product.notes is None:
        return weights
    for level, weight in LEVEL_WEIGHTS.items():
        for note in getattr(product.notes, level):
            name = dictionary.canonical(note)
            if name is None:
                logger.warning("unknown note skipped | record=%s note=%s", product.id, note)
            else:
                weights[name] = max(weights.get(name, 0.0), weight)
    return weights


def _normalize(note: str) -> str:
    return " ".join(note.lower().split())


def _unit(values: list[float]) -> list[float]:
    length = math.sqrt(sum(value * value for value in values))
    return [value / length for value in values] if length else values
