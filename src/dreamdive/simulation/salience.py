from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from dreamdive.simulation.seeds import SimulationSeed


@dataclass
class SalienceWeights:
    urgency: float = 0.25
    conflict: float = 0.25
    emotional_charge: float = 0.2
    world_importance: float = 0.15
    novelty: float = 0.15


def compute_salience(
    seed: SimulationSeed,
    *,
    narrative_tension: float = 0.5,
    weights: SalienceWeights | None = None,
) -> float:
    active_weights = weights or SalienceWeights()
    score = (
        active_weights.urgency * seed.urgency
        + active_weights.conflict * seed.conflict
        + active_weights.emotional_charge * seed.emotional_charge
        + active_weights.world_importance * seed.world_importance
        + active_weights.novelty * seed.novelty
    )
    boosted = score * (0.75 + (0.5 * narrative_tension))
    return max(0.0, min(1.0, boosted))


def rank_seeds(
    seeds: Iterable[SimulationSeed],
    *,
    narrative_tension: float = 0.5,
    weights: SalienceWeights | None = None,
) -> List[SimulationSeed]:
    ranked = []
    for seed in seeds:
        seed.salience = compute_salience(
            seed,
            narrative_tension=narrative_tension,
            weights=weights,
        )
        ranked.append(seed)
    return sorted(ranked, key=lambda item: item.salience, reverse=True)
