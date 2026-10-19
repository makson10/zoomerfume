from __future__ import annotations

from app.kb.chunking import chunk_record, count_tokens


def long_body() -> str:
    sentences = " ".join(f"Sentence number {n} talks about delivery rules." for n in range(120))
    return f"## Intro\n\nShort intro.\n\n## Delivery\n\n{sentences}\n\n## Related\n\nKB-042"


def test_chunks_stay_under_the_limit_and_overlap() -> None:
    chunks = chunk_record("Test", long_body(), max_tokens=200, overlap_tokens=40)

    assert len(chunks) > 2
    assert [chunk.index for chunk in chunks] == list(range(len(chunks)))
    assert all(count_tokens(chunk.text) <= 200 for chunk in chunks)
    for previous, chunk in zip(chunks, chunks[1:], strict=False):
        first_line = chunk.text.split("\n\n")[0]
        assert first_line in previous.text


def test_small_sections_are_merged_with_a_breadcrumb() -> None:
    body = "## Notes\n\nBergamot.\n\n## How it wears\n\nAbout 8 hours."

    chunks = chunk_record("Creed Aventus", body)

    assert len(chunks) == 1
    assert chunks[0].breadcrumb == "Creed Aventus › Notes, How it wears"
    assert chunks[0].embed_text.startswith("Creed Aventus › Notes, How it wears\n\n## Notes")


def test_a_split_section_keeps_its_heading_in_every_breadcrumb() -> None:
    chunks = chunk_record("Test", long_body(), max_tokens=200, overlap_tokens=40)

    delivery = [chunk for chunk in chunks if "Delivery" in chunk.breadcrumb]
    assert len(delivery) > 1


def test_chunking_is_deterministic() -> None:
    assert chunk_record("Test", long_body()) == chunk_record("Test", long_body())
