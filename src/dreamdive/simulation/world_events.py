from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from dreamdive.simulation.seeds import SimulationSeed


def _urgency_to_score(urgency: str) -> float:
    normalized = urgency.strip().lower()
    if normalized == "high":
        return 0.9
    if normalized == "medium":
        return 0.6
    if normalized == "low":
        return 0.3
    return 0.5


@dataclass
class WorldEventCascade:
    description: str
    affected_agents: List[str]
    delay_minutes: int
    urgency: str = "medium"
    location: str = ""


@dataclass
class ScheduledWorldEvent:
    event_id: str
    trigger_timeline_index: int
    description: str
    affected_agents: List[str]
    urgency: str = "medium"
    location: str = ""
    cascades: List[WorldEventCascade] = field(default_factory=list)

    def to_seed(self) -> SimulationSeed:
        urgency_score = _urgency_to_score(self.urgency)
        return SimulationSeed(
            seed_id=self.event_id,
            seed_type="world",
            participants=list(self.affected_agents),
            location=self.location,
            description=self.description,
            urgency=urgency_score,
            conflict=0.2,
            emotional_charge=max(0.3, urgency_score - 0.1),
            world_importance=max(0.6, urgency_score),
            novelty=0.4,
        )


class WorldEventScheduler:
    def __init__(self, scheduled_events: List[ScheduledWorldEvent] | None = None) -> None:
        self.pending_events: List[ScheduledWorldEvent] = list(scheduled_events or [])
        self.fired_event_ids: List[str] = []

    def schedule(self, event: ScheduledWorldEvent) -> None:
        self.pending_events.append(event)
        self.pending_events.sort(key=lambda item: (item.trigger_timeline_index, item.event_id))

    def next_trigger_delta(self, current_timeline_index: int) -> int | None:
        if not self.pending_events:
            return None
        next_index = min(event.trigger_timeline_index for event in self.pending_events)
        return max(0, next_index - current_timeline_index)

    def consume_due_events(self, current_timeline_index: int, dt_minutes: int) -> List[SimulationSeed]:
        horizon = current_timeline_index + dt_minutes
        due = [
            event
            for event in self.pending_events
            if event.trigger_timeline_index <= horizon
        ]
        if not due:
            return []

        self.pending_events = [
            event
            for event in self.pending_events
            if event.trigger_timeline_index > horizon
        ]

        emitted = []
        for event in due:
            self.fired_event_ids.append(event.event_id)
            emitted.append(event.to_seed())
            for index, cascade in enumerate(event.cascades):
                self.schedule(
                    ScheduledWorldEvent(
                        event_id="{}_cascade_{:02d}".format(event.event_id, index + 1),
                        trigger_timeline_index=event.trigger_timeline_index + cascade.delay_minutes,
                        description=cascade.description,
                        affected_agents=list(cascade.affected_agents),
                        urgency=cascade.urgency,
                        location=cascade.location,
                    )
                )
        return emitted
