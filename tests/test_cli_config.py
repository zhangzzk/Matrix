import argparse
import tempfile
import unittest
from pathlib import Path

from dreamdive.cli_config import (
    apply_cli_config,
    load_cli_config,
    parse_simple_toml,
    resolve_cli_config_path,
)


class CliConfigTests(unittest.TestCase):
    def test_parse_simple_toml_supports_sections_and_scalars(self) -> None:
        data = parse_simple_toml(
            """
            [defaults]
            workspace = ".dreamdive"
            debug = true

            [profiles.main]
            session_id = "main"

            [profiles.main.run]
            ticks = 10
            """
        )

        self.assertEqual(data["defaults"]["workspace"], ".dreamdive")
        self.assertEqual(data["defaults"]["debug"], True)
        self.assertEqual(data["profiles"]["main"]["session_id"], "main")
        self.assertEqual(data["profiles"]["main"]["run"]["ticks"], 10)

    def test_parse_simple_toml_supports_arrays(self) -> None:
        data = parse_simple_toml(
            """
            [init]
            character_ids = ["liu_bei", "cao_cao"]
            """
        )

        self.assertEqual(data["init"]["character_ids"], ["liu_bei", "cao_cao"])

    def test_resolve_cli_config_path_finds_repo_and_nested_locations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            nested = root / "src" / "dreamdive"
            nested.mkdir(parents=True)
            config_path = root / "dreamdive.toml"
            config_path.write_text("[defaults]\nworkspace='.dreamdive'\n", encoding="utf-8")

            resolved = resolve_cli_config_path(start_dir=nested)

            self.assertEqual(resolved, config_path.resolve())

    def test_apply_cli_config_merges_defaults_profile_and_cli_overrides(self) -> None:
        args = argparse.Namespace(command="run", profile="main", ticks=3)
        config = {
            "defaults": {"workspace": ".dreamdive", "debug": True},
            "run": {"ticks": 5},
            "profiles": {
                "main": {
                    "session_id": "main",
                    "run": {"ticks": 10},
                }
            },
        }

        merged = apply_cli_config(args, config)

        self.assertEqual(merged.workspace, ".dreamdive")
        self.assertEqual(merged.session_id, "main")
        self.assertEqual(merged.ticks, 3)
        self.assertEqual(merged.debug, True)

    def test_apply_cli_config_does_not_let_none_override_defaults(self) -> None:
        args = argparse.Namespace(
            command="init",
            profile="",
            source="resources/redcliff.txt",
            chapter_id="001",
            tick_label=None,
            timeline_index=None,
        )

        merged = apply_cli_config(args, {})

        self.assertEqual(merged.tick_label, "snapshot")
        self.assertEqual(merged.timeline_index, 0)

    def test_load_cli_config_reads_example_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "dreamdive.toml"
            path.write_text(
                "[defaults]\nworkspace='.dreamdive'\n[run]\nticks=10\n",
                encoding="utf-8",
            )

            loaded = load_cli_config(path)

            self.assertEqual(loaded["defaults"]["workspace"], ".dreamdive")
            self.assertEqual(loaded["run"]["ticks"], 10)

    def test_apply_cli_config_includes_new_rerun_and_overwrite_defaults(self) -> None:
        ingest_args = argparse.Namespace(command="ingest", profile="", source="resources/redcliff.txt")
        init_args = argparse.Namespace(
            command="init",
            profile="",
            source="resources/redcliff.txt",
            chapter_id="001",
        )

        merged_ingest = apply_cli_config(
            ingest_args,
            {"ingest": {"rerun_chapters": True, "rerun_entities": True}},
        )
        merged_init = apply_cli_config(
            init_args,
            {"init": {"overwrite": True}},
        )
        merged_run = apply_cli_config(
            argparse.Namespace(command="run", profile="", ticks=5),
            {},
        )

        self.assertEqual(merged_ingest.rerun_structural_scan, False)
        self.assertEqual(merged_ingest.rerun_chapters, True)
        self.assertEqual(merged_ingest.rerun_entities, True)
        self.assertEqual(merged_init.overwrite, True)
        self.assertEqual(merged_run.overwrite, True)


if __name__ == "__main__":
    unittest.main()
