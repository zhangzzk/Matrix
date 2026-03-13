import tempfile
import unittest
from pathlib import Path

from dreamdive.db.migrate import PostgresMigrationRunner


class FakeCursor:
    def __init__(self, executed):
        self.executed = executed

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql):
        self.executed.append(sql)


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return FakeCursor(self.executed)

    def commit(self):
        self.commits += 1


class MigrationRunnerTests(unittest.TestCase):
    def test_runner_loads_sql_file_and_executes_it_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "schema.sql"
            path.write_text("CREATE TABLE test (id INT);", encoding="utf-8")
            connection = FakeConnection()
            runner = PostgresMigrationRunner(lambda: connection, migration_path=path)

            applied_sql = runner.apply()

            self.assertEqual(applied_sql, "CREATE TABLE test (id INT);")
            self.assertEqual(connection.executed, ["CREATE TABLE test (id INT);"])
            self.assertEqual(connection.commits, 1)


if __name__ == "__main__":
    unittest.main()
