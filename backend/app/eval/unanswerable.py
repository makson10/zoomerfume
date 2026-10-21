"""Ask questions the knowledge base can't answer and check that Zoomer says so.

    python -m app.eval.unanswerable [--file eval/unanswerable.yaml]

A question passes when the reply says that Zoomer doesn't know, in one of the
:data:`DONT_KNOW` phrasings. The table also lists the tools and the valid citations: a
reply may cite a related rule next to the admission (the support hours, for example), so
a citation alone doesn't fail a question. The checks are plain string checks; no model
judges the replies. Exits with status 1 if a question fails. Needs the stack and the
OpenAI API.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

from app.agent.runtime import TurnResult
from app.core.config import Settings, get_settings
from app.eval.turns import ask, running_app

# Ways the prompt's "I don't have information about that" rule comes out, lowercase.
DONT_KNOW = (
    "don't have",
    "do not have",
    "don't know",
    "not sure",
    "no information",
    "can't find",
    "couldn't find",
)


def says_it_doesnt_know(reply: str) -> bool:
    """True when the reply admits that the knowledge base doesn't answer the question."""
    text = reply.lower().replace("’", "'")
    return any(phrase in text for phrase in DONT_KNOW)


async def _run(settings: Settings, questions: list[str]) -> list[TurnResult]:
    async with running_app(settings) as app:
        return [await ask(app, question) for question in questions]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the unanswerable-question check.")
    parser.add_argument("--file", type=Path, default=Path("eval/unanswerable.yaml"))
    args = parser.parse_args()
    questions: list[str] = yaml.safe_load(args.file.read_text())

    results = asyncio.run(_run(get_settings(), questions))

    print("| # | Question | Tools | Valid citations | Says it doesn't know | Result |")
    print("|---|---|---|---|---|---|")
    passed = 0
    for number, (question, result) in enumerate(zip(questions, results, strict=True), start=1):
        tools = ", ".join(step.tool for step in result.steps) or "none"
        valid = ", ".join(result.citations.valid) or "none"
        admits = says_it_doesnt_know(result.reply)
        passed += admits
        verdict = "pass" if admits else "FAIL"
        print(f"| {number} | {question} | {tools} | {valid} | {admits} | {verdict} |")
    print()
    print(f"passed: {passed}/{len(questions)}")
    if passed < len(questions):
        sys.exit(1)


if __name__ == "__main__":
    main()
