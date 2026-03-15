from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import unicodedata
from pathlib import Path
from typing import Iterable

from dreamdive.cli_config import apply_cli_config, load_cli_config, resolve_cli_config_path
from dreamdive.config import get_settings
from dreamdive.debug import DebugSession
from dreamdive.ingestion.backend import LLMExtractionBackend
from dreamdive.db.migrate import build_migration_runner
from dreamdive.ingestion.extractor import ArtifactStore, IngestionPipeline, ManifestStore
from dreamdive.ingestion.source_loader import load_chapters, load_text, sample_representative_excerpts
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.llm.openai_transport import build_transport
from dreamdive.simulation.background_runner import BackgroundMaintenanceRunner
from dreamdive.simulation.runtime_store import SimulationRuntimeStore, build_runtime_store
from dreamdive.simulation.workflow import (
    advance_session,
    branch_session,
    initialize_session,
    run_session_tick,
    session_report,
)
from dreamdive.visualization_server import (
    build_visualization_url,
    start_visualization_server,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dreamdive workflow CLI.",
        argument_default=argparse.SUPPRESS,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Run manuscript ingestion.")
    ingest.add_argument("source", nargs="?", help="Path to the novel text or markdown file.")
    ingest.add_argument(
        "--workspace",
        help="Directory for ingestion manifests and artifacts.",
    )
    ingest.add_argument(
        "--skip-structural-scan",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Skip the structural scan and process chapters only.",
    )
    ingest.add_argument(
        "--rerun-structural-scan",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force rerunning structural scan even if cached artifacts exist.",
    )
    ingest.add_argument(
        "--rerun-chapters",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force rerunning chapter extraction and overwrite chapter snapshots.",
    )
    ingest.add_argument(
        "--skip-meta-layer",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Skip the meta-layer extraction pass.",
    )
    ingest.add_argument(
        "--rerun-meta-layer",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force rerunning the meta-layer extraction pass even if cached.",
    )
    ingest.add_argument(
        "--skip-entities",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Skip the entity extraction pass.",
    )
    ingest.add_argument(
        "--rerun-entities",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force rerunning entity extraction even if cached.",
    )
    ingest.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Max parallel LLM workers for chapter extraction (default: 4).",
    )

    init_snapshot = subparsers.add_parser("init-snapshot", help="Initialize a simulation session.")
    init_snapshot.add_argument("source", nargs="?", help="Path to the novel text or markdown file.")
    init_snapshot.add_argument("--workspace")
    init_snapshot.add_argument("--chapter-id")
    init_snapshot.add_argument("--tick-label")
    init_snapshot.add_argument("--timeline-index", type=int)
    init_snapshot.add_argument("--character-id", action="append", dest="character_ids")
    init_snapshot.add_argument("--session-id")
    init_snapshot.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)
    init_snapshot.add_argument("--max-workers", type=int, default=None, help="Max parallel LLM workers for agent initialization (default: 4).")

    tick = subparsers.add_parser("tick", help="Advance an existing simulation session by one tick.")
    tick.add_argument("--workspace")
    tick.add_argument("--session-id")
    tick.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)
    tick.add_argument("--tick-max-events", type=int, help="Maximum background/foreground events to process per tick.")

    run = subparsers.add_parser("run", help="Advance an existing simulation session by multiple ticks.")
    run.add_argument("--workspace")
    run.add_argument("--ticks", type=int)
    run.add_argument("--session-id")
    run.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)
    run.add_argument("--tick-max-events", type=int, help="Maximum background/foreground events to process per tick.")

    background = subparsers.add_parser("background", help="Run due background maintenance jobs.")
    background.add_argument("--workspace")
    background.add_argument("--max-jobs", type=int)
    background.add_argument("--session-id")
    background.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)

    branch = subparsers.add_parser("branch", help="Create a counterfactual branch from an earlier point.")
    branch.add_argument("--workspace")
    branch.add_argument("--output-workspace")
    branch.add_argument("--session-id")
    branch.add_argument("--output-session-id")
    branch.add_argument("--overwrite", action="store_true", default=argparse.SUPPRESS)
    branch_group = branch.add_mutually_exclusive_group(required=False)
    branch_group.add_argument("--timeline-index", type=int)
    branch_group.add_argument("--before-event-id")

    migrate = subparsers.add_parser("migrate", help="Apply the PostgreSQL schema migration.")
    migrate.add_argument("--database-url")

    visualize = subparsers.add_parser("visualize", help="Serve the visualization web app.")
    visualize.add_argument("--workspace")
    visualize.add_argument("--session-id")
    visualize.add_argument("--host")
    visualize.add_argument("--port", type=int)
    for subparser in [ingest, init_snapshot, tick, run, background, branch, migrate, visualize]:
        subparser.add_argument("--debug", action="store_true", default=argparse.SUPPRESS)
        subparser.add_argument("--debug-dir")
        subparser.add_argument("--config")
        subparser.add_argument("--profile")
    for subparser in [ingest, init_snapshot, tick, run, background, branch, migrate, visualize]:
        subparser.add_argument(
            "--json",
            action="store_true",
            default=argparse.SUPPRESS,
            help="Print machine-readable JSON instead of the minimal status line.",
        )
    return parser


