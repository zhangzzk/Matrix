from __future__ import annotations

from collections.abc import Iterable
from hashlib import blake2b
import math
import re
from typing import Optional, Sequence

from dreamdive.schemas import EpisodicMemory


TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[a-z0-9']+")  # Chinese + ASCII
STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}
DEFAULT_EMBEDDING_DIMENSIONS = 1_536


def tokenize(text: str) -> set[str]:
    return {
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if token not in STOPWORDS
    }


def build_memory_semantic_text(memory: EpisodicMemory) -> str:
    return " ".join(
        part
        for part in (
            memory.summary,
            memory.location or "",
            " ".join(memory.participants),
            memory.emotional_tag or "",
        )
        if part
    )


def build_memory_query_text(
    *,
    scene_description: str,
    scene_participants: Optional[Sequence[str]] = None,
    location: str = "",
    current_state: Optional[dict] = None,
) -> str:
    query_terms = tokenize(scene_description)
    query_terms.update(tokenize(location))
    query_terms.update(_state_terms(current_state))
    return " ".join(
        part
        for part in (
            scene_description,
            location,
            " ".join(scene_participants or []),
            " ".join(sorted(query_terms)),
        )
        if part
    )


def build_entity_semantic_text(entity: dict) -> str:
    values = []
    for key in (
        "name",
        "type",
        "narrative_role",
        "belief",
        "goal_relevance",
        "misunderstanding",
        "emotional_charge",
        "semantic_text",
    ):
        value = entity.get(key)
        if isinstance(value, str) and value.strip():
            values.append(value.strip())
    return " ".join(values)


from functools import lru_cache


@lru_cache(maxsize=1024)
def embed_text(
    text: str,
    *,
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS,
) -> list[float]:
    dimensions = max(1, dimensions)
    vector = [0.0] * dimensions
    token_list = [
        token
        for token in TOKEN_PATTERN.findall(text.lower())
        if token not in STOPWORDS
    ]
    if not token_list:
        return vector

    for token in token_list:
        digest = blake2b(token.encode("utf-8"), digest_size=16).digest()
        index = int.from_bytes(digest[:8], "big") % dimensions
        sign = 1.0 if digest[8] % 2 == 0 else -1.0
        weight = 1.0 + ((digest[9] % 7) / 20.0)
        vector[index] += sign * weight

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0.0:
        return vector
    return [value / magnitude for value in vector]


try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    if _HAS_NUMPY:
        a = np.asarray(left, dtype=np.float32)
        b = np.asarray(right, dtype=np.float32)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a <= 0 or norm_b <= 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    limit = min(len(left), len(right))
    if limit <= 0:
        return 0.0
    dot = sum(left[index] * right[index] for index in range(limit))
    left_magnitude = math.sqrt(sum(left[index] * left[index] for index in range(limit)))
    right_magnitude = math.sqrt(sum(right[index] * right[index] for index in range(limit)))
    if left_magnitude <= 0.0 or right_magnitude <= 0.0:
        return 0.0
    return max(0.0, min(1.0, dot / (left_magnitude * right_magnitude)))


def batch_cosine_similarity(
    query_embedding: Sequence[float],
    target_embeddings: Sequence[Sequence[float]],
) -> list[float]:
    if not query_embedding or not target_embeddings:
        return [0.0] * len(target_embeddings)

    if _HAS_NUMPY:
        q = np.asarray(query_embedding, dtype=np.float32)
        targets = np.asarray(target_embeddings, dtype=np.float32)
        
        # Calculate dot products
        dots = np.dot(targets, q)
        
        # Calculate norms
        q_norm = np.linalg.norm(q)
        target_norms = np.linalg.norm(targets, axis=1)
        
        # Avoid division by zero
        if q_norm <= 0:
            return [0.0] * len(target_embeddings)
        
        # Calculate similarities
        with np.errstate(divide="ignore", invalid="ignore"):
            similarities = dots / (q_norm * target_norms)
            similarities = np.nan_to_num(similarities, nan=0.0)
            
        return similarities.tolist()

    # Fallback to loop
    return [cosine_similarity(query_embedding, target) for target in target_embeddings]


