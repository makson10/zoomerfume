from __future__ import annotations

from app.kb.chunking import chunk_record, count_tokens


def long_body() -> str:
    sentences = " ".join(
        f"Sentence number {number} talks about delivery rules." for number in range(120)
    )
    return f"## Intro\n\nShort intro.\n\n## Delivery\n\n{sentences}\n\n## Related\n\nKB-042"


def test_a_long_section_splits_into_overlapping_chunks_under_the_limit() -> None:
    chunks = chunk_record("Test", long_body(), max_tokens=200, overlap_tokens=40)

    assert len(chunks) > 2
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(count_tokens(chunk.text) <= 200 for chunk in chunks)
    for previous, chunk in zip(chunks, chunks[1:], strict=False):
        first_line = chunk.text.split("\n\n")[0]
        assert first_line in previous.text
    assert len([chunk for chunk in chunks if "Delivery" in chunk.breadcrumb]) > 1


def test_small_sections_are_merged_with_a_breadcrumb() -> None:
    body = "## Notes\n\nBergamot.\n\n## How it wears\n\nAbout 8 hours."

    chunks = chunk_record("Creed Aventus", body)

    assert len(chunks) == 1
    assert chunks[0].breadcrumb == "Creed Aventus › Notes, How it wears"
    assert chunks[0].embed_text.startswith("Creed Aventus › Notes, How it wears\n\n## Notes")
