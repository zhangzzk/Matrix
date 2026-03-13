import unittest
from pathlib import Path


class MigrationSchemaTests(unittest.TestCase):
    def test_initial_schema_includes_notion_core_tables_and_pgvector(self) -> None:
        migration = Path("migrations/0001_initial_schema.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE EXTENSION IF NOT EXISTS vector;", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS state_change_log", migration)
        self.assertIn("idempotency_key TEXT NOT NULL UNIQUE", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS goal_stack", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS relationship_log", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS episodic_memory", migration)
        self.assertIn("embedding VECTOR(1536)", migration)
        self.assertIn("CREATE INDEX IF NOT EXISTS idx_entity_embedding", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS event_log", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS entity", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS entity_representation", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS simulation_session", migration)


if __name__ == "__main__":
    unittest.main()
