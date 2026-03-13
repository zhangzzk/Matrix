from __future__ import annotations

from typing import Iterable, List

from dreamdive.db.models import EventLogRecord
from dreamdive.schemas import NarrativeArcState


class NarrativeArcTracker:
    def update_from_events(
        self,
        events: Iterable[EventLogRecord],
        *,
        previous: NarrativeArcState | None = None,
    ) -> NarrativeArcState:
        event_list = list(events)
        if not event_list:
            return previous or NarrativeArcState(
                current_phase="setup",
                tension_level=0.0,
                unresolved_threads=[],
                approaching_climax=False,
            )

        recent = sorted(event_list, key=lambda item: item.timeline_index)[-5:]
        avg_salience = sum(item.salience for item in recent) / len(recent)
        unresolved_threads = [item.event_id for item in recent if item.salience >= 0.5]
        phase = "setup"
        if avg_salience >= 0.75:
            phase = "climax" if len(unresolved_threads) <= 2 else "rising_action"
        elif avg_salience >= 0.45:
            phase = "rising_action"
        elif previous is not None:
            phase = previous.current_phase

        return NarrativeArcState(
            current_phase=phase,
            tension_level=max(previous.tension_level if previous else 0.0, avg_salience),
            unresolved_threads=unresolved_threads,
            approaching_climax=avg_salience >= 0.7,
        )
