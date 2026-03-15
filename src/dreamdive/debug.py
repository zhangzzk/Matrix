from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slugify(value: str) -> str:
    cleaned = []
    for char in value:
        if char.isalnum():
            cleaned.append(char.lower())
        elif char in {"-", "_"}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned).strip("_") or "item"


@dataclass
class DebugSession:
    root_dir: Path
    record_llm: bool = True
    session_id: str = ""
    _counter: int = 0
    _attempt_dirs: Dict[int, Path] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        *,
        debug_dir: Optional[Path] = None,
        record_llm: bool = True,
    ) -> "DebugSession":
        if debug_dir is None:
            root_dir = Path(tempfile.mkdtemp(prefix="dreamdive-debug-"))
        else:
            debug_dir.mkdir(parents=True, exist_ok=True)
            root_dir = Path(tempfile.mkdtemp(prefix="run_", dir=debug_dir))
        session = cls(
            root_dir=root_dir,
            record_llm=record_llm,
            session_id=root_dir.name,
        )
        (session.root_dir / "llm").mkdir(parents=True, exist_ok=True)
        (session.root_dir / "session.json").write_text(
            json.dumps(
                {
                    "created_at": _utc_now(),
                    "record_llm": record_llm,
                    "root_dir": str(session.root_dir),
                    "session_id": session.session_id,
                    "pid": os.getpid(),
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return session

    @property
    def events_path(self) -> Path:
        return self.root_dir / "events.jsonl"

    def event(self, name: str, **payload: Any) -> None:
        record = {
            "at": _utc_now(),
            "event": name,
            "payload": payload,
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        summary = " ".join(f"{key}={payload[key]!r}" for key in sorted(payload))
        if summary:
            print(f"[dreamdive-debug] {name} {summary}", file=sys.stderr)
        else:
            print(f"[dreamdive-debug] {name}", file=sys.stderr)

    def start_llm_attempt(
        self,
        *,
        profile_name: str,
        prompt_name: str,
        schema_name: str,
        attempt_index: int,
        prompt_payload: Dict[str, Any],
    ) -> int:
        self._counter += 1
        attempt_id = self._counter
        if not self.record_llm:
            return attempt_id
        attempt_dir = (
            self.root_dir
            / "llm"
            / f"{attempt_id:04d}_{_slugify(profile_name)}_{_slugify(prompt_name)}"
        )
        attempt_dir.mkdir(parents=True, exist_ok=True)
        self._attempt_dirs[attempt_id] = attempt_dir
        (attempt_dir / "request.json").write_text(
            json.dumps(
                {
                    "at": _utc_now(),
                    "profile_name": profile_name,
                    "prompt_name": prompt_name,
                    "schema_name": schema_name,
                    "attempt_index": attempt_index,
                    "prompt": prompt_payload,
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return attempt_id

    def finish_llm_attempt(
        self,
        attempt_id: int,
        *,
        raw_response: Optional[str] = None,
        parsed_payload: Optional[Dict[str, Any]] = None,
        error_message: str = "",
    ) -> None:
        if not self.record_llm:
            return
        attempt_dir = self._attempt_dirs.get(attempt_id)
        if attempt_dir is None:
            return
        if raw_response is not None:
            (attempt_dir / "response.txt").write_text(raw_response, encoding="utf-8")
        if parsed_payload is not None:
            (attempt_dir / "parsed.json").write_text(
                json.dumps(parsed_payload, indent=2, sort_keys=True, ensure_ascii=False),
                encoding="utf-8",
            )
        (attempt_dir / "result.json").write_text(
            json.dumps(
                {
                    "at": _utc_now(),
                    "error_message": error_message,
                    "has_raw_response": raw_response is not None,
                    "has_parsed_payload": parsed_payload is not None,
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
