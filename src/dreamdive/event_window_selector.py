"""Event window selection for narrative synthesis.

Determines which simulation events belong in which chapter based on:
- Tick ranges and story time
- Salience scores (with user preferences applied)
- POV character preferences
- Chapter pacing settings
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from dreamdive.narrative_synthesis import ChapterWindow, EventSummary
from dreamdive.schemas import EpisodicMemory, StateChangeLogEntry
from dreamdive.simulation.session import SimulationSessionState
from dreamdive.user_config import UserMeta


def select_chapter_window(
    events: List[EpisodicMemory],
    *,
    start_tick_index: int,
    end_tick_index: int,
    user_meta: Optional[UserMeta] = None,
    min_salience: float = 0.3,
    max_events_per_chapter: int = 20,
    event_details_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    state_changes_by_event: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
) -> ChapterWindow:
    """Select events for a chapter from a tick range.

    Args:
        events: All simulation events
        start_tick_index: Starting tick index (inclusive)
        end_tick_index: Ending tick index (inclusive)
        user_meta: User preferences for focus and pacing
        min_salience: Minimum salience to include (default 0.3)
        max_events_per_chapter: Maximum events to include

    Returns:
        ChapterWindow ready for synthesis
    """
    event_details_by_id = event_details_by_id or {}
    state_changes_by_event = state_changes_by_event or {}

    # Filter events in tick range
    events_in_range = [
        event
        for event in events
        if start_tick_index <= event.replay_key.timeline_index <= end_tick_index
    ]

    # Sort by salience (descending)
    events_in_range.sort(key=lambda e: e.salience, reverse=True)

    # Filter by minimum salience
    significant_events = [
        event for event in events_in_range if event.salience >= min_salience
    ]

    # Apply user preferences: boost focus character events
    if user_meta and user_meta.focus_characters:
        # Reorder to prioritize focus character events
        focus_events = [
            event
            for event in significant_events
            if any(char in user_meta.focus_characters for char in event.participants)
        ]
        other_events = [
            event
            for event in significant_events
            if not any(
                char in user_meta.focus_characters for char in event.participants
            )
        ]
        significant_events = focus_events + other_events

    # Limit to max events per chapter
    selected_events = significant_events[:max_events_per_chapter]

    # Convert to EventSummary format
    event_summaries = []
    for event in selected_events:
        event_id = event.event_id or f"mem_{event.replay_key.tick}_{event.replay_key.event_sequence}"
        details = event_details_by_id.get(event_id, {})
        participants = list(details.get("participants", event.participants))
        location = str(details.get("location", event.location or "") or "")
        summary = str(
            details.get("summary")
            or details.get("outcome_summary")
            or event.summary
        )
        scene_transcript = str(details.get("description", "") or "")
        state_changes = dict(state_changes_by_event.get(event_id, {}))
        event_summaries.append(
            EventSummary(
                event_id=event_id,
                salience=event.salience,
                participants=participants,
                location=location,
                summary=summary,
                scene_transcript=scene_transcript,
                state_changes=state_changes,
            )
        )

    # Identify high-salience events (top 20% or salience > 0.7)
    salience_threshold = 0.7
    high_salience_events = [
        summary.event_id
        for summary in event_summaries
        if summary.salience >= salience_threshold
    ]

    # Build tick range string
    tick_range = f"tick_{start_tick_index:04d}-tick_{end_tick_index:04d}"

    return ChapterWindow(
        tick_range=tick_range,
        events=event_summaries,
        high_salience_events=high_salience_events,
    )


def select_chapter_window_from_session(
    session: SimulationSessionState,
    *,
    start_tick_index: int,
    end_tick_index: int,
    user_meta: Optional[UserMeta] = None,
    min_salience: float = 0.3,
    max_events_per_chapter: int = 20,
) -> ChapterWindow:
    """Build a synthesis window directly from the session append-only log."""
    append_only_log = session.append_only_log or {}
    return select_chapter_window(
        _deduplicate_memories(append_only_log.get("episodic_memories", [])),
        start_tick_index=start_tick_index,
        end_tick_index=end_tick_index,
        user_meta=user_meta,
        min_salience=min_salience,
        max_events_per_chapter=max_events_per_chapter,
        event_details_by_id=_index_event_details(append_only_log.get("event_log", [])),
        state_changes_by_event=_index_state_changes(append_only_log.get("state_changes", [])),
    )


def calculate_chapter_boundaries(
    total_ticks: int,
    *,
    user_meta: Optional[UserMeta] = None,
    default_ticks_per_chapter: int = 10,
) -> List[tuple[int, int]]:
    """Calculate chapter boundaries for a simulation.

    Args:
        total_ticks: Total number of simulation ticks
        user_meta: User preferences (for pacing)
        default_ticks_per_chapter: Default ticks per chapter

    Returns:
        List of (start_tick, end_tick) tuples
    """
    ticks_per_chapter = _target_ticks_per_chapter(
        user_meta=user_meta,
        default_ticks_per_chapter=default_ticks_per_chapter,
        event_count=0,
        total_ticks=total_ticks,
    )

    boundaries: List[tuple[int, int]] = []
    current_tick = 0

    while current_tick < total_ticks:
        end_tick = min(current_tick + ticks_per_chapter - 1, total_ticks - 1)
        boundaries.append((current_tick, end_tick))
        current_tick = end_tick + 1

    return boundaries


def calculate_chapter_boundaries_from_session(
    session: SimulationSessionState,
    *,
    start_tick_index: int,
    end_tick_index: int,
    user_meta: Optional[UserMeta] = None,
    default_ticks_per_chapter: int = 0,
) -> List[tuple[int, int]]:
    """Infer chapter boundaries from the simulation event stream.

    Falls back to simple fixed-size windows if the session does not have
    enough event-log structure to infer narrative breakpoints.
    """
    total_ticks = max(0, end_tick_index - start_tick_index + 1)
    if total_ticks <= 0:
        return []

    append_only_log = session.append_only_log or {}
    raw_events = list(append_only_log.get("event_log", []))
    normalized_events = _normalize_boundary_events(
        raw_events,
        start_tick_index=start_tick_index,
        end_tick_index=end_tick_index,
    )
    if len(normalized_events) < 2:
        return [
            (start_tick_index + start, start_tick_index + end)
            for start, end in calculate_chapter_boundaries(
                total_ticks,
                user_meta=user_meta,
                default_ticks_per_chapter=default_ticks_per_chapter,
            )
        ]

    target_ticks = _target_ticks_per_chapter(
        user_meta=user_meta,
        default_ticks_per_chapter=default_ticks_per_chapter,
        event_count=len(normalized_events),
        total_ticks=total_ticks,
    )
    min_ticks = max(3, target_ticks // 2)
    max_ticks = max(min_ticks + 2, target_ticks * 2)
    target_events = max(3, min(8, round(len(normalized_events) / max(1, total_ticks / target_ticks))))
    min_events = max(2, target_events // 2)
    max_events = max(min_events + 2, target_events * 2)

    boundaries: List[tuple[int, int]] = []
    chapter_start = start_tick_index
    chapter_start_event_index = 0

    for index in range(len(normalized_events) - 1):
        current = normalized_events[index]
        nxt = normalized_events[index + 1]
        current_tick = int(current["timeline_index"])
        next_tick = int(nxt["timeline_index"])
        if next_tick <= current_tick:
            continue

        chapter_span = current_tick - chapter_start + 1
        chapter_event_count = index - chapter_start_event_index + 1
        break_score = _chapter_break_score(current, nxt, target_ticks=target_ticks)

        should_break = False
        if chapter_span >= max_ticks or chapter_event_count >= max_events:
            should_break = True
        elif chapter_event_count >= min_events and chapter_span >= min_ticks and break_score >= 0.8:
            should_break = True
        elif break_score >= 1.1:
            should_break = True

        if not should_break:
            continue

        split_tick = _split_tick_between(current_tick, next_tick)
        if split_tick < chapter_start:
            continue
        boundaries.append((chapter_start, split_tick))
        chapter_start = split_tick + 1
        chapter_start_event_index = index + 1

    if not boundaries:
        return [
            (start_tick_index + start, start_tick_index + end)
            for start, end in calculate_chapter_boundaries(
                total_ticks,
                user_meta=user_meta,
                default_ticks_per_chapter=default_ticks_per_chapter,
            )
        ]

    if chapter_start <= end_tick_index:
        boundaries.append((chapter_start, end_tick_index))

    return _merge_short_boundary_tail(
        boundaries,
        min_ticks=min_ticks,
        min_events=min_events,
        events=normalized_events,
    )


def extract_voice_samples(
    novel_meta: "MetaLayerRecord",  # type: ignore
    max_samples: int = 3,
) -> List[str]:
    """Extract voice samples from novel meta for synthesis.

    Args:
        novel_meta: Meta layer record with writing style
        max_samples: Maximum samples to extract

    Returns:
        List of sample passages
    """
    from dreamdive.ingestion.models import MetaLayerRecord

    if not isinstance(novel_meta, MetaLayerRecord):
        return []

    samples: List[str] = []

    # Extract from writing style sample passages
    if novel_meta.writing_style.sample_passages:
        for passage in novel_meta.writing_style.sample_passages[:max_samples]:
            if passage.text:
                samples.append(passage.text)

    # If not enough samples, try character voice samples
    if len(samples) < max_samples and novel_meta.character_voices:
        for voice in novel_meta.character_voices[:2]:  # Max 2 character samples
            if voice.sample_dialogues and voice.sample_dialogues[0].text:
                samples.append(voice.sample_dialogues[0].text)

    return samples[:max_samples]


def _target_ticks_per_chapter(
    *,
    user_meta: Optional[UserMeta],
    default_ticks_per_chapter: int,
    event_count: int,
    total_ticks: int,
) -> int:
    ticks_per_chapter = max(0, int(default_ticks_per_chapter or 0))

    if user_meta and user_meta.chapter_format.story_time_per_chapter:
        pacing = user_meta.chapter_format.story_time_per_chapter.lower()
        if "fast" in pacing or "rapid" in pacing:
            return 5
        if "slow" in pacing or "detailed" in pacing:
            return 20

    if ticks_per_chapter > 0:
        return ticks_per_chapter

    if event_count > 0 and total_ticks > 0:
        density = event_count / max(1, total_ticks)
        if density > 0:
            estimated = round(6 / density)
            return max(6, min(40, estimated))

    return 10


def _normalize_boundary_events(
    raw_events: Sequence[dict],
    *,
    start_tick_index: int,
    end_tick_index: int,
) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for order, item in enumerate(raw_events):
        try:
            timeline_index = int(item.get("timeline_index", 0) or 0)
        except (TypeError, ValueError):
            continue
        if timeline_index < start_tick_index or timeline_index > end_tick_index:
            continue
        normalized.append(
            {
                "order": order,
                "event_id": str(item.get("event_id", "") or ""),
                "timeline_index": timeline_index,
                "salience": float(item.get("salience", 0.0) or 0.0),
                "location": str(item.get("location", "") or ""),
                "participants": list(item.get("participants", [])),
                "resolution_mode": str(item.get("resolution_mode", "") or ""),
            }
        )
    normalized.sort(key=lambda item: (int(item["timeline_index"]), int(item["order"])))
    return normalized


def _chapter_break_score(
    current: Dict[str, Any],
    nxt: Dict[str, Any],
    *,
    target_ticks: int,
) -> float:
    current_tick = int(current["timeline_index"])
    next_tick = int(nxt["timeline_index"])
    gap = max(1, next_tick - current_tick)
    gap_score = min(0.8, gap / max(1, target_ticks))
    if gap >= max(2, target_ticks // 2):
        gap_score += 0.25

    salience_now = float(current.get("salience", 0.0) or 0.0)
    salience_next = float(nxt.get("salience", 0.0) or 0.0)
    salience_score = 0.0
    if salience_now >= 0.75:
        salience_score += 0.2
    if salience_now - salience_next >= 0.2:
        salience_score += 0.2

    location_score = 0.0
    if str(current.get("location", "") or "") != str(nxt.get("location", "") or ""):
        location_score += 0.2

    participant_score = 0.0
    current_participants = set(str(item) for item in current.get("participants", []) if str(item))
    next_participants = set(str(item) for item in nxt.get("participants", []) if str(item))
    if current_participants or next_participants:
        overlap = len(current_participants & next_participants)
        union = len(current_participants | next_participants)
        if union > 0 and overlap / union < 0.34:
            participant_score += 0.2

    resolution_score = 0.0
    if str(current.get("resolution_mode", "") or "") in {"spotlight", "foreground"}:
        resolution_score += 0.15

    return gap_score + salience_score + location_score + participant_score + resolution_score


def _split_tick_between(current_tick: int, next_tick: int) -> int:
    gap = max(1, next_tick - current_tick)
    if gap <= 1:
        return current_tick
    return current_tick + (gap // 2)


def _merge_short_boundary_tail(
    boundaries: List[tuple[int, int]],
    *,
    min_ticks: int,
    min_events: int,
    events: Sequence[Dict[str, Any]],
) -> List[tuple[int, int]]:
    if len(boundaries) < 2:
        return boundaries

    last_start, last_end = boundaries[-1]
    last_span = last_end - last_start + 1
    last_event_count = sum(
        1
        for item in events
        if last_start <= int(item["timeline_index"]) <= last_end
    )
    if last_span >= min_ticks or last_event_count >= min_events:
        return boundaries

    previous_start, _previous_end = boundaries[-2]
    merged = list(boundaries[:-2])
    merged.append((previous_start, last_end))
    return merged


def _deduplicate_memories(raw_memories: List[dict]) -> List[EpisodicMemory]:
    merged: Dict[str, EpisodicMemory] = {}
    for item in raw_memories:
        memory = EpisodicMemory.model_validate(item)
        key = _memory_key(memory)
        existing = merged.get(key)
        if existing is None:
            merged[key] = memory
            continue
        merged[key] = _merge_memories(existing, memory)
    return list(merged.values())


def _memory_key(memory: EpisodicMemory) -> str:
    if memory.event_id:
        return memory.event_id
    return (
        f"{memory.replay_key.timeline_index}:"
        f"{memory.replay_key.event_sequence}:"
        f"{memory.summary}"
    )


def _merge_memories(left: EpisodicMemory, right: EpisodicMemory) -> EpisodicMemory:
    participants = sorted(set(left.participants) | set(right.participants))
    preferred = left if left.salience >= right.salience else right
    return preferred.model_copy(
        update={
            "participants": participants,
            "location": preferred.location or left.location or right.location,
            "salience": max(left.salience, right.salience),
        }
    )


def _index_event_details(raw_events: List[dict]) -> Dict[str, Dict[str, Any]]:
    indexed: Dict[str, Dict[str, Any]] = {}
    for item in raw_events:
        event_id = str(item.get("event_id", "") or "")
        if not event_id:
            continue
        indexed[event_id] = {
            "participants": list(item.get("participants", [])),
            "location": item.get("location", ""),
            "description": item.get("description", ""),
            "outcome_summary": item.get("outcome_summary", ""),
            "summary": item.get("outcome_summary") or item.get("description") or "",
        }
    return indexed


def _index_state_changes(raw_state_changes: List[dict]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    indexed: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for item in raw_state_changes:
        entry = StateChangeLogEntry.model_validate(item)
        if not entry.event_id:
            continue
        character_changes = indexed.setdefault(entry.event_id, {}).setdefault(
            entry.character_id,
            {},
        )
        character_changes[entry.dimension] = entry.to_value
    return indexed
