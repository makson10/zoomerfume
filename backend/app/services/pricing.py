"""Model prices and the cost of one model call."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

TOKENS_PER_PRICE_UNIT = Decimal(1_000_000)
# Prices per million tokens have at most three decimals, so every cost is exact to nine
# places, the scale of ``llm_calls.cost_usd``.
COST_STEP = Decimal("0.000000001")


@dataclass(frozen=True)
class ModelPrices:
    """A model's prices in USD per million tokens."""

    input: Decimal
    cached_input: Decimal = Decimal(0)
    cache_write: Decimal = Decimal(0)
    output: Decimal = Decimal(0)


# From the OpenAI pricing page. Cache writes cost 1.25× the input price.
PRICES = {
    "gpt-6-luna": ModelPrices(
        input=Decimal("0.10"),
        cached_input=Decimal("0.01"),
        cache_write=Decimal("0.125"),
        output=Decimal("0.50"),
    ),
    "text-embedding-3-small": ModelPrices(input=Decimal("0.02")),
}


def call_cost(
    model: str,
    input_tokens: int,
    cached_tokens: int = 0,
    cache_write_tokens: int = 0,
    output_tokens: int = 0,
) -> Decimal:
    """Return the USD cost of one model call.

    ``input_tokens`` counts every input token. The cached ones and the ones written to the
    cache each have their own rate, and the rest are billed at the full input rate.

    Args:
        model: The model's name, a key of :data:`PRICES`. A model without a price costs 0,
            with a warning in the log.
        input_tokens: All input tokens, as the API reports them.
        cached_tokens: Input tokens read from the prompt cache.
        cache_write_tokens: Input tokens written to the prompt cache.
        output_tokens: Output tokens, reasoning included.
    """
    prices = PRICES.get(model)
    if prices is None:
        logger.warning("no price for model %s, its calls cost 0", model)
        return Decimal(0)
    uncached = input_tokens - cached_tokens - cache_write_tokens
    total = (
        uncached * prices.input
        + cached_tokens * prices.cached_input
        + cache_write_tokens * prices.cache_write
        + output_tokens * prices.output
    )
    return (total / TOKENS_PER_PRICE_UNIT).quantize(COST_STEP)
