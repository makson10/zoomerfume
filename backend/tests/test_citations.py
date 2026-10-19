from __future__ import annotations

import pytest

from app.agent.citations import Citations, check_citations


def test_sorts_citations_into_valid_and_invalid() -> None:
    answer = "Soft [KB-012], cheap [KB-031], rare [KB-099], soft again [KB-012], see KB-040."

    citations = check_citations(answer, retrieved_now={"KB-012"}, retrieved_before={"KB-031"})

    assert citations == Citations(valid=["KB-012", "KB-031"], invalid=["KB-099"], missing=False)


@pytest.mark.parametrize(
    ("answer", "now", "before", "missing"),
    [
        ("No citations at all.", {"KB-012"}, set(), True),
        ("Only an older record [KB-031].", {"KB-012"}, {"KB-031"}, True),
        ("A follow-up [KB-031].", set(), {"KB-031"}, False),
        ("EDP lasts longer than EDT.", set(), set(), False),
    ],
    ids=["nothing-cited", "only-older-cited", "follow-up", "no-lookup"],
)
def test_flags_an_answer_that_cites_none_of_this_turns_records(
    answer: str, now: set[str], before: set[str], missing: bool
) -> None:
    assert check_citations(answer, now, before).missing is missing
