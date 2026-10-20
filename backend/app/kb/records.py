"""The ``kb_records`` table: full records for lookups, and content hashes for ingest."""

from __future__ import annotations

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import KbRecord
from app.kb.corpus import Record


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


async def delete_records(session: AsyncSession, record_ids: list[str]) -> None:
    """Delete records that are no longer in the corpus."""
    if record_ids:
        await session.execute(delete(KbRecord).where(KbRecord.id.in_(record_ids)))