def maybe_build_debug_session(args, settings) -> DebugSession | None:
    enabled = bool(getattr(args, "debug", False) or settings.debug_mode)
    if not enabled:
        return None
    debug_dir_value = getattr(args, "debug_dir", "") or settings.debug_dir
    debug_dir = Path(debug_dir_value) if debug_dir_value else None
    debug_session = DebugSession.create(
        debug_dir=debug_dir,
        record_llm=settings.debug_record_llm,
    )
    debug_session.event(
        "cli.debug_enabled",
        command=args.command,
        debug_dir=str(debug_session.root_dir),
        record_llm=settings.debug_record_llm,
    )
    return debug_session


def build_llm_client(settings, debug_session: DebugSession | None):
    transport = build_transport(settings)
    client = StructuredLLMClient.from_settings(transport, settings)
    client.debug_session = debug_session
    return client


def _supports_unicode(stream) -> bool:
    encoding = (getattr(stream, "encoding", "") or "").lower()
    return "utf" in encoding or "unicode" in encoding


def _supports_pretty_status(stream) -> bool:
    if os.getenv("NO_COLOR"):
        return False
    if not getattr(stream, "isatty", lambda: False)():
        return False
    return (os.getenv("TERM", "") or "").lower() not in {"", "dumb"}


_BRAILLE_SPINNER_FRAMES = (
    "⠋",
    "⠙",
    "⠹",
    "⠸",
    "⠼",
    "⠴",
    "⠦",
    "⠧",
    "⠇",
    "⠏",
)


def _status_icon(phase: str, *, unicode_ok: bool) -> str:
    icons = {
        "running": _BRAILLE_SPINNER_FRAMES[0] if unicode_ok else "o",
        "done": "●" if unicode_ok else "*",
        "error": "◍" if unicode_ok else "!",
    }
    return icons.get(phase, icons["done"])


def _format_duration_compact(minutes: int) -> str:
    total = max(0, int(minutes))
    if total < 60:
        return f"{total} min"
    if total >= 1440:
        days, remainder = divmod(total, 1440)
        if remainder == 0:
            return f"{days} day{'s' if days != 1 else ''}"
        hours = remainder // 60
        return f"{days}d {hours}h"
    hours, remainder = divmod(total, 60)
    if remainder == 0:
        return f"{hours} hr"
    return f"{hours}h {remainder}m"


def _format_status_line(
    label: str,
    detail: str = "",
    *,
    phase: str = "running",
    pretty: bool = False,
    unicode_ok: bool = True,
    icon: str | None = None,
) -> str:
    marker = icon or _status_icon(phase, unicode_ok=unicode_ok)
    text = f"{marker} {label}"
    if detail:
        text = f"{text} · {detail}"
    if not pretty:
        return text

    accent = {
        "running": "\033[38;5;110m",
        "done": "\033[38;5;72m",
        "error": "\033[38;5;167m",
    }.get(phase, "\033[38;5;72m")
    reset = "\033[0m"
    bold = "\033[1m"
    dim = "\033[2m"
    rendered = f"{accent}{marker}{reset} {bold}{label}{reset}"
    if detail:
        rendered = f"{rendered} {dim}· {detail}{reset}"
    return rendered


def _char_display_width(char: str) -> int:
    """Return the number of terminal columns a character occupies."""
    eaw = unicodedata.east_asian_width(char)
    return 2 if eaw in ("F", "W") else 1


def _truncate_to_display_width(text: str, max_width: int) -> str:
    """Truncate *text* so its display width fits within *max_width* columns.

    ANSI escape sequences are skipped during width counting but preserved in
    the output.  If truncation is required, the string is cut and an ellipsis
    (``…``) is appended.
    """
    if max_width <= 0:
        return text
    width = 0
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        # Skip ANSI escape sequences (they occupy zero display columns).
        if ch == "\033" and i + 1 < n and text[i + 1] == "[":
            j = i + 2
            while j < n and text[j] not in "ABCDEFGHJKSTfmnsulh":
                j += 1
            i = j + 1  # skip past the terminator
            continue
        cw = _char_display_width(ch)
        if width + cw > max_width - 1:  # reserve 1 column for '…'
            return text[:i] + "…\033[0m"
        width += cw
        i += 1
    return text


