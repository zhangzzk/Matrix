from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from dreamdive.schemas import EpisodicMemory, ReplayKey


@dataclass
class CompressionResult:
    retained: List[EpisodicMemory]
    compressed: List[EpisodicMemory]
    discarded_ids: List[str]


class MemoryConsolidator:
    def __init__(
        self,
        *,
        compression_interval_ticks: int = 15,
        high_salience_threshold: float = 0.7,
        discard_threshold: float = 0.2,
    ) -> None:
        self.compression_interval_ticks = compression_interval_ticks
        self.high_salience_threshold = high_salience_threshold
        self.discard_threshold = discard_threshold

    def consolidate(
        self,
        memories: List[EpisodicMemory],
        *,
        current_timeline_index: int,
    ) -> CompressionResult:
        retained: List[EpisodicMemory] = []
        candidates: List[EpisodicMemory] = []
        discarded_ids: List[str] = []

        for memory in memories:
            age = current_timeline_index - memory.replay_key.timeline_index
            if memory.pinned or memory.compressed or age < self.compression_interval_ticks:
                retained.append(memory)
                continue
            if memory.salience >= self.high_salience_threshold:
                retained.append(memory)
                continue
            if memory.salience <= self.discard_threshold:
                discarded_ids.append(memory.event_id or memory.summary)
                continue
            candidates.append(memory)

        compressed = self._compress_candidates(candidates)
        retained.extend(compressed)
        retained.sort(key=lambda item: (item.replay_key.timeline_index, item.summary))
        return CompressionResult(retained=retained, compressed=compressed, discarded_ids=discarded_ids)

    def _compress_candidates(self, memories: List[EpisodicMemory]) -> List[EpisodicMemory]:
        grouped: Dict[str, List[EpisodicMemory]] = {}
        for memory in memories:
            grouped.setdefault(memory.character_id, []).append(memory)

        compressed: List[EpisodicMemory] = []
        for character_id, items in grouped.items():
            if not items:
                continue
            items = sorted(items, key=lambda item: item.replay_key.timeline_index)
            replay_key = ReplayKey(
                tick=items[-1].replay_key.tick,
                timeline_index=items[-1].replay_key.timeline_index,
                event_sequence=items[-1].replay_key.event_sequence,
            )
            summary = self._build_summary(items)
            compressed.append(
                EpisodicMemory(
                    character_id=character_id,
                    replay_key=replay_key,
                    event_id="compressed:{}:{}".format(character_id, replay_key.timeline_index),
                    participants=sorted({p for item in items for p in item.participants}),
                    location=items[-1].location,
                    summary=summary,
                    emotional_tag=items[-1].emotional_tag,
                    salience=max(item.salience for item in items),
                    pinned=False,
                    compressed=True,
                )
            )
        return compressed

    @staticmethod
    def _build_summary(memories: List[EpisodicMemory]) -> str:
        first = memories[0].summary
        last = memories[-1].summary
        return "Compressed memory of {} events: {} ... {}".format(
            len(memories),
            first,
            last,
        )
