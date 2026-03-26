import tempfile
import unittest
from pathlib import Path

from dreamdive.cli import (
    _format_exception_chain,
    _available_local_session_ids,
    _ensure_existing_session_can_be_modified,
    _ensure_target_not_exists,
    _format_background_summary,
    _format_duration_compact,
    _format_ingest_detail,
    _format_ingest_progress,
    _format_init_stage,
    _format_init_progress,
    _format_provider_usage,
    _format_session_not_found_message,
    _format_session_ready_detail,
    _format_status_line,
    _format_story_time,
    _format_tick_summary,
    _validate_command_args,
    build_parser,
)


class CliHelpersTests(unittest.TestCase):
    def test_available_local_session_ids_includes_default_and_named_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            (workspace / "simulation_session.json").write_text("{}", encoding="utf-8")
            (workspace / "simulation_session.main.json").write_text("{}", encoding="utf-8")
            (workspace / "simulation_session.branch_a.json").write_text("{}", encoding="utf-8")

            session_ids = _available_local_session_ids(workspace)

            self.assertEqual(session_ids, ["default", "branch_a", "main"])

    def test_format_session_not_found_message_suggests_default_when_present(self) -> None:
        workspace = Path(".dreamdive")
        expected_path = workspace / "simulation_session.main.json"

        message = _format_session_not_found_message(
            command="run",
            workspace_dir=workspace,
            session_id="main",
            expected_path=expected_path,
            available_session_ids=["default"],
        )

        self.assertIn("session_id 'main'", message)
        self.assertIn(str(expected_path), message)
        self.assertIn("Available session IDs: default", message)
        self.assertIn("without --session-id", message)

    def test_format_session_not_found_message_suggests_init_when_empty(self) -> None:
        workspace = Path(".dreamdive")
        expected_path = workspace / "simulation_session.alpha.json"

        message = _format_session_not_found_message(
            command="tick",
            workspace_dir=workspace,
            session_id="alpha",
            expected_path=expected_path,
            available_session_ids=[],
        )

        self.assertIn("Initialize one first with `init`", message)
        self.assertIn("workspace `.dreamdive`", message)

    def test_validate_command_args_allows_config_backed_init_values(self) -> None:
        class FakeParser:
            def error(self, message):
                raise AssertionError(message)

        args = type(
            "Args",
            (),
            {
                "command": "init",
                "source": "resources/redcliff.txt",
                "chapter_id": "001",
            },
        )()

        _validate_command_args(FakeParser(), args)

    def test_validate_command_args_rejects_missing_ingest_source(self) -> None:
        class FakeParser:
            def error(self, message):
                raise RuntimeError(message)

        args = type("Args", (), {"command": "ingest", "source": ""})()

        with self.assertRaises(RuntimeError):
            _validate_command_args(FakeParser(), args)

    def test_format_duration_compact_handles_minutes_and_hours(self) -> None:
        self.assertEqual(_format_duration_compact(1), "1 min")
        self.assertEqual(_format_duration_compact(60), "1 hr")
        self.assertEqual(_format_duration_compact(75), "1h 15m")
        self.assertEqual(_format_duration_compact(1440), "1 day")
        self.assertEqual(_format_duration_compact(2280), "1d 14h")

    def test_format_story_time_uses_story_language(self) -> None:
        self.assertEqual(_format_story_time(0), "story start")
        self.assertEqual(_format_story_time(2280), "story +1d 14h")

    def test_format_tick_summary_includes_step_story_and_last_span(self) -> None:
        self.assertEqual(
            _format_tick_summary(4560, 1110, tick_count=6),
            "step 6 · story +3d 4h · last +18h 30m",
        )

    def test_format_tick_summary_includes_new_and_total_warnings(self) -> None:
        self.assertEqual(
            _format_tick_summary(
                4560,
                1110,
                tick_count=6,
                llm_issue_count=1,
                total_llm_issue_count=4,
            ),
            "step 6 · story +3d 4h · last +18h 30m · 1 new LLM warning · 4 total warnings",
        )

    def test_format_init_progress_includes_starting_chapter_story_time_and_session(self) -> None:
        self.assertEqual(
            _format_init_progress(
                chapter_id="001",
                chapter_title="序幕 白帝城",
                chapter_index=1,
                chapter_count=12,
                timeline_index=0,
                session_id="main",
            ),
            "chapter 1/12 · 序幕 白帝城 · story start · session main",
        )

    def test_format_init_progress_includes_agent_and_stage_details(self) -> None:
        self.assertEqual(
            _format_init_progress(
                chapter_id="003",
                chapter_title="Chapter 2 · 黄金瞳",
                chapter_index=3,
                chapter_count=5,
                timeline_index=0,
                session_id="main",
                agent_index=4,
                agent_total=27,
                character_name="路明非",
                stage_label="inferring state",
            ),
            "chapter 3/5 · Chapter 2 · 黄金瞳 · story start · session main · agent 4/27 · 路明非 · inferring state",
        )

    def test_format_init_stage_maps_initializer_events(self) -> None:
        self.assertEqual(_format_init_stage({"stage": "prepare_agents", "agent_total": 27}), "preparing 27 agents")
        self.assertEqual(_format_init_stage({"stage": "snapshot_inference"}), "inferring state")
        self.assertEqual(_format_init_stage({"stage": "goal_seeding_fallback"}), "using heuristic goal fallback")

    def test_format_session_ready_detail_includes_starting_chapter_context(self) -> None:
        session = type(
            "Session",
            (),
            {
                "current_timeline_index": 0,
                "agents": {"char_001": object(), "char_002": object()},
                "metadata": {
                    "chapter_title": "序幕 白帝城",
                    "chapter_order_index": 1,
                    "chapter_count": 12,
                    "llm_issue_count": 0,
                },
            },
        )()

        self.assertEqual(
            _format_session_ready_detail(session),
            "chapter 1/12 · 序幕 白帝城 · story start · 2 agents",
        )

    def test_format_background_summary_includes_warning_history(self) -> None:
        session = type(
            "Session",
            (),
            {
                "current_timeline_index": 1440,
                "pending_background_jobs": [{"job_id": "job_1"}],
                "metadata": {
                    "last_background_llm_issue_count": 2,
                    "llm_issue_count": 5,
                },
            },
        )()

        self.assertEqual(
            _format_background_summary(session),
            "story +1 day · 1 job queued · 2 new LLM warnings · 5 total warnings",
        )

    def test_format_ingest_detail_handles_pluralization(self) -> None:
        self.assertEqual(_format_ingest_detail(chapter_count=1, character_count=1), "1 chapter · 1 character")
        self.assertEqual(_format_ingest_detail(chapter_count=3, character_count=12), "3 chapters · 12 characters")

    def test_format_ingest_progress_reports_current_chapter_section(self) -> None:
        self.assertEqual(
            _format_ingest_progress(
                "chapter_section",
                {
                    "chapter_id": "002",
                    "chapter_title": "Chapter 1 · 卡塞尔之门",
                    "chapter_index": 2,
                    "chapter_count": 12,
                    "section_title": "Chapter 1 · 卡塞尔之门 [section 3/6]",
                },
            ),
            "chapter 2/12 · Chapter 1 · 卡塞尔之门 [section 3/6]",
        )

    def test_format_ingest_progress_reports_structural_scan_and_cached_meta(self) -> None:
        self.assertEqual(
            _format_ingest_progress("structural_scan", {"chunk_count": 15}),
            "structural scan · 15 chunks",
        )
        self.assertEqual(
            _format_ingest_progress("meta_layer", {"cached": True}),
            "meta-layer analysis · cached",
        )

    def test_format_status_line_uses_minimal_plain_output(self) -> None:
        line = _format_status_line(
            "Simulation running",
            "3 ticks",
            phase="running",
            pretty=False,
            unicode_ok=False,
        )

        self.assertEqual(line, "o Simulation running · 3 ticks")

    def test_format_status_line_uses_braille_dot_when_unicode_is_available(self) -> None:
        line = _format_status_line(
            "Running simulation...",
            phase="running",
            pretty=False,
            unicode_ok=True,
        )

        self.assertEqual(line, "⠋ Running simulation...")

    def test_format_exception_chain_includes_nested_causes(self) -> None:
        inner = RuntimeError("Inner cause")
        outer = RuntimeError("Outer message")
        outer.__cause__ = inner

        self.assertEqual(
            _format_exception_chain(outer),
            "Outer message · Inner cause",
        )

    def test_format_provider_usage_supports_single_and_fallback_chain(self) -> None:
        single_client = type(
            "Client",
            (),
            {
                "provider_usage_summary": lambda self: {
                    "ordered_profiles": ["qwen"],
                    "counts": {"qwen": 2},
                    "total_calls": 2,
                }
            },
        )()
        fallback_client = type(
            "Client",
            (),
            {
                "provider_usage_summary": lambda self: {
                    "ordered_profiles": ["qwen", "moonshot"],
                    "counts": {"qwen": 3, "moonshot": 1},
                    "total_calls": 4,
                }
            },
        )()

        self.assertEqual(_format_provider_usage(single_client), "LLM qwen")
        self.assertEqual(_format_provider_usage(fallback_client), "LLM qwen->moonshot")

    def test_parser_accepts_json_flag_for_run(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["run", "--workspace", ".dreamdive", "--ticks", "2", "--json"])

        self.assertTrue(args.json)
        self.assertEqual(args.command, "run")

    def test_parser_accepts_json_flag_for_ingest(self) -> None:
        parser = build_parser()

        args = parser.parse_args(["ingest", "resources/redcliff.txt", "--workspace", ".dreamdive", "--json"])

        self.assertTrue(args.json)
        self.assertEqual(args.command, "ingest")

    def test_parser_accepts_rerun_flags_for_ingest(self) -> None:
        parser = build_parser()

        args = parser.parse_args(
            [
                "ingest",
                "resources/redcliff.txt",
                "--rerun-structural-scan",
                "--rerun-chapters",
                "--rerun-meta-layer",
            ]
        )

        self.assertTrue(args.rerun_structural_scan)
        self.assertTrue(args.rerun_chapters)
        self.assertTrue(args.rerun_meta_layer)

    def test_parser_accepts_overwrite_for_init_and_branch(self) -> None:
        parser = build_parser()

        init_args = parser.parse_args(["init", "resources/redcliff.txt", "--chapter-id", "001", "--overwrite"])
        branch_args = parser.parse_args(["branch", "--timeline-index", "10", "--overwrite"])
        run_args = parser.parse_args(["run", "--ticks", "5", "--overwrite"])

        self.assertTrue(init_args.overwrite)
        self.assertTrue(branch_args.overwrite)
        self.assertTrue(run_args.overwrite)

    def test_ensure_target_not_exists_raises_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = type(
                "Store",
                (),
                {
                    "path": Path(tmpdir) / "simulation_session.main.json",
                    "exists": lambda self: True,
                },
            )()

            with self.assertRaises(FileExistsError):
                _ensure_target_not_exists(
                    store,
                    command="init",
                    session_id="main",
                    overwrite=False,
                )

    def test_ensure_target_not_exists_allows_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = type(
                "Store",
                (),
                {
                    "path": Path(tmpdir) / "simulation_session.main.json",
                    "exists": lambda self: True,
                },
            )()

            _ensure_target_not_exists(
                store,
                command="init",
                session_id="main",
                overwrite=True,
            )

    def test_ensure_existing_session_can_be_modified_raises_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = type(
                "Store",
                (),
                {
                    "path": Path(tmpdir) / "simulation_session.main.json",
                    "exists": lambda self: True,
                },
            )()

            with self.assertRaises(FileExistsError):
                _ensure_existing_session_can_be_modified(
                    store,
                    command="run",
                    session_id="main",
                    overwrite=False,
                )

    def test_ensure_existing_session_can_be_modified_allows_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            store = type(
                "Store",
                (),
                {
                    "path": Path(tmpdir) / "simulation_session.main.json",
                    "exists": lambda self: True,
                },
            )()

            _ensure_existing_session_can_be_modified(
                store,
                command="run",
                session_id="main",
                overwrite=True,
            )


if __name__ == "__main__":
    unittest.main()
