from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class SimulationSeed:
    seed_id: str
    seed_type: str
    participants: List[str]
    location: str
    description: str
    urgency: float = 0.0
    conflict: float = 0.0
    emotional_charge: float = 0.0
    world_importance: float = 0.0
    novelty: float = 0.0
    salience: float = field(default=0.0, compare=False)
