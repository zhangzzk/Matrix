from __future__ import annotations

import argparse
import ast
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


CLI_DEFAULTS: Dict[str, Dict[str, object]] = {
    "_common": {
        "debug": False,
        "debug_dir": "",
        "config": "",
        "profile": "",
    },
    "ingest": {
        "source": "",
        "workspace": ".dreamdive",
        "skip_structural_scan": False,
        "rerun_structural_scan": False,
        "rerun_chapters": False,
        "skip_meta_layer": False,
        "rerun_meta_layer": False,
        "skip_entities": False,
        "rerun_entities": False,
        "max_workers": 4,
        "section_max_workers": 4,
    },
    "init": {
        "source": "",
        "chapter_id": "",
        "workspace": ".dreamdive",
        "tick_label": "snapshot",
        "timeline_index": 0,
        "character_ids": [],
        "session_id": "default",
        "overwrite": False,
        "max_workers": 4,
    },
    "tick": {
        "workspace": ".dreamdive",
        "session_id": "default",
        "overwrite": True,
        "tick_max_events": 15,
    },
    "run": {
        "workspace": ".dreamdive",
        "ticks": 1,
        "session_id": "default",
        "overwrite": True,
        "tick_max_events": 15,
    },
    "background": {
        "workspace": ".dreamdive",
        "max_jobs": 0,
        "max_workers": 4,
        "session_id": "default",
        "overwrite": True,
    },
    "branch": {
        "workspace": ".dreamdive",
        "output_workspace": "",
        "session_id": "default",
        "output_session_id": "",
        "overwrite": False,
    },
    "synthesize": {
        "workspace": ".dreamdive",
        "session_id": "default",
        "start_tick": None,
        "end_tick": None,
        "output_dir": "",
        "chapter_number": None,
    },
    "migrate": {
        "database_url": "",
    },
    "visualize": {
        "workspace": ".dreamdive",
        "session_id": "default",
        "host": "127.0.0.1",
        "port": 8000,
    },
}


def resolve_cli_config_path(
    explicit_path: Optional[str] = None,
    *,
    start_dir: Optional[Path] = None,
) -> Optional[Path]:
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    current = (start_dir or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        direct = directory / "dreamdive.toml"
        if direct.exists():
            return direct
        nested = directory / ".dreamdive" / "config.toml"
        if nested.exists():
            return nested
    return None


def _strip_comment(line: str) -> str:
    quoted = ""
    escaped = False
    output: list[str] = []
    for char in line:
        if escaped:
            output.append(char)
            escaped = False
            continue
        if char == "\\" and quoted:
            output.append(char)
            escaped = True
            continue
        if char in {'"', "'"}:
            output.append(char)
            if quoted == char:
                quoted = ""
            elif not quoted:
                quoted = char
            continue
        if char == "#" and not quoted:
            break
        output.append(char)
    return "".join(output).strip()


def _parse_scalar(raw_value: str) -> object:
    value = raw_value.strip()
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value.startswith("[") and value.endswith("]"):
        return ast.literal_eval(value)
    if value.startswith(("'", '"')):
        return ast.literal_eval(value)
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    raise ValueError(f"Unsupported TOML value: {raw_value}")


def parse_simple_toml(text: str) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    current: Dict[str, Any] = result
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = _strip_comment(raw_line)
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            if not section_name:
                raise ValueError(f"Empty TOML section at line {line_number}")
            current = result
            for part in section_name.split("."):
                key = part.strip()
                if not key:
                    raise ValueError(f"Invalid TOML section at line {line_number}")
                next_value = current.setdefault(key, {})
                if not isinstance(next_value, dict):
                    raise ValueError(f"TOML section conflict at line {line_number}")
                current = next_value
            continue
        if "=" not in line:
            raise ValueError(f"Invalid TOML line {line_number}: {raw_line}")
        key, raw_value = line.split("=", 1)
        name = key.strip()
        if not name:
            raise ValueError(f"Empty TOML key at line {line_number}")
        current[name] = _parse_scalar(raw_value)
    return result


def load_cli_config(path: Optional[Path]) -> Dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return parse_simple_toml(path.read_text(encoding="utf-8"))


def _mapping(root: Mapping[str, Any], *path: str) -> Dict[str, Any]:
    current: Any = root
    for part in path:
        if not isinstance(current, Mapping):
            return {}
        current = current.get(part, {})
    if not isinstance(current, Mapping):
        return {}
    return {key: value for key, value in current.items() if not isinstance(value, Mapping)}


def apply_cli_config(
    parsed_args: argparse.Namespace,
    config_data: Mapping[str, Any],
) -> argparse.Namespace:
    command = parsed_args.command
    profile = getattr(parsed_args, "profile", "")

    # Normalize legacy aliases
    _COMMAND_ALIASES: Dict[str, str] = {"init-snapshot": "init"}
    canonical_command = _COMMAND_ALIASES.get(command, command)

    merged: Dict[str, object] = {}
    merged.update(CLI_DEFAULTS.get("_common", {}))
    merged.update(CLI_DEFAULTS.get(canonical_command, {}))
    merged.update(_mapping(config_data, "defaults"))
    # Support both old and new config section names
    merged.update(_mapping(config_data, "init-snapshot") if canonical_command == "init" else {})
    merged.update(_mapping(config_data, canonical_command))
    if profile:
        merged.update(_mapping(config_data, "profiles", profile))
        merged.update(_mapping(config_data, "profiles", profile, command))
    for key, value in vars(parsed_args).items():
        if value is None:
            continue
        merged[key] = value
    return argparse.Namespace(**merged)
