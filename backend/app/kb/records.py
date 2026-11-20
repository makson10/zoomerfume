"""The ``kb_records`` table: full records for lookups by id or product name, and content
hashes for ingest."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KbRecord
from app.kb.corpus import Record

# The pg_trgm word similarity a name needs to match a product title, from 0 to 1. Names of
# perfumes we don't sell that share words with ours, like "Invictus Victory", score up to 0.6.
MIN_NAME_SIMILARITY = 0.7


async def stored_hashes(session: AsyncSession) -> dict[str, str]:
    """Map every stored record id to the content hash it was ingested with."""
    rows = await session.execute(select(KbRecord.id, KbRecord.content_hash))
    return {record_id: content_hash for record_id, content_hash in rows.all()}


async def save_record(session: AsyncSession, record: Record) -> None:
    """Insert a record, or overwrite the stored one with the same id."""
    header = record.header
    values = {
        "id": header.id,
        "title": header.title,
        "type": header.type,
        "source": record.source,
        "updated": header.updated,
        "header": header.model_dump(mode="json", exclude_none=True),
        "body": record.body,
        "content_hash": record.content_hash,
    }
    stmt = insert(KbRecord).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[KbRecord.id],
        set_={**values, "ingested_at": func.now()},
    )
    await session.execute(stmt)


async def find_product(session: AsyncSession, name: str) -> KbRecord | None:
    """Return the product whose title matches the name best, or None when none is close.

    Uses pg_trgm's word similarity, so a part of the title ("aventus") still matches. Of
    equal matches, as "Sauvage" is for all three Sauvage cards, the lowest record id wins.
    """
    word_match = func.word_similarity(name, KbRecord.title)
    stmt = (
        select(KbRecord)
        .where(KbRecord.type == "product", word_match >= MIN_NAME_SIMILARITY)
        .order_by(word_match.desc(), KbRecord.id)
        .limit(1)
    )
    return await session.scalar(stmt)


async def delete_records(session: AsyncSession, record_ids: list[str]) -> None:
    """Delete records that are no longer in the corpus."""
    if record_ids:
        await session.execute(delete(KbRecord).where(KbRecord.id.in_(record_ids)))