class _CliStatusLine:
    def __init__(
        self,
        label: str,
        detail: str = "",
        *,
        enabled: bool = True,
        stream=None,
    ) -> None:
        self.label = label
        self.detail = detail
        self.enabled = enabled
        self.stream = stream or sys.stdout
        self.pretty = enabled and _supports_pretty_status(self.stream)
        self.unicode_ok = _supports_unicode(self.stream)
        self.finished = False
        self._lock = threading.Lock()
        self._spinner_stop = threading.Event()
        self._spinner_thread: threading.Thread | None = None

    def _write_pretty(self, line: str, *, newline: bool = False) -> None:
        suffix = "\n" if newline else ""
        try:
            cols = os.get_terminal_size(self.stream.fileno()).columns
        except (AttributeError, ValueError, OSError):
            cols = 0
        if cols > 0:
            line = _truncate_to_display_width(line, cols)
        self.stream.write(f"\r\033[2K{line}{suffix}")
        self.stream.flush()

    def _render_running_frame(self, icon: str) -> None:
        line = _format_status_line(
            self.label,
            self.detail,
            phase="running",
            pretty=self.pretty,
            unicode_ok=self.unicode_ok,
            icon=icon,
        )
        if self.pretty:
            self._write_pretty(line)
        else:
            print(line, file=self.stream, flush=True)

    def _start_spinner(self) -> None:
        if not (self.pretty and self.unicode_ok):
            return

        def spin() -> None:
            index = 0
            while not self._spinner_stop.wait(0.08):
                frame = _BRAILLE_SPINNER_FRAMES[index % len(_BRAILLE_SPINNER_FRAMES)]
                with self._lock:
                    if self.finished:
                        return
                    self._render_running_frame(frame)
                index += 1

        self._spinner_thread = threading.Thread(target=spin, daemon=True)
        self._spinner_thread.start()

    def __enter__(self) -> "_CliStatusLine":
        if not self.enabled:
            return self
        self._render_running_frame(_status_icon("running", unicode_ok=self.unicode_ok))
        self._start_spinner()
        return self

    def update(self, *, label: str | None = None, detail: str | None = None) -> None:
        if not self.enabled:
            return
        if label is not None:
            self.label = label
        if detail is not None:
            self.detail = detail
        line = _format_status_line(
            self.label,
            self.detail,
            phase="running",
            pretty=self.pretty,
            unicode_ok=self.unicode_ok,
        )
        with self._lock:
            if self.finished:
                return
            if self.pretty:
                self._write_pretty(line)
            else:
                print(line, file=self.stream, flush=True)

    def finish(self, label: str, detail: str = "", *, phase: str = "done") -> None:
        if not self.enabled:
            return
        self._spinner_stop.set()
        if self._spinner_thread is not None:
            self._spinner_thread.join(timeout=0.2)
        line = _format_status_line(
            label,
            detail,
            phase=phase,
            pretty=self.pretty,
            unicode_ok=self.unicode_ok,
        )
        with self._lock:
            if self.pretty:
                self._write_pretty(line, newline=True)
            else:
                print(line, file=self.stream, flush=True)
        self.finished = True

    def __exit__(self, exc_type, exc, _tb) -> bool:
        if exc_type is not None and not self.finished:
            detail = _format_exception_chain(exc) if exc is not None else exc_type.__name__
            self.finish("Command failed", detail, phase="error")
        return False


def _format_exception_chain(exc: BaseException) -> str:
    parts: list[str] = []
    current: BaseException | None = exc
    while current is not None:
        text = str(current).strip() or current.__class__.__name__
        if text not in parts:
            parts.append(text)
        current = current.__cause__
    return " · ".join(parts)


def _format_story_time(minutes: int) -> str:
    total = max(0, int(minutes))
    if total == 0:
        return "story start"
    return f"story +{_format_duration_compact(total)}"


def _format_tick_summary(
    current_timeline_index: int,
    last_tick_minutes: int = 0,
    *,
    tick_count: int | None = None,
    llm_issue_count: int = 0,
    total_llm_issue_count: int | None = None,
) -> str:
    parts = []
    if tick_count is not None:
        parts.append(f"step {tick_count}")
    parts.append(_format_story_time(current_timeline_index))
    if last_tick_minutes > 0:
        parts.append(f"last +{_format_duration_compact(last_tick_minutes)}")
    if llm_issue_count > 0:
        parts.append(f"{llm_issue_count} new LLM warning{'s' if llm_issue_count != 1 else ''}")
    total = int(total_llm_issue_count or 0)
    if total > 0 and total != llm_issue_count:
        parts.append(f"{total} total warnings")
    return " · ".join(parts)


def _format_provider_usage(client) -> str:
    summary_fn = getattr(client, "provider_usage_summary", None)
    if not callable(summary_fn):
        return ""
    summary = summary_fn()
    ordered = [str(item) for item in summary.get("ordered_profiles", []) if str(item).strip()]
    if not ordered:
        return ""
    if len(ordered) == 1:
        return f"LLM {ordered[0]}"
    return f"LLM {'->'.join(ordered)}"


def _format_tick_stage(event: dict[str, object]) -> str:
    message = str(event.get("message", "") or "").strip()
    if message:
        return message
    stage = str(event.get("stage", "") or "").strip()
    if stage:
        return stage.replace("_", " ")
    return "working"


