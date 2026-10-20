"""Check that rephrased questions still find the record that answers them.

    python -m app.kb.eval_rephrase [--file eval/rephrase.yaml] [-k 5]

Prints a Markdown table with the rank of the first expected record for every question,
then hit@1 and hit@k. Needs Qdrant with an ingested corpus and the OpenAI API.
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import yaml
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.kb.search import Hit, search
from app.services.clients import create_openai_client, create_qdrant_client


class Case(BaseModel):
    """One question and the records that answer it."""

    question: str
    expected: list[str]


def record_rank(hits: list[Hit], expected: list[str]) -> int | None:
    """The 1-based rank of the first expected record among the hits' records, if any."""
    records = list(dict.fromkeys(hit.record_id for hit in hits))
    return next((rank for rank, rid in enumerate(records, start=1) if rid in expected), None)


async def _run(settings: Settings, cases: list[Case], k: int) -> list[list[Hit]]:
    qdrant = create_qdrant_client(settings)
    openai = create_openai_client(settings)
    try:
        return [(await search(qdrant, openai, settings, case.question, k))[0] for case in cases]
    finally:
        await openai.close()
        await qdrant.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the rephrased-question check.")
    parser.add_argument("--file", type=Path, default=Path("eval/rephrase.yaml"))
    parser.add_argument("-k", type=int, default=5, help="chunks per search (default 5)")
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(debug=settings.debug)

    cases = [Case.model_validate(item) for item in yaml.safe_load(args.file.read_text())]
    results = asyncio.run(_run(settings, cases, args.k))

    print("| # | Question | Expected | Rank | Top hit |")
    print("|---|---|---|---|---|")
    ranks = []
    for number, (case, hits) in enumerate(zip(cases, results, strict=True), start=1):
        rank = record_rank(hits, case.expected)
        ranks.append(rank)
        top = f"{hits[0].record_id} ({hits[0].score:.2f})" if hits else "—"
        expected = ", ".join(case.expected)
        print(f"| {number} | {case.question} | {expected} | {rank or 'miss'} | {top} |")
    hit_1 = sum(rank == 1 for rank in ranks)
    hit_k = sum(rank is not None for rank in ranks)
    print()
    print(f"hit@1: {hit_1}/{len(cases)} ({hit_1 / len(cases):.0%})")
    print(f"hit@{args.k}: {hit_k}/{len(cases)} ({hit_k / len(cases):.0%})")


if __name__ == "__main__":
    main()
