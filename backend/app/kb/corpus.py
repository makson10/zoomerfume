"""Read knowledge base records from the corpus folder.

Each record is one ``KB-NNN.md`` file: a YAML front-matter header between ``---`` lines,
then a Markdown body.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

RecordType = Literal["product", "policy", "company", "faq", "news"]
Availability = Literal["in_stock", "few_left", "pre_order", "discontinued"]

PRODUCT_FIELDS = ("brand", "concentration", "family", "gender", "seasons", "availability")


class CorpusError(ValueError):
    """A record file that can't be parsed."""


class Size(BaseModel):
    """One bottle size of a product, or its decant."""

    model_config = ConfigDict(extra="forbid")

    ml: int = Field(gt=0)
    price: int = Field(gt=0)
    points: int = Field(ge=0)


class RecordHeader(BaseModel):
    """The front matter of a record. The product fields are required for products only."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^KB-\d{3}$")
    title: str = Field(min_length=1)
    type: RecordType
    updated: date
    brand: str | None = None
    concentration: str | None = None
    family: str | None = None
    gender: Literal["men", "women", "unisex"] | None = None
    seasons: list[str] | None = None
    sizes: list[Size] = []
    decant: Size | None = None
    availability: Availability | None = None

    @model_validator(mode="after")
    def _check_product_fields(self) -> RecordHeader:
        if self.type != "product":
            return self
        missing = [name for name in PRODUCT_FIELDS if getattr(self, name) is None]
        if missing:
            raise ValueError(f"a product needs {', '.join(missing)}")
        if not self.sizes and self.availability != "discontinued":
            raise ValueError("only a discontinued product can have no sizes")
        return self

    @property
    def price(self) -> int | None:
        """The cheapest bottle's price; None when there are no sizes."""
        return min((size.price for size in self.sizes), default=None)


@dataclass(frozen=True)
class Record:
    """One parsed record file."""

    header: RecordHeader
    body: str
    source: str
    content_hash: str


def parse_record(path: Path) -> Record:
    """Parse one record file.

    Raises:
        CorpusError: The file has no front matter, the header is invalid, the id
            doesn't match the file name, or the body is empty.
    """
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise CorpusError(f"{path.name}: no front matter")
    _, front, body = text.split("---\n", 2)
    try:
        header = RecordHeader.model_validate(yaml.safe_load(front))
    except (yaml.YAMLError, ValidationError) as exc:
        raise CorpusError(f"{path.name}: {exc}") from exc
    if path.name != f"{header.id}.md":
        raise CorpusError(f"{path.name}: the id {header.id} doesn't match the file name")
    body = body.strip()
    if not body:
        raise CorpusError(f"{path.name}: the body is empty")
    return Record(
        header=header,
        body=body,
        source=path.name,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def load_corpus(corpus_dir: Path) -> list[Record]:
    """Parse every ``KB-*.md`` file in the folder, ordered by id."""
    return [parse_record(path) for path in sorted(corpus_dir.glob("KB-*.md"))]
