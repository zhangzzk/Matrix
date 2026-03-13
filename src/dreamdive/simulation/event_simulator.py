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
)
from dreamdive.simulation.context import ContextAssembler
from dreamdive.simulation.event_prompts import (
    build_agent_beat_prompt,
    build_background_event_prompt,
    build_resolution_check_prompt,
    build_spotlight_setup_prompt,
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
    ) -> SpotlightResult:
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
