from __future__ import annotations

from pathlib import Path

import pytest

from app.kb.check_corpus import check
from app.kb.corpus import CorpusError, load_corpus, parse_record

CORPUS_DIR = Path(__file__).parents[1] / "corpus"

PRODUCT = """---
id: KB-001
title: Test Perfume
type: product
updated: 2026-05-01
brand: Test
concentration: EDP
family: woody
gender: unisex
seasons: [autumn]
sizes:
  - {ml: 100, price: 4990, points: 249}
  - {ml: 50, price: 2990, points: 149}
availability: in_stock
---

## Overview

A test product.
"""


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text)
    return path


def test_parse_record_reads_header_and_body(tmp_path: Path) -> None:
    record = parse_record(write(tmp_path, "KB-001.md", PRODUCT))

    assert record.header.title == "Test Perfume"
    assert record.header.price == 2990
    assert record.body.startswith("## Overview")
    assert len(record.content_hash) == 64


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("KB-002.md", PRODUCT),
        ("KB-001.md", PRODUCT.replace("brand: Test\n", "")),
        ("KB-001.md", "## Overview\n\nNo front matter.\n"),
    ],
    ids=["id-not-file-name", "product-without-brand", "no-front-matter"],
)
def test_parse_record_rejects_bad_files(tmp_path: Path, name: str, text: str) -> None:
    with pytest.raises(CorpusError):
        parse_record(write(tmp_path, name, text))


def test_check_flags_a_wrong_price_and_a_missing_link(tmp_path: Path) -> None:
    write(tmp_path, "KB-001.md", PRODUCT)
    faq = PRODUCT.split("brand:")[0].replace("KB-001", "KB-002").replace("product", "faq")
    write(tmp_path, "KB-002.md", faq + "---\n\nTest Perfume (KB-001) costs 3,500 ₴. See KB-099.\n")

    problems = check(load_corpus(tmp_path))

    assert any("3,500 ₴ isn't a price of KB-001" in problem for problem in problems)
    assert any("KB-099" in problem for problem in problems)


def test_shipped_corpus_passes_the_checks() -> None:
    records = load_corpus(CORPUS_DIR)

    assert records
    assert check(records) == []
