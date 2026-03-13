from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    chunk_id: str
    text: str
    start_offset: int
    end_offset: int
    approx_token_count: int


def estimate_token_count(text: str) -> int:
    # A lightweight approximation good enough for chunk planning.
    return max(1, len(text) // 4)


def chunk_text(
    text: str,
    *,
    prefix: str,
    max_tokens: int = 5_000,
    overlap_tokens: int = 200,
) -> List[TextChunk]:
    if not text.strip():
        return []

    max_chars = max_tokens * 4
    overlap_chars = max(0, overlap_tokens * 4)
    chunks: List[TextChunk] = []

    start = 0
    while start < len(text):
        end = _find_chunk_end(text, start=start, max_chars=max_chars)
        chunk_text = text[start:end]
        chunks.append(
            TextChunk(
                chunk_id=f"{prefix}_{len(chunks) + 1:03d}",
                text=chunk_text,
                start_offset=start,
                end_offset=end,
                approx_token_count=estimate_token_count(chunk_text),
            )
        )
        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)

    return chunks


def _find_chunk_end(text: str, *, start: int, max_chars: int) -> int:
    hard_limit = min(len(text), start + max_chars)
    if hard_limit >= len(text):
        return len(text)

    soft_limit = start + max(1, max_chars // 2)
    for token in ("\n\n", "\n", "。", "！", "？", "；", ".", "!", "?", ";", " "):
        index = text.rfind(token, soft_limit, hard_limit)
        if index >= 0:
            return index + len(token)
    return hard_limit
