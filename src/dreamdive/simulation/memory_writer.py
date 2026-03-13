from __future__ import annotations

from dataclasses import dataclass
from typing import List

from dreamdive.memory.retrieval import embed_text
from dreamdive.schemas import EpisodicMemory, ReplayKey


@dataclass
class MemoryWriter:
    max_summary_length: int = 280

    def build_memory(
        self,
        *,
        character_id: str,
        replay_key: ReplayKey,
        event_id: str,
        participants: List[str],
        location: str,
        summary: str,
        emotional_tag: str,
        salience: float,
        pinned: bool = False,
    ) -> EpisodicMemory:
        normalized = " ".join(summary.split()).strip()
        if len(normalized) > self.max_summary_length:
            normalized = normalized[: self.max_summary_length - 3].rstrip() + "..."
        return EpisodicMemory(
            character_id=character_id,
            replay_key=replay_key,
            event_id=event_id,
            participants=participants,
            location=location,
            summary=normalized,
            emotional_tag=emotional_tag,
            salience=max(0.0, min(1.0, salience)),
            pinned=pinned,
            compressed=False,
            embedding=embed_text(" ".join(part for part in (normalized, location, emotional_tag) if part)),
        )
