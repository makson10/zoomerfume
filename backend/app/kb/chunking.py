"""Split a record into chunks of about 500 tokens for embedding.

Sections (``## `` headings) are the units. Small neighbouring sections are packed into one
chunk, and a section too big for a chunk is split on paragraphs, then sentences. Every chunk
after the first starts with the last ~75 tokens of the chunk before it, so text near a
boundary is found from either side. Tokens are counted with ``cl100k_base``, the tokenizer of
the embedding model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

import tiktoken

MAX_TOKENS = 500
OVERLAP_TOKENS = 75

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    """One piece of a record, ready to embed."""

    index: int
    # "Creed Aventus › Notes, How it wears": the record title and the sections inside.
    breadcrumb: str
    text: str
    tokens: int

    @property
    def embed_text(self) -> str:
        """The text that gets embedded: the breadcrumb line, then the chunk."""
        return f"{self.breadcrumb}\n\n{self.text}"


@dataclass(frozen=True)
class _Piece:
    heading: str | None
    text: str


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    """Count tokens the way the embedding model does."""
    return len(_encoding().encode(text))


def chunk_record(
    title: str,
    body: str,
    *,
    max_tokens: int = MAX_TOKENS,
    overlap_tokens: int = OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split a record body into chunks of at most ``max_tokens`` tokens.

    The result depends only on the input, so a re-run produces the same chunks.

    Args:
        title: The record title, used in every chunk's breadcrumb.
        body: The Markdown body of the record.
        max_tokens: The size limit for a chunk's text, overlap included.
        overlap_tokens: How much of the previous chunk a chunk starts with.
    """
    budget = max_tokens - overlap_tokens
    pieces = [
        piece
        for heading, text in _split_sections(body)
        for piece in _section_pieces(heading, text, budget)
    ]
    groups: list[list[_Piece]] = []
    for piece in pieces:
        if groups and count_tokens(_join(groups[-1] + [piece])) <= budget:
            groups[-1].append(piece)
        else:
            groups.append([piece])

    chunks: list[Chunk] = []
    for index, group in enumerate(groups):
        text = _join(group)
        if chunks:
            text = f"{_tail(chunks[-1].text, overlap_tokens - 1)}\n\n{text}"
        headings = list(dict.fromkeys(piece.heading for piece in group if piece.heading))
        breadcrumb = f"{title} › {', '.join(headings)}" if headings else title
        chunks.append(Chunk(index, breadcrumb, text, count_tokens(text)))
    return chunks


def _split_sections(body: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if heading or "".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading, lines = line[3:].strip(), []
        else:
            lines.append(line)
    if heading or "".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def _section_pieces(heading: str | None, text: str, budget: int) -> list[_Piece]:
    full = f"## {heading}\n\n{text}" if heading else text
    if count_tokens(full) <= budget:
        return [_Piece(heading, full)]
    pieces: list[_Piece] = []
    current: list[str] = []
    for unit in _units(full, budget):
        if current and count_tokens("\n\n".join(current + [unit])) > budget:
            pieces.append(_Piece(heading, "\n\n".join(current)))
            current = []
        current.append(unit)
    pieces.append(_Piece(heading, "\n\n".join(current)))
    return pieces


def _units(text: str, budget: int) -> list[str]:
    """Paragraphs that fit the budget, else their sentences, else token windows."""
    units: list[str] = []
    for paragraph in (block.strip() for block in text.split("\n\n") if block.strip()):
        if count_tokens(paragraph) <= budget:
            units.append(paragraph)
            continue
        for sentence in _SENTENCE_END.split(paragraph):
            tokens = _encoding().encode(sentence)
            for start in range(0, len(tokens), budget):
                units.append(_encoding().decode(tokens[start : start + budget]))
    return units


def _tail(text: str, max_tokens: int) -> str:
    """The end of a text, at most ``max_tokens`` long, starting at a sentence or word."""
    tokens = _encoding().encode(text)
    if len(tokens) <= max_tokens:
        return text
    tail = _encoding().decode(tokens[-max_tokens:])
    for separator in ("\n", ". ", " "):
        cut = tail.find(separator)
        if 0 <= cut < len(tail) // 2:
            return tail[cut + len(separator) :].strip()
    return tail.strip()


def _join(pieces: list[_Piece]) -> str:
    return "\n\n".join(piece.text for piece in pieces)