def rank_memories(
    memories: Iterable[EpisodicMemory],
    *,
    max_results: int,
) -> list[EpisodicMemory]:
    """Combine semantic relevance, salience, and recency from timeline position."""

    memory_list = list(memories)
    scored: list[tuple[float, EpisodicMemory]] = []
    pinned: list[EpisodicMemory] = []
    timeline_max = max(
        (memory.replay_key.timeline_index for memory in memory_list),
        default=0,
    )

    for memory in memory_list:
        if memory.pinned:
            pinned.append(memory)
            continue

        semantic_score = memory.semantic_score or 0.0
        timeline_gap = max(0, timeline_max - memory.replay_key.timeline_index)
        recency_score = 1.0 / (timeline_gap + 1)
        score = (0.5 * semantic_score) + (0.3 * recency_score) + (0.2 * memory.salience)
        scored.append((score, memory))

    pinned = sorted(
        pinned,
        key=lambda memory: (
            memory.replay_key.timeline_index,
            memory.replay_key.event_sequence,
        ),
        reverse=True,
    )
    ranked = [memory for _, memory in sorted(scored, key=lambda item: item[0], reverse=True)]
    deduped: list[EpisodicMemory] = []
    seen_summaries: set[str] = set()
    for memory in pinned:
        if memory.summary in seen_summaries:
            continue
        deduped.append(memory)
        seen_summaries.add(memory.summary)
    for memory in ranked:
        if memory.summary in seen_summaries:
            continue
        deduped.append(memory)
        seen_summaries.add(memory.summary)
        if len(deduped) >= len(pinned) + max_results:
            break

    return deduped


def _state_terms(current_state: Optional[dict]) -> set[str]:
    if not current_state:
        return set()

    values: list[str] = []
    for key in ("location", "physical_state", "current_activity"):
        value = current_state.get(key)
        if isinstance(value, str):
            values.append(value)

    emotional_state = current_state.get("emotional_state")
    if isinstance(emotional_state, str):
        values.append(emotional_state)
    elif isinstance(emotional_state, dict):
        for value in emotional_state.values():
            if isinstance(value, str):
                values.append(value)

    active_goals = current_state.get("active_goals", [])
    if isinstance(active_goals, Sequence):
        for goal in active_goals:
            if isinstance(goal, dict):
                for field in ("description", "challenge"):
                    value = goal.get(field)
                    if isinstance(value, str):
                        values.append(value)
            elif isinstance(goal, str):
                values.append(goal)
    terms: set[str] = set()
    for value in values:
        terms.update(tokenize(value))
    return terms


def retrieve_memories(
    memories: Sequence[EpisodicMemory],
    *,
    scene_description: str,
    scene_participants: Optional[Sequence[str]] = None,
    location: str = "",
    current_state: Optional[dict] = None,
    max_results: int = 5,
) -> list[EpisodicMemory]:
    """Score memories against the current scene before salience ranking."""

    if not memories:
        return []

    query_text = build_memory_query_text(
        scene_description=scene_description,
        scene_participants=scene_participants,
        location=location,
        current_state=current_state,
    )
    query_terms = tokenize(query_text)
    query_embedding = embed_text(query_text)

    participants = {participant for participant in scene_participants or [] if participant}
    scored: list[EpisodicMemory] = []
    for memory in memories:
        summary_terms = tokenize(memory.summary)
        overlap = 0.0
        if query_terms and summary_terms:
            overlap = len(query_terms & summary_terms) / float(len(query_terms))

        vector_score = cosine_similarity(
            query_embedding,
            memory.embedding or embed_text(build_memory_semantic_text(memory)),
        )

        participant_bonus = 0.0
        if participants and participants.intersection(memory.participants):
            participant_bonus = 0.2

        location_bonus = 0.0
        if location and memory.location and memory.location.lower() == location.lower():
            location_bonus = 0.15

        emotion_bonus = 0.0
        if current_state and isinstance(current_state.get("emotional_state"), str):
            emotional_state = current_state.get("emotional_state", "")
            if isinstance(memory.emotional_tag, str) and memory.emotional_tag:
                if memory.emotional_tag.lower() in emotional_state.lower():
                    emotion_bonus = 0.1

        relevance = min(
            1.0,
            (0.7 * vector_score)
            + (0.2 * overlap)
            + participant_bonus
            + location_bonus
            + emotion_bonus
            + (0.1 * (memory.semantic_score or 0.0)),
        )
        if not memory.pinned and relevance <= 0.0:
            continue
        scored.append(
            memory.model_copy(
                update={
                    "semantic_score": relevance,
                    "embedding": memory.embedding or embed_text(build_memory_semantic_text(memory)),
                }
            )
        )

    return rank_memories(scored, max_results=max_results)
