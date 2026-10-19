"""Load the corpus into Qdrant and the ``kb_records`` table.

    python -m app.kb.ingest [--force] [--dry-run]

A record whose file hasn't changed since the last run is skipped, so a re-run embeds
nothing. Records removed from the corpus are deleted from both stores.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.logging import setup_logging
from app.db.engine import create_db_engine
from app.kb.chunking import chunk_record, count_tokens
from app.kb.corpus import load_corpus
from app.kb.embeddings import embed_texts
from app.kb.records import delete_records, save_record, stored_hashes
from app.kb.store import (
    delete_record_chunks,
    ensure_collection,
    replace_record_chunks,
    wait_until_indexed,
)
from app.services.clients import create_openai_client, create_qdrant_client


@dataclass
class IngestSummary:
    """What one ingest run did. ``points`` and ``indexed`` are None for a dry run."""

    records: int
    changed: int
    deleted: int
    chunks: int
    tokens: int
    points: int | None = None
    indexed: int | None = None


async def ingest(
    settings: Settings, *, force: bool = False, dry_run: bool = False
) -> IngestSummary:
    """Embed new and changed records, and delete records that left the corpus.

    Args:
        settings: The app settings (corpus folder, Qdrant collection, embedding model).
        force: Re-embed every record, even unchanged ones.
        dry_run: Only report what would change. No embedding calls and no writes; the
            token count is our own estimate.
    """
    records = load_corpus(settings.corpus_dir)
    engine = create_db_engine(settings)
    qdrant = create_qdrant_client(settings)
    openai = create_openai_client(settings)
    collection = settings.qdrant_collection
    try:
        async with AsyncSession(engine) as session:
            hashes = await stored_hashes(session)
            if not dry_run and await ensure_collection(
                qdrant, collection, settings.embedding_dimensions
            ):
                force = True
            changed = [r for r in records if force or hashes.get(r.header.id) != r.content_hash]
            removed = sorted(set(hashes) - {r.header.id for r in records})
            chunked = [(r, chunk_record(r.header.title, r.body)) for r in changed]
            summary = IngestSummary(
                records=len(records),
                changed=len(changed),
                deleted=len(removed),
                chunks=sum(len(chunks) for _, chunks in chunked),
                tokens=0,
            )
            if dry_run:
                summary.tokens = sum(
                    count_tokens(chunk.embed_text) for _, chunks in chunked for chunk in chunks
                )
                return summary

            for record, chunks in chunked:
                if not chunks:
                    continue
                vectors, tokens = await embed_texts(
                    openai,
                    [chunk.embed_text for chunk in chunks],
                    model=settings.embedding_model,
                    dimensions=settings.embedding_dimensions,
                )
                summary.tokens += tokens
                await replace_record_chunks(qdrant, collection, record, chunks, vectors)
                await save_record(session, record)
            for record_id in removed:
                await delete_record_chunks(qdrant, collection, record_id)
            await delete_records(session, removed)
            await session.commit()

        info = await wait_until_indexed(qdrant, collection)
        summary.points = info.points_count
        summary.indexed = info.indexed_vectors_count
        return summary
    finally:
        await openai.close()
        await qdrant.close()
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Load the corpus into Qdrant and Postgres.")
    parser.add_argument(
        "--force", action="store_true", help="re-embed every record, even unchanged ones"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change, write nothing"
    )
    args = parser.parse_args()
    settings = get_settings()
    setup_logging(debug=settings.debug)

    summary = asyncio.run(ingest(settings, force=args.force, dry_run=args.dry_run))
    verb = "would embed" if args.dry_run else "embedded"
    print(
        f"Records: {summary.records} total, {summary.changed} changed, "
        f"{summary.records - summary.changed} skipped, {summary.deleted} deleted"
    )
    print(f"Chunks: {summary.chunks} {verb}, {summary.tokens:,} tokens")
    if summary.points is not None:
        print(
            f"Qdrant {settings.qdrant_collection}: {summary.points} points, "
            f"{summary.indexed} indexed vectors (HNSW)"
        )


if __name__ == "__main__":
    main()