def _format_session_ready_detail(session) -> str:
    parts = []
    chapter_title = str(session.metadata.get("chapter_title", "") or "")
    chapter_index = int(session.metadata.get("chapter_order_index", 0) or 0)
    chapter_count = int(session.metadata.get("chapter_count", 0) or 0)
    if chapter_title:
        if chapter_index > 0 and chapter_count > 0:
            parts.append(f"chapter {chapter_index}/{chapter_count}")
        parts.append(chapter_title)
    parts.extend(
        [
            _format_story_time(session.current_timeline_index),
            f"{len(session.agents)} agents",
        ]
    )
    init_issues = int(session.metadata.get("llm_issue_count", 0) or 0)
    if init_issues > 0:
        parts.append(f"{init_issues} LLM warning{'s' if init_issues != 1 else ''}")
    return " · ".join(parts)


def _format_background_summary(session) -> str:
    last_background_issues = int(session.metadata.get("last_background_llm_issue_count", 0) or 0)
    total_issues = int(session.metadata.get("llm_issue_count", 0) or 0)
    job_count = len(session.pending_background_jobs)
    parts = [
        _format_story_time(session.current_timeline_index),
        f"{job_count} job{'s' if job_count != 1 else ''} queued",
    ]
    if last_background_issues > 0:
        parts.append(
            f"{last_background_issues} new LLM warning{'s' if last_background_issues != 1 else ''}"
        )
    if total_issues > 0 and total_issues != last_background_issues:
        parts.append(f"{total_issues} total warnings")
    return " · ".join(parts)


def _format_ingest_detail(*, chapter_count: int, character_count: int) -> str:
    return " · ".join(
        [
            f"{chapter_count} chapter{'s' if chapter_count != 1 else ''}",
            f"{character_count} character{'s' if character_count != 1 else ''}",
        ]
    )


def _format_ingest_progress(stage: str, payload: dict[str, object]) -> str:
    if stage == "structural_scan":
        detail = "structural scan"
        chunk_count = int(payload.get("chunk_count", 0) or 0)
        if chunk_count > 0:
            detail = f"{detail} · {chunk_count} chunk{'s' if chunk_count != 1 else ''}"
        if bool(payload.get("cached", False)):
            detail = f"{detail} · cached"
        return detail
    if stage in {"chapter", "chapter_section", "chapter_retry_split"}:
        chapter_index = int(payload.get("chapter_index", 0) or 0)
        chapter_count = int(payload.get("chapter_count", 0) or 0)
        chapter_id = str(payload.get("chapter_id", "") or "")
        chapter_title = str(payload.get("chapter_title", "") or chapter_id)
        position = (
            f"chapter {chapter_index}/{chapter_count}"
            if chapter_index > 0 and chapter_count > 0
            else f"chapter {chapter_id}"
        )
        title = str(payload.get("section_title", "") or chapter_title)
        parts = [part for part in [position, title] if part]
        if stage == "chapter_retry_split":
            retry_count = int(payload.get("retry_count", 0) or 0)
            if retry_count > 0:
                parts.append(f"retry split {retry_count}")
        elif bool(payload.get("cached", False)):
            parts.append("cached")
        return " · ".join(parts)
    if stage == "meta_layer":
        detail = "meta-layer analysis"
        if bool(payload.get("cached", False)):
            detail = f"{detail} · cached"
        return detail
    if stage == "entity_extraction":
        detail = "entity extraction"
        if bool(payload.get("cached", False)):
            detail = f"{detail} · cached"
        return detail
    return ""


def _format_init_progress(
    *,
    chapter_id: str,
    chapter_title: str,
    chapter_index: int,
    chapter_count: int,
    timeline_index: int,
    session_id: str,
    agent_index: int | None = None,
    agent_total: int | None = None,
    character_name: str = "",
    stage_label: str = "",
) -> str:
    parts: list[str] = []
    if chapter_index > 0 and chapter_count > 0:
        parts.append(f"chapter {chapter_index}/{chapter_count}")
    elif chapter_id:
        parts.append(f"chapter {chapter_id}")
    if chapter_title:
        parts.append(chapter_title)
    parts.append(_format_story_time(timeline_index))
    if session_id:
        parts.append(f"session {session_id}")
    if agent_index is not None and agent_total:
        parts.append(f"agent {agent_index}/{agent_total}")
    if character_name:
        parts.append(character_name)
    if stage_label:
        parts.append(stage_label)
    return " · ".join(parts)


def _format_init_stage(event: dict[str, object]) -> str:
    stage = str(event.get("stage", "") or "")
    if stage == "prepare_agents":
        total = int(event.get("agent_total", 0) or 0)
        return f"preparing {total} agent{'s' if total != 1 else ''}"
    if stage == "agent_start":
        return "assembling snapshot"
    if stage == "snapshot_inference":
        return "inferring state"
    if stage == "snapshot_inference_fallback":
        return "using heuristic state fallback"
    if stage == "goal_seeding":
        return "seeding goals"
    if stage == "goal_seeding_fallback":
        return "using heuristic goal fallback"
    if stage == "agent_ready":
        return "ready"
    return ""


