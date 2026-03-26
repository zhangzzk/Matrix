from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from dreamdive.memory.retrieval import (
    build_entity_semantic_text,
    cosine_similarity,
    embed_text,
    retrieve_memories,
    tokenize,
)
from dreamdive.schemas import AgentContextPacket, CharacterSnapshot, EpisodicMemory


class ContextAssembler:
    """Programmatic context slicing that preserves epistemic isolation."""

    def assemble(
        self,
        *,
        snapshot: CharacterSnapshot,
        scene_description: str,
        scene_participants: Optional[Sequence[str]] = None,
        time_label: str = "",
        world_entities: Optional[List[Dict[str, object]]] = None,
        episodic_memories: Optional[Sequence[EpisodicMemory]] = None,
        recent_events: Optional[Sequence[str]] = None,
        max_memories: int = 3,
    ) -> AgentContextPacket:
        participants = list(scene_participants or [])
        relevant_relationships = [
            {
                "target_id": relation.to_character_id,
                "summary": relation.summary,
                "reason": relation.reason,
            }
            for relation in snapshot.relationships
            if not participants or relation.to_character_id in participants
        ][:4]
        location = str(snapshot.current_state.get("location", ""))
        current_state = {
            **dict(snapshot.current_state),
            "active_goals": [
                {"priority": goal.priority, "description": goal.description, "challenge": goal.challenge}
                for goal in sorted(snapshot.goals, key=lambda goal: goal.priority)[:3]
            ],
        }
        memory_items = retrieve_memories(
            list(episodic_memories or snapshot.working_memory),
            scene_description=scene_description,
            scene_participants=participants,
            location=location,
            current_state=current_state,
            max_results=max_memories,
        )
        # Compact identity — exclude verbose fields already covered by
        # the identity anchor in the beat prompt to save tokens.
        identity_data = snapshot.identity.model_dump(mode="json")
        compact_identity = {
            "character_id": identity_data.get("character_id"),
            "name": identity_data.get("name"),
            "background": identity_data.get("background"),
            "core_traits": identity_data.get("core_traits", [])[:4],
            "values": identity_data.get("values", [])[:3],
            "desires": identity_data.get("desires", [])[:3],
            "fears": identity_data.get("fears", [])[:2],
            "personality_summary": identity_data.get("personality_summary", ""),
        }
        return AgentContextPacket(
            identity=compact_identity,
            current_state=current_state,
            working_memory=[memory.summary for memory in memory_items],
            recent_events=list(recent_events or []),
            relationship_context=relevant_relationships,
            world_entities=[],  # Entity system disabled — skip semantic scoring.
            scene_context={
                "description": scene_description,
                "time": time_label,
                "participants": participants,
                "location": location,
            },
        )

    def _filter_world_entities(
        self,
        world_entities: Sequence[Dict[str, object]],
        *,
        scene_description: str,
        current_state: Dict[str, object],
        limit: int = 5,
    ) -> List[Dict[str, object]]:
        if not world_entities:
            return []

        query_terms = tokenize(scene_description)
        query_terms.update(tokenize(str(current_state.get("location", ""))))
        for goal in current_state.get("active_goals", []):
            if isinstance(goal, dict):
                query_terms.update(tokenize(str(goal.get("goal", ""))))
                query_terms.update(tokenize(str(goal.get("obstacle", ""))))
        query_embedding = embed_text(" ".join(sorted(query_terms)))

        scored: List[tuple[float, Dict[str, object]]] = []
        for entity in world_entities:
            entity_terms = self._entity_terms(entity)
            overlap = 0.0
            if query_terms and entity_terms:
                overlap = len(query_terms & entity_terms) / float(len(query_terms))
            entity_embedding = entity.get("semantic_embedding")
            if not isinstance(entity_embedding, Sequence):
                entity_embedding = embed_text(build_entity_semantic_text(entity))
            vector_score = cosine_similarity(query_embedding, entity_embedding)

            emotional_charge = str(entity.get("emotional_charge", "")).strip()
            emotional_bonus = 0.1 if emotional_charge else 0.0
            scored.append(
                (
                    (0.75 * vector_score) + (0.15 * overlap) + emotional_bonus,
                    self._public_entity_view(entity),
                )
            )

        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        selected = [entity for score, entity in ranked if score > 0][:limit]
        if selected:
            return selected
        return [self._public_entity_view(entity) for entity in world_entities[:limit]]

    @staticmethod
    def _entity_terms(entity: Dict[str, object]) -> set[str]:
        values: List[str] = []
        for key in (
            "name",
            "type",
            "narrative_role",
            "belief",
            "goal_relevance",
            "misunderstanding",
            "emotional_charge",
        ):
            value = entity.get(key)
            if isinstance(value, str):
                values.append(value)
        terms = set()
        for value in values:
            terms.update(tokenize(value))
        return terms

    @staticmethod
    def _public_entity_view(entity: Dict[str, object]) -> Dict[str, object]:
        return {
            key: value
            for key, value in dict(entity).items()
            if key not in {"semantic_embedding", "semantic_text"}
        }
