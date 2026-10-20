"""Check the ``[KB-042]`` citations in Zoomer's answers against the records it retrieved."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict

# Zoomer cites a record by its id in square brackets, e.g. "[KB-042]".
CITATION = re.compile(r"\[(KB-\d{3})\]")


class Citations(BaseModel):
    """The citations of one answer, checked against the records the tools returned.

    ``Citations()`` is an answer that cites nothing.
    """

    # Every field is in the output, so the schema marks the defaulted ones required too.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)

    # Cited records that a tool returned in this conversation, in the order first cited.
    valid: list[str] = []
    # Cited ids that no tool returned in this conversation.
    invalid: list[str] = []
    # True when this turn retrieved records and the answer cites none of them.
    missing: bool = False


def check_citations(answer: str, retrieved_now: set[str], retrieved_before: set[str]) -> Citations:
    """Sort an answer's citations into valid and invalid ones, and flag missing citations.

    A follow-up answered from records found earlier in the conversation keeps valid
    citations without a new search.

    Args:
        answer: Zoomer's reply.
        retrieved_now: Records the tools returned in this turn.
        retrieved_before: Records the tools returned in earlier turns of the conversation.
    """
    cited = list(dict.fromkeys(CITATION.findall(answer)))
    known = retrieved_now | retrieved_before
    return Citations(
        valid=[record_id for record_id in cited if record_id in known],
        invalid=[record_id for record_id in cited if record_id not in known],
        missing=bool(retrieved_now) and not retrieved_now.intersection(cited),
    )