def _available_local_session_ids(workspace_dir: Path) -> list[str]:
    if not workspace_dir.exists():
        return []
    named_session_ids: list[str] = []
    has_default = False
    for path in sorted(workspace_dir.glob("simulation_session*.json")):
        name = path.name
        if name == "simulation_session.json":
            has_default = True
            continue
        if name.startswith("simulation_session.") and name.endswith(".json"):
            named_session_ids.append(name[len("simulation_session.") : -len(".json")])
    session_ids: list[str] = ["default"] if has_default else []
    session_ids.extend(named_session_ids)
    return session_ids


def _format_session_not_found_message(
    *,
    command: str,
    workspace_dir: Path,
    session_id: str,
    expected_path: Path,
    available_session_ids: Iterable[str],
) -> str:
    available = list(available_session_ids)
    message = (
        f"No saved simulation session was found for command '{command}' and "
        f"session_id '{session_id}'. Expected: {expected_path}"
    )
    if available:
        message += f". Available session IDs: {', '.join(available)}"
        if session_id != "default" and "default" in available:
            message += ". Try rerunning without --session-id, or use --session-id default"
    else:
        message += (
            f". Initialize one first with `init-snapshot` in workspace "
            f"`{workspace_dir}`"
        )
    return message


def load_required_session(store, *, command: str, workspace_dir: Path, session_id: str):
    if getattr(store, "exists", None) and not store.exists():
        expected_path = getattr(store, "path", workspace_dir / "simulation_session.json")
        available_session_ids = (
            _available_local_session_ids(workspace_dir)
            if isinstance(store, SimulationRuntimeStore)
            else []
        )
        raise FileNotFoundError(
            _format_session_not_found_message(
                command=command,
                workspace_dir=workspace_dir,
                session_id=session_id,
                expected_path=Path(expected_path),
                available_session_ids=available_session_ids,
            )
        )
    return store.load()


def _ensure_target_not_exists(
    store,
    *,
    command: str,
    session_id: str,
    overwrite: bool,
) -> None:
    if overwrite or not getattr(store, "exists", None):
        return
    if not store.exists():
        return
    target = getattr(store, "path", None)
    target_label = str(target) if target is not None else f"session_id '{session_id}'"
    raise FileExistsError(
        f"Command '{command}' would overwrite existing output at {target_label}. "
        "Use --overwrite or set overwrite = true in dreamdive.toml"
    )


def _ensure_existing_session_can_be_modified(
    store,
    *,
    command: str,
    session_id: str,
    overwrite: bool,
) -> None:
    if overwrite or not getattr(store, "exists", None):
        return
    if not store.exists():
        return
    target = getattr(store, "path", None)
    target_label = str(target) if target is not None else f"session_id '{session_id}'"
    raise FileExistsError(
        f"Command '{command}' would modify existing session data at {target_label}. "
        "Set overwrite = true or pass --overwrite to allow in-place updates"
    )


