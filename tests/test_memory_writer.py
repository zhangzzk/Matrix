import unittest

from dreamdive.db.queries import EpisodicMemoryRepository
from dreamdive.db.session import InMemoryStore
from dreamdive.memory.retrieval import embed_text
from dreamdive.schemas import ReplayKey
from dreamdive.simulation.memory_writer import MemoryWriter


class MemoryWriterTests(unittest.TestCase):
    def test_memory_writer_truncates_and_clamps_salience(self) -> None:
        writer = MemoryWriter(max_summary_length=20)
        memory = writer.build_memory(
            character_id="arya",
            replay_key=ReplayKey(tick="day_1", timeline_index=1),
            event_id="evt_001",
            participants=["arya"],
            location="yard",
            summary="This is a much longer summary than the configured maximum.",
            emotional_tag="fear",
            salience=1.5,
        )

        self.assertEqual(memory.summary, "This is a much lo...")
        self.assertEqual(memory.salience, 1.0)
        self.assertIsNotNone(memory.embedding)

    def test_memory_repository_embeds_on_write_and_returns_embedding(self) -> None:
        memory = MemoryWriter().build_memory(
            character_id="arya",
            replay_key=ReplayKey(tick="day_1", timeline_index=1),
            event_id="evt_001",
            participants=["arya", "sansa"],
            location="yard",
            summary="Arya hid the letter in the yard wall.",
            emotional_tag="fear",
            salience=0.6,
        )
        repo = EpisodicMemoryRepository(InMemoryStore())

        repo.append(memory)
        stored = repo.list_for_character("arya")

        self.assertEqual(len(stored), 1)
        self.assertIsNotNone(stored[0].embedding)
        self.assertEqual(len(stored[0].embedding), 1536)

    def test_memory_repository_supports_semantic_search_and_pinned_lookup(self) -> None:
        repo = EpisodicMemoryRepository(InMemoryStore())
        pinned = MemoryWriter().build_memory(
            character_id="arya",
            replay_key=ReplayKey(tick="day_1", timeline_index=1),
            event_id="evt_pinned",
            participants=["arya"],
            location="yard",
            summary="Never forget the warning in the yard.",
            emotional_tag="fear",
            salience=0.9,
            pinned=True,
        )
        relevant = MemoryWriter().build_memory(
            character_id="arya",
            replay_key=ReplayKey(tick="day_2", timeline_index=2),
            event_id="evt_letter",
            participants=["arya", "sansa"],
            location="yard",
            summary="Sansa hid the letter in the yard wall.",
            emotional_tag="focus",
            salience=0.5,
        )
        irrelevant = MemoryWriter().build_memory(
            character_id="arya",
            replay_key=ReplayKey(tick="day_3", timeline_index=3),
            event_id="evt_kitchen",
            participants=["cook"],
            location="kitchen",
            summary="The cook burned the bread in the kitchen.",
            emotional_tag="annoyance",
            salience=0.7,
        )
        repo.append(pinned)
        repo.append(relevant)
        repo.append(irrelevant)

        results = repo.search_semantic_for_character(
            "arya",
            query_embedding=embed_text("yard letter sansa"),
            limit=1,
            timeline_index=3,
        )
        pinned_results = repo.list_pinned_for_character("arya", timeline_index=3)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].event_id, "evt_letter")
        self.assertEqual([memory.event_id for memory in pinned_results], ["evt_pinned"])


if __name__ == "__main__":
    unittest.main()
