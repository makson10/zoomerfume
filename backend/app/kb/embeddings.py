"""Turn texts into vectors with the OpenAI embeddings API."""

from __future__ import annotations

from openai import AsyncOpenAI

# Texts per request. The API accepts up to 2,048 inputs, but smaller batches keep one
# failed request cheap to retry.
BATCH_SIZE = 100


async def embed_texts(
    client: AsyncOpenAI, texts: list[str], *, model: str, dimensions: int
) -> tuple[list[list[float]], int]:
    """Embed texts in batches.

    Transient API errors are retried by the client itself (``OPENAI_MAX_RETRIES``).

    Args:
        client: The OpenAI client.
        texts: The texts to embed.
        model: The embedding model, e.g. ``text-embedding-3-small``.
        dimensions: The vector size the model should return.

    Returns:
        The vectors in the same order as ``texts``, and the number of tokens the API billed.
    """
    vectors: list[list[float]] = []
    tokens = 0
    for start in range(0, len(texts), BATCH_SIZE):
        response = await client.embeddings.create(
            model=model, input=texts[start : start + BATCH_SIZE], dimensions=dimensions
        )
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda d: d.index))
        tokens += response.usage.total_tokens
    return vectors, tokens
