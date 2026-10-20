"""The token usage and cost of model calls, per call and per turn."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, PlainSerializer

from app.db.models import LlmCall
from app.services.pricing import call_cost

# A chat model call of the agent loop, or an embeddings call.
CallKind = Literal["chat", "embedding"]
# A dollar amount in JSON: a string in plain notation, e.g. "0.000065500", never "6.55E-5".
Usd = Annotated[Decimal, PlainSerializer(lambda value: f"{value:f}", return_type=str)]


@dataclass(frozen=True)
class CallUsage:
    """The tokens one model call used, as the API reported them."""

    kind: CallKind
    model: str
    input_tokens: int
    cached_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0

    @property
    def cost_usd(self) -> Decimal:
        return call_cost(
            self.model,
            self.input_tokens,
            self.cached_tokens,
            self.cache_write_tokens,
            self.output_tokens,
        )

    def as_row(self, turn_id: uuid.UUID | None = None) -> LlmCall:
        """Return the call as an ``llm_calls`` row, priced now."""
        return LlmCall(
            turn_id=turn_id,
            kind=self.kind,
            model=self.model,
            input_tokens=self.input_tokens,
            cached_tokens=self.cached_tokens,
            cache_write_tokens=self.cache_write_tokens,
            output_tokens=self.output_tokens,
            cost_usd=self.cost_usd,
        )


class TurnUsage(BaseModel):
    """What one turn's model calls used and cost.

    The calls and tokens are the chat model's. The cost also covers the embeddings of the
    turn's searches.
    """

    calls: int
    input_tokens: int
    cached_tokens: int
    cache_write_tokens: int
    output_tokens: int
    cost_usd: Usd

    @classmethod
    def of(cls, calls: Sequence[CallUsage | LlmCall]) -> TurnUsage:
        """Sum up a turn's calls, from the turn itself or from the ``llm_calls`` table."""
        chat = [call for call in calls if call.kind == "chat"]
        return cls(
            calls=len(chat),
            input_tokens=sum(call.input_tokens for call in chat),
            cached_tokens=sum(call.cached_tokens for call in chat),
            cache_write_tokens=sum(call.cache_write_tokens for call in chat),
            output_tokens=sum(call.output_tokens for call in chat),
            cost_usd=sum((call.cost_usd for call in calls), Decimal(0)),
        )
