from __future__ import annotations

from datetime import date

import pytest

from app.kb.corpus import NotePyramid, RecordHeader, Size
from app.kb.scent import Candidate, NoteDictionary, ScentVector, build_vectors, rank, similarity

NOTES = NoteDictionary.load()


def product(record_id: str, line: str, **notes: list[str]) -> RecordHeader:
    return RecordHeader(
        id=record_id,
        title=f"Perfume {record_id}",
        type="product",
        updated=date(2026, 11, 1),
        brand="Test",
        line=line,
        concentration="EDP",
        family="woody",
        gender="unisex",
        seasons=["autumn"],
        notes=NotePyramid(**notes),
        sizes=[Size(ml=50, price=2000, points=100)],
        availability="in_stock",
    )


def test_dictionary_maps_every_spelling_to_one_note() -> None:
    assert NOTES.canonical("Calabrian  Bergamot") == "bergamot"
    assert NOTES.canonical("ambrox") == NOTES.canonical("ambroxan") == "ambroxan"
    assert NOTES.canonical("unobtainium") is None


def test_rare_shared_notes_count_more_than_common_ones() -> None:
    fillers = [
        product(f"KB-1{i:02d}", f"filler {i}", top=["bergamot"], base=["musk"]) for i in range(6)
    ]
    vectors = build_vectors(
        [
            product(
                "KB-001", "aventus", top=["Calabrian bergamot", "pineapple"], base=["birch", "musk"]
            ),
            product("KB-002", "clone", top=["bergamot", "pineapple"], base=["birch", "ambroxan"]),
            product("KB-003", "fresh", top=["bergamot", "lavender"], base=["musk", "vanilla"]),
            *fillers,
        ],
        NOTES,
    )
    aventus = vectors["KB-001"]

    assert similarity(aventus, vectors["KB-002"])[1] > 0.5
    assert similarity(aventus, vectors["KB-003"])[1] < 0.1
    index = NOTES.notes.index
    assert index("bergamot") not in aventus.notes
    assert aventus.notes[index("pineapple")] < aventus.notes[index("birch")]


def test_accords_match_notes_that_smell_alike() -> None:
    vectors = build_vectors(
        [
            product("KB-001", "cedar", base=["cedarwood"]),
            product("KB-002", "sandal", base=["sandalwood"]),
            product("KB-003", "vanilla", base=["vanilla"]),
        ],
        NOTES,
    )

    accords, notes = similarity(vectors["KB-001"], vectors["KB-002"])

    assert notes == 0
    assert accords > 0.8
    assert similarity(vectors["KB-001"], vectors["KB-003"])[0] < 0.1


def test_rank_orders_by_the_hybrid_score_and_keeps_one_product_per_line() -> None:
    reference = ScentVector(accords=[1.0, 0.0], notes={0: 1.0})
    candidates = [
        Candidate("KB-002", "sauvage", ScentVector([1.0, 0.0], {0: 1.0})),
        Candidate("KB-003", "sauvage", ScentVector([0.8, 0.6], {0: 1.0})),
        Candidate("KB-004", "eros", ScentVector([0.0, 1.0], {0: 1.0})),
        Candidate("KB-005", "invictus", ScentVector([0.8, 0.6], {})),
    ]

    matches = rank(reference, candidates, k=2)

    assert [match.candidate.record_id for match in matches] == ["KB-002", "KB-005"]
    assert matches[1].score == pytest.approx(0.6 * 0.8)