def _validate_command_args(parser: argparse.ArgumentParser, args) -> None:
    if args.command == "ingest" and not getattr(args, "source", ""):
        parser.error("`ingest` requires `source`, either on the command line or in dreamdive.toml")
    if args.command == "init-snapshot":
        if not getattr(args, "source", ""):
            parser.error(
                "`init-snapshot` requires `source`, either on the command line or in dreamdive.toml"
            )
        if not getattr(args, "chapter_id", ""):
            parser.error(
                "`init-snapshot` requires `chapter_id`, either on the command line or in dreamdive.toml"
            )
    if args.command == "branch":
        if getattr(args, "timeline_index", None) is None and not getattr(args, "before_event_id", ""):
            parser.error(
                "`branch` requires either `timeline_index` or `before_event_id`, "
                "either on the command line or in dreamdive.toml"
            )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config_path = resolve_cli_config_path(getattr(args, "config", ""))
    config_data = load_cli_config(config_path)
    args = apply_cli_config(args, config_data)
    _validate_command_args(parser, args)

    settings = get_settings()
    if hasattr(args, "tick_max_events") and getattr(args, "tick_max_events", None) is not None:
        settings.tick_max_events = args.tick_max_events
    debug_session = maybe_build_debug_session(args, settings)
    if args.command == "ingest":
        client = build_llm_client(settings, debug_session)
        source_path = Path(args.source)
        workspace_dir = Path(args.workspace)
        manifest_store = ManifestStore(workspace_dir / "ingestion_manifest.json")
        artifact_store = ArtifactStore(workspace_dir / "artifacts")
        pipeline = IngestionPipeline(manifest_store, artifact_store=artifact_store)
        backend = LLMExtractionBackend(client, debug_session=debug_session)
        emit_json = bool(getattr(args, "json", False))
        with _CliStatusLine(
            "Loading world...",
            enabled=not emit_json,
        ) as status:
            def ingest_progress(stage: str, payload: dict[str, object]) -> None:
                detail = _format_ingest_progress(stage, payload)
                if detail:
                    status.update(detail=detail)

            if not args.skip_structural_scan:
                structural_text = load_text(source_path)
                if debug_session is not None:
                    debug_session.event(
                        "cli.ingest.loaded_source",
                        source=str(source_path),
                        character_count=len(structural_text),
                    )
                structural = pipeline.run_structural_scan(
                    structural_text,
                    backend,
                    force_rerun=bool(getattr(args, "rerun_structural_scan", False)),
                    progress_callback=ingest_progress,
                )
                if emit_json:
                    print(json.dumps(structural.model_dump(mode="json"), indent=2, ensure_ascii=False))

            chapters = load_chapters(source_path)
            if debug_session is not None:
                debug_session.event(
                    "cli.ingest.chapters_loaded",
                    chapter_count=len(chapters),
                )
            accumulated = pipeline.run_chapter_passes(
                chapters,
                backend,
                force_rerun=bool(getattr(args, "rerun_chapters", False)),
                progress_callback=ingest_progress,
                max_workers=int(getattr(args, "max_workers", 0) or 4),
            )
            if not args.skip_meta_layer:
                meta = pipeline.run_meta_layer(
                    sample_representative_excerpts(chapters),
                    backend,
                    major_character_ids=[record.id for record in accumulated.characters],
                    force_rerun=bool(getattr(args, "rerun_meta_layer", False)),
                    progress_callback=ingest_progress,
                )
                accumulated = accumulated.model_copy(update={"meta": meta})
            if not args.skip_entities:
                entities = pipeline.run_entity_extraction(
                    accumulated,
                    backend,
                    force_rerun=bool(getattr(args, "rerun_entities", False)),
                    progress_callback=ingest_progress,
                )
                accumulated = accumulated.model_copy(update={"entities": entities.entities})
            if emit_json:
                print(json.dumps(accumulated.model_dump(mode="json"), indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "World loaded",
                    " · ".join(
                        part
                        for part in [
                            _format_ingest_detail(
                                chapter_count=len(chapters),
                                character_count=len(accumulated.characters),
                            ),
                            _format_provider_usage(client),
                        ]
                        if part
                    ),
                )
        return 0

    if args.command == "init-snapshot":
        client = build_llm_client(settings, debug_session)
        emit_json = bool(getattr(args, "json", False))
        source_path = Path(args.source)
        chapters = load_chapters(source_path)
        chapter_map = {chapter.chapter_id: chapter for chapter in chapters}
        chapter = chapter_map.get(args.chapter_id)
        init_detail = _format_init_progress(
            chapter_id=args.chapter_id,
            chapter_title=(chapter.title if chapter is not None else args.chapter_id),
            chapter_index=(chapter.order_index if chapter is not None else 0),
            chapter_count=len(chapters),
            timeline_index=int(args.timeline_index or 0),
            session_id=args.session_id,
        )
        with _CliStatusLine(
            "Initializing...",
            init_detail,
            enabled=not emit_json,
        ) as status:
            def _update_init_progress(event: dict[str, object]) -> None:
                status.update(
                    detail=_format_init_progress(
                        chapter_id=str(event.get("chapter_id", args.chapter_id) or args.chapter_id),
                        chapter_title=str(
                            event.get("chapter_title", chapter.title if chapter is not None else args.chapter_id)
                            or ""
                        ),
                        chapter_index=int(
                            event.get("chapter_index", chapter.order_index if chapter is not None else 0) or 0
                        ),
                        chapter_count=int(event.get("chapter_count", len(chapters)) or 0),
                        timeline_index=int(args.timeline_index or 0),
                        session_id=args.session_id,
                        agent_index=(
                            int(event["agent_index"])
                            if event.get("agent_index") is not None
                            else None
                        ),
                        agent_total=(
                            int(event["agent_total"])
                            if event.get("agent_total") is not None
                            else None
                        ),
                        character_name=str(event.get("character_name", "") or ""),
                        stage_label=_format_init_stage(event),
                    )
                )

            store = build_runtime_store(
                Path(args.workspace),
                settings=settings,
                session_id=args.session_id,
            )
            _ensure_target_not_exists(
                store,
                command="init-snapshot",
                session_id=args.session_id,
                overwrite=bool(getattr(args, "overwrite", False)),
            )
            session = initialize_session(
                source_path=source_path,
                workspace_dir=Path(args.workspace),
                chapter_id=args.chapter_id,
                tick_label=args.tick_label,
                timeline_index=args.timeline_index,
                llm_client=client,
                character_ids=args.character_ids,
                debug_session=debug_session,
                on_progress=_update_init_progress,
                max_workers=int(getattr(args, "max_workers", 4) or 4),
            )
            store.save(session)
            if emit_json:
                print(json.dumps(session.model_dump(mode="json"), indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "Initialized",
                    " · ".join(
                        part
                        for part in [
                            _format_session_ready_detail(session),
                            _format_provider_usage(client),
                        ]
                        if part
                    ),
                )
        return 0

    if args.command == "tick":
        client = build_llm_client(settings, debug_session)
        workspace_dir = Path(args.workspace)
        store = build_runtime_store(
            workspace_dir,
            settings=settings,
            session_id=args.session_id,
        )
        _ensure_existing_session_can_be_modified(
            store,
            command="tick",
            session_id=args.session_id,
            overwrite=bool(getattr(args, "overwrite", True)),
        )
        session = load_required_session(
            store,
            command="tick",
            workspace_dir=workspace_dir,
            session_id=args.session_id,
        )
        emit_json = bool(getattr(args, "json", False))
        with _CliStatusLine(
            "Advancing simulation...",
            enabled=not emit_json,
        ) as status:
            def _update_tick_progress(event: dict[str, object]) -> None:
                status.update(detail=_format_tick_stage(event))

            updated = run_session_tick(
                session,
                client,
                debug_session=debug_session,
                settings=settings,
                on_progress=_update_tick_progress,
            )
            store.save(updated)
            if emit_json:
                print(json.dumps(updated.model_dump(mode="json"), indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "Simulation advanced",
                    " · ".join(
                        part
                        for part in [
                            _format_tick_summary(
                                updated.current_timeline_index,
                                int(updated.metadata.get("last_tick_minutes", 0) or 0),
                                tick_count=int(updated.metadata.get("tick_count", 0) or 0),
                                llm_issue_count=int(updated.metadata.get("last_tick_llm_issue_count", 0) or 0),
                                total_llm_issue_count=int(updated.metadata.get("llm_issue_count", 0) or 0),
                            ),
                            _format_provider_usage(client),
                        ]
                        if part
                    ),
                )
        return 0

    if args.command == "run":
        client = build_llm_client(settings, debug_session)
        workspace_dir = Path(args.workspace)
        store = build_runtime_store(
            workspace_dir,
            settings=settings,
            session_id=args.session_id,
        )
        _ensure_existing_session_can_be_modified(
            store,
            command="run",
            session_id=args.session_id,
            overwrite=bool(getattr(args, "overwrite", True)),
        )
        session = load_required_session(
            store,
            command="run",
            workspace_dir=workspace_dir,
            session_id=args.session_id,
        )
        emit_json = bool(getattr(args, "json", False))
        tick_count = int(args.ticks or 0)
        with _CliStatusLine(
            "Running simulation...",
            f"{tick_count} tick{'s' if tick_count != 1 else ''}",
            enabled=not emit_json,
        ) as status:
            def _update_run_progress(tick_ordinal: int, event: dict[str, object]) -> None:
                status.update(
                    detail=" · ".join(
                        part
                        for part in [
                            f"tick {tick_ordinal}/{tick_count}",
                            _format_tick_stage(event),
                        ]
                        if part
                    )
                )

            def _persist_progress(latest, completed: int) -> None:
                store.save(latest)
                provider_detail = _format_provider_usage(client)
                status.update(
                    detail=" · ".join(
                        part
                        for part in [
                            f"{completed}/{tick_count} tick{'s' if tick_count != 1 else ''}",
                            _format_tick_summary(
                                latest.current_timeline_index,
                                int(latest.metadata.get("last_tick_minutes", 0) or 0),
                                tick_count=int(latest.metadata.get("tick_count", 0) or 0),
                                llm_issue_count=int(latest.metadata.get("last_tick_llm_issue_count", 0) or 0),
                                total_llm_issue_count=int(latest.metadata.get("llm_issue_count", 0) or 0),
                            ),
                            provider_detail,
                        ]
                        if part
                    )
                )

            updated = advance_session(
                session,
                client,
                ticks=args.ticks,
                debug_session=debug_session,
                settings=settings,
                on_tick=_persist_progress,
                on_progress=_update_run_progress,
            )
            store.save(updated)
            if emit_json:
                print(json.dumps(session_report(updated), indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "Simulation complete",
                    " · ".join(
                        part
                        for part in [
                            f"ran {tick_count} tick{'s' if tick_count != 1 else ''}",
                            _format_tick_summary(
                                updated.current_timeline_index,
                                int(updated.metadata.get("last_tick_minutes", 0) or 0),
                                tick_count=int(updated.metadata.get("tick_count", 0) or 0),
                                llm_issue_count=int(updated.metadata.get("last_tick_llm_issue_count", 0) or 0),
                                total_llm_issue_count=int(updated.metadata.get("llm_issue_count", 0) or 0),
                            ),
                            _format_provider_usage(client),
                        ]
                        if part
                    ),
                )
        return 0

    if args.command == "background":
        client = build_llm_client(settings, debug_session)
        workspace_dir = Path(args.workspace)
        store = build_runtime_store(
            workspace_dir,
            settings=settings,
            session_id=args.session_id,
        )
        _ensure_existing_session_can_be_modified(
            store,
            command="background",
            session_id=args.session_id,
            overwrite=bool(getattr(args, "overwrite", True)),
        )
        session = load_required_session(
            store,
            command="background",
            workspace_dir=workspace_dir,
            session_id=args.session_id,
        )
        emit_json = bool(getattr(args, "json", False))
        runner = BackgroundMaintenanceRunner(client, debug_session=debug_session)
        with _CliStatusLine(
            "Maintaining world...",
            enabled=not emit_json,
        ) as status:
            updated = runner.run_due_jobs(
                session,
                max_jobs=args.max_jobs or None,
            )
            store.save(updated)
            if emit_json:
                print(json.dumps(session_report(updated), indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "World maintenance complete",
                    " · ".join(
                        part
                        for part in [
                            _format_background_summary(updated),
                            _format_provider_usage(client),
                        ]
                        if part
                    ),
                )
        return 0

    if args.command == "branch":
        workspace_dir = Path(args.workspace)
        source_store = build_runtime_store(
            workspace_dir,
            settings=settings,
            session_id=args.session_id,
        )
        session = load_required_session(
            source_store,
            command="branch",
            workspace_dir=workspace_dir,
            session_id=args.session_id,
        )
        branched = branch_session(
            session,
            timeline_index=args.timeline_index,
            before_event_id=args.before_event_id,
        )
        if debug_session is not None:
            debug_session.event(
                "cli.branch.done",
                source_session_id=args.session_id,
                output_session_id=args.output_session_id or args.session_id,
                branched_timeline_index=branched.current_timeline_index,
            )
        target_workspace = Path(args.output_workspace) if args.output_workspace else Path(args.workspace)
        target_store = build_runtime_store(
            target_workspace,
            settings=settings,
            session_id=args.output_session_id or args.session_id,
        )
        _ensure_target_not_exists(
            target_store,
            command="branch",
            session_id=args.output_session_id or args.session_id,
            overwrite=bool(getattr(args, "overwrite", False)),
        )
        target_store.save(branched)
        if getattr(args, "json", False):
            print(json.dumps(session_report(branched), indent=2, ensure_ascii=False))
        else:
            print(
                _format_status_line(
                    "Branch ready",
                    _format_session_ready_detail(branched),
                    phase="done",
                    pretty=_supports_pretty_status(sys.stdout),
                    unicode_ok=_supports_unicode(sys.stdout),
                )
            )
        return 0

    if args.command == "migrate":
        runner = build_migration_runner(args.database_url or settings.database_url)
        emit_json = bool(getattr(args, "json", False))
        with _CliStatusLine(
            "Applying migration...",
            enabled=not emit_json,
        ) as status:
            applied_sql = runner.apply()
            if debug_session is not None:
                debug_session.event(
                    "cli.migrate.done",
                    bytes_applied=len(applied_sql),
                )
            if emit_json:
                print(json.dumps({"applied": True, "bytes": len(applied_sql)}, indent=2, ensure_ascii=False))
            else:
                status.finish(
                    "Migration complete",
                    f"{len(applied_sql)} bytes applied",
                )
        return 0

    if args.command == "visualize":
        workspace_path = Path(args.workspace)
        session_filename = "simulation_session.json"
        if args.session_id != "default":
            session_filename = f"simulation_session.{args.session_id}.json"
        session_path = workspace_path / session_filename
        if not session_path.exists():
            raise FileNotFoundError(
                "No simulation session file found at "
                f"{session_path}. Initialize or run a session before opening the visualization."
            )
        root_dir = Path(__file__).resolve().parents[2]
        session_relative_path = os.path.relpath(
            session_path.resolve(),
            (root_dir / "visualization").resolve(),
        )
        server, actual_port = start_visualization_server(
            root_dir=root_dir,
            host=args.host,
            port=args.port,
        )
        url = build_visualization_url(
            host=args.host,
            port=actual_port,
            session_relative_path=session_relative_path.replace(os.sep, "/"),
        )
        requested_port = int(args.port)
        port_note = ""
        if requested_port == 0:
            port_note = "auto-selected port"
        elif actual_port != requested_port:
            port_note = f"requested {requested_port} unavailable; using {actual_port}"
        if getattr(args, "json", False):
            print(
                json.dumps(
                    {
                        "serving": str(root_dir),
                        "session": str(session_path),
                        "requested_port": requested_port,
                        "port": actual_port,
                        "port_note": port_note,
                        "url": url,
                    },
                    indent=2,
                    ensure_ascii=False,
                )
            )
        else:
            print(
                _format_status_line(
                    "Visualization ready",
                    " · ".join(part for part in [url, port_note] if part),
                    phase="done",
                    pretty=_supports_pretty_status(sys.stdout),
                    unicode_ok=_supports_unicode(sys.stdout),
                )
            )
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
