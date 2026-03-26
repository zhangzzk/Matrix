from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from dreamdive.schemas import (
    AgentBeatPayload,
    BackgroundEventPayload,
    CharacterSnapshot,
    ResolutionCheckPayload,
    SceneSetupPayload,
    UnifiedScenePayload,
)
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.event_prompts import (
    build_agent_beat_prompt,
    build_background_event_prompt,
    build_resolution_check_prompt,
    build_spotlight_setup_prompt,
    build_unified_scene_prompt,
)
from dreamdive.simulation.seeds import SimulationSeed


@dataclass
class SpotlightTurn:
    agent_id: str
    internal: Dict[str, object]
    external: Dict[str, object]
    held_back: str
    beat_index: int


@dataclass
class SpotlightResult:
    scene_setup: SceneSetupPayload
    transcript: List[SpotlightTurn]
    resolution: ResolutionCheckPayload
    private_state_by_agent: Dict[str, List[Dict[str, object]]] = field(default_factory=dict)


class EventSimulator:
    def __init__(self, llm_client, context_assembler: Optional[ContextAssembler] = None) -> None:
        self.llm_client = llm_client
        self.context_assembler = context_assembler or ContextAssembler()

    def simulate_background(
        self,
        *,
        seed: SimulationSeed,
        snapshots: List[CharacterSnapshot],
        current_time: str,
        writing_style_note: str = "",
        language_guidance: str = "",
    ) -> BackgroundEventPayload:
        prompt = build_background_event_prompt(
            seed=seed,
            snapshots=snapshots,
            current_time=current_time,
            writing_style_note=writing_style_note,
            language_guidance=language_guidance,
        )
        return asyncio.run(self.llm_client.call_json(prompt, BackgroundEventPayload))

    def simulate_unified(
        self,
        *,
        seed: SimulationSeed,
        snapshots: List[CharacterSnapshot],
        narrative_phase: str,
        tension_level: float,
        relevant_threads: List[str],
        voice_samples_by_agent: Optional[Dict[str, List[str]]] = None,
        world_entities_by_agent: Optional[Dict[str, List[Dict[str, object]]]] = None,
        max_beats: int = 8,
        language_guidance: str = "",
    ) -> SpotlightResult:
        """Generate a complete scene with a single LLM call.

        This replaces the beat-by-beat loop (1 setup + N beat + resolution
        check calls) with one unified prompt that produces the entire scene.
        """
        snapshot_by_id = {s.identity.character_id: s for s in snapshots}

        # Pre-assemble context packets for every participant so the unified
        # prompt can include each character's epistemically-isolated context.
        context_packets = {}
        for snapshot in snapshots:
            agent_id = snapshot.identity.character_id
            context_packets[agent_id] = self.context_assembler.assemble(
                snapshot=snapshot,
                scene_description=seed.description,
                scene_participants=seed.participants,
                time_label=seed.location,
                world_entities=(world_entities_by_agent or {}).get(agent_id, []),
            )

        prompt = build_unified_scene_prompt(
            seed=seed,
            snapshots=snapshots,
            context_packets=context_packets,
            narrative_phase=narrative_phase,
            tension_level=tension_level,
            relevant_threads=relevant_threads,
            voice_samples_by_agent=voice_samples_by_agent,
            max_beats=max_beats,
            language_guidance=language_guidance,
        )

        scene = asyncio.run(self.llm_client.call_json(prompt, UnifiedScenePayload))

        # Convert the unified response into the same SpotlightResult that
        # downstream code already consumes.
        transcript: List[SpotlightTurn] = []
        private_state: Dict[str, List[Dict[str, object]]] = {
            agent_id: [] for agent_id in seed.participants
        }

        for beat_index, beat in enumerate(scene.beats):
            turn = SpotlightTurn(
                agent_id=beat.agent_id,
                internal=beat.internal.model_dump(mode="json"),
                external=beat.external.model_dump(mode="json"),
                held_back=beat.held_back,
                beat_index=beat_index,
            )
            transcript.append(turn)
            if beat.agent_id in private_state:
                private_state[beat.agent_id].append(turn.internal)

        # Build a SceneSetupPayload from the unified response so callers
        # that inspect scene_setup still get meaningful data.
        scene_setup = SceneSetupPayload(
            scene_opening=scene.scene_opening,
            resolution_conditions={
                "primary": scene.resolution.scene_outcome,
                "secondary": "",
                "forced_exit": "",
            },
            agent_perceptions={},
            tension_signature=scene.tension_signature,
        )

        resolution = ResolutionCheckPayload(
            resolved=scene.resolution.resolved,
            resolution_type=scene.resolution.resolution_type,
            scene_outcome=scene.resolution.scene_outcome,
            continue_scene=not scene.resolution.resolved,
        )

        return SpotlightResult(
            scene_setup=scene_setup,
            transcript=transcript,
            resolution=resolution,
            private_state_by_agent=private_state,
        )

    def simulate_spotlight(
        self,
        *,
        seed: SimulationSeed,
        snapshots: List[CharacterSnapshot],
        narrative_phase: str,
        tension_level: float,
        relevant_threads: List[str],
        voice_samples_by_agent: Optional[Dict[str, List[str]]] = None,
        world_entities_by_agent: Optional[Dict[str, List[Dict[str, object]]]] = None,
        max_beats: int = 8,
        language_guidance: str = "",
        use_unified: bool = True,
    ) -> SpotlightResult:
        """Simulate a spotlight scene.

        When *use_unified* is True (the default), the scene is generated in
        a single LLM call via :meth:`simulate_unified`.  Set it to False to
        fall back to the legacy beat-by-beat loop.
        """
        if use_unified:
            return self.simulate_unified(
                seed=seed,
                snapshots=snapshots,
                narrative_phase=narrative_phase,
                tension_level=tension_level,
                relevant_threads=relevant_threads,
                voice_samples_by_agent=voice_samples_by_agent,
                world_entities_by_agent=world_entities_by_agent,
                max_beats=max_beats,
                language_guidance=language_guidance,
            )

        return self._simulate_spotlight_legacy(
            seed=seed,
            snapshots=snapshots,
            narrative_phase=narrative_phase,
            tension_level=tension_level,
            relevant_threads=relevant_threads,
            voice_samples_by_agent=voice_samples_by_agent,
            world_entities_by_agent=world_entities_by_agent,
            max_beats=max_beats,
            language_guidance=language_guidance,
        )

    def _simulate_spotlight_legacy(
        self,
        *,
        seed: SimulationSeed,
        snapshots: List[CharacterSnapshot],
        narrative_phase: str,
        tension_level: float,
        relevant_threads: List[str],
        voice_samples_by_agent: Optional[Dict[str, List[str]]] = None,
        world_entities_by_agent: Optional[Dict[str, List[Dict[str, object]]]] = None,
        max_beats: int = 8,
        language_guidance: str = "",
    ) -> SpotlightResult:
        """Original beat-by-beat spotlight simulation (kept for backward compatibility)."""
        snapshot_by_id = {snapshot.identity.character_id: snapshot for snapshot in snapshots}
        setup_prompt = build_spotlight_setup_prompt(
            seed=seed,
            narrative_phase=narrative_phase,
            tension_level=tension_level,
            relevant_threads=relevant_threads,
            language_guidance=language_guidance,
        )
        scene_setup = asyncio.run(self.llm_client.call_json(setup_prompt, SceneSetupPayload))

        transcript: List[SpotlightTurn] = []
        private_state: Dict[str, List[Dict[str, object]]] = {agent_id: [] for agent_id in seed.participants}
        participants = seed.participants[:]
        beat_index = 0
        resolution = ResolutionCheckPayload(
            resolved=False,
            resolution_type="continue",
            scene_outcome="",
            continue_scene=True,
        )

        while beat_index < max_beats:
            agent_id = participants[beat_index % len(participants)]
            snapshot = snapshot_by_id[agent_id]
            perceived_transcript = self._transcript_for_agent(transcript, agent_id)
            last_beat = perceived_transcript[-1] if perceived_transcript else {}
            beat_prompt = build_agent_beat_prompt(
                snapshot=snapshot,
                context_packet=self.context_assembler.assemble(
                    snapshot=snapshot,
                    scene_description=scene_setup.scene_opening,
                    scene_participants=seed.participants,
                    time_label=seed.location,
                    world_entities=(world_entities_by_agent or {}).get(agent_id, []),
                ),
                perceived_transcript=perceived_transcript,
                scene_setup=scene_setup,
                last_beat=last_beat,
                voice_samples=(voice_samples_by_agent or {}).get(agent_id, []),
                language_guidance=language_guidance,
            )
            beat = asyncio.run(self.llm_client.call_json(beat_prompt, AgentBeatPayload))
            turn = SpotlightTurn(
                agent_id=agent_id,
                internal=beat.internal.model_dump(mode="json"),
                external=beat.external.model_dump(mode="json"),
                held_back=beat.held_back,
                beat_index=beat_index,
            )
            transcript.append(turn)
            private_state[agent_id].append(turn.internal)

            # Skip resolution check for the first 2 beats to save LLM calls.
            # In most cases, a scene needs at least 3 beats to reach any meaningful resolution.
            if beat_index >= 2:
                resolution_prompt = build_resolution_check_prompt(
                    scene_transcript=self._public_transcript(transcript),
                    scene_setup=scene_setup,
                    beat_count=beat_index + 1,
                    max_beats=max_beats,
                    language_guidance=language_guidance,
                )
                resolution = asyncio.run(
                    self.llm_client.call_json(resolution_prompt, ResolutionCheckPayload)
                )

            beat_index += 1
            if resolution.resolved or not resolution.continue_scene:
                break

        if not resolution.resolved and beat_index >= max_beats:
            resolution = ResolutionCheckPayload(
                resolved=True,
                resolution_type="forced_exit",
                scene_outcome=scene_setup.resolution_conditions.forced_exit,
                continue_scene=False,
            )

        return SpotlightResult(
            scene_setup=scene_setup,
            transcript=transcript,
            resolution=resolution,
            private_state_by_agent=private_state,
        )

    def simulate_foreground(
        self,
        *,
        seed: SimulationSeed,
        snapshots: List[CharacterSnapshot],
        narrative_phase: str,
        tension_level: float,
        relevant_threads: List[str],
        voice_samples_by_agent: Optional[Dict[str, List[str]]] = None,
        world_entities_by_agent: Optional[Dict[str, List[Dict[str, object]]]] = None,
        max_beats: int = 4,
        language_guidance: str = "",
    ) -> SpotlightResult:
        return self.simulate_spotlight(
            seed=seed,
            snapshots=snapshots,
            narrative_phase=narrative_phase,
            tension_level=tension_level,
            relevant_threads=relevant_threads,
            voice_samples_by_agent=voice_samples_by_agent,
            world_entities_by_agent=world_entities_by_agent,
            max_beats=max_beats,
            language_guidance=language_guidance,
        )

    @staticmethod
    def _public_transcript(transcript: List[SpotlightTurn]) -> List[Dict[str, object]]:
        return [
            {
                "agent_id": turn.agent_id,
                "external": turn.external,
                "beat_index": turn.beat_index,
            }
            for turn in transcript
        ]

    @staticmethod
    def _transcript_for_agent(
        transcript: List[SpotlightTurn],
        agent_id: str,
    ) -> List[Dict[str, object]]:
        visible = []
        for turn in transcript:
            item = {
                "agent_id": turn.agent_id,
                "external": turn.external,
                "beat_index": turn.beat_index,
            }
            if turn.agent_id == agent_id:
                item["internal"] = turn.internal
                item["held_back"] = turn.held_back
            visible.append(item)
        return visible
