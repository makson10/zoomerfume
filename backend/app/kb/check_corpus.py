"""Consistency checks for the corpus. Needs no services and no settings.

    python -m app.kb.check_corpus [corpus_dir]

Exits with status 1 and lists the problems if any check fails.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from app.kb.corpus import CorpusError, Record, load_corpus

# Zoomer Points on a product card: 5% of the price, rounded down.
POINTS_PERCENT = 5
# 2 ml samples (designer and niche) may appear next to any product.
SAMPLE_PRICES = {69, 119}

_REFERENCE = re.compile(r"\bKB-\d{3}\b")
_AMOUNT = re.compile(r"(\d[\d,]*) ₴")
_DOMAIN = re.compile(r"\b(?:[\w-]+\.)+(?:com|net|org|io|ua|eu|example)\b", re.IGNORECASE)


def check(records: list[Record]) -> list[str]:
    """Return a description of every problem found in the records."""
    problems: list[str] = []
    ids = {record.header.id for record in records}
    product_prices = {
        record.header.id: {size.price for size in record.header.sizes}
        | ({record.header.decant.price} if record.header.decant else set())
        for record in records
        if record.header.type == "product"
    }
    for record in records:
        record_id = record.header.id
        for size in [*record.header.sizes, *filter(None, [record.header.decant])]:
            if size.points != size.price * POINTS_PERCENT // 100:
                problems.append(f"{record_id}: {size.ml} ml earns {size.points} points")
        for reference in set(_REFERENCE.findall(record.body)) - ids:
            problems.append(f"{record_id}: links to {reference}, which doesn't exist")
        if "[KB-" in record.body:
            problems.append(f"{record_id}: a record id in square brackets looks like a citation")
        for line in record.body.splitlines():
            linked = set(_REFERENCE.findall(line)) & product_prices.keys()
            if len(linked) == 1 and (product := linked.pop()) != record_id:
                for amount in _AMOUNT.findall(line):
                    price = int(amount.replace(",", ""))
                    if price not in product_prices[product] | SAMPLE_PRICES:
                        problems.append(f"{record_id}: {price:,} ₴ isn't a price of {product}")
        for domain in _DOMAIN.findall(record.body):
            if not domain.lower().endswith(".example"):
                problems.append(f"{record_id}: {domain} isn't on a .example domain")
        if re.search("[\u0400-\u04ff]", record.body):
            problems.append(f"{record_id}: contains Cyrillic text")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Check the corpus for consistency.")
    parser.add_argument("corpus_dir", nargs="?", type=Path, default=Path("corpus"))
    args = parser.parse_args()
    try:
        records = load_corpus(args.corpus_dir)
    except CorpusError as exc:
        sys.exit(f"Corpus error: {exc}")
    problems = check(records)
    words = Counter[str]()
    counts = Counter(record.header.type for record in records)
    for record in records:
        words[record.header.type] += len(record.body.split())
    for record_type, count in sorted(counts.items()):
        print(f"{record_type}: {count} records, {words[record_type]:,} words")
    print(f"total: {len(records)} records, {sum(words.values()):,} words")
    for problem in problems:
        print(f"PROBLEM {problem}")
    if problems:
        sys.exit(1)


if __name__ == "__main__":
    main()
