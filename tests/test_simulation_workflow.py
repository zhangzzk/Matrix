import json
import tempfile
import unittest
from pathlib import Path

from dreamdive.config import LLMProfileSettings
from dreamdive.ingestion.extractor import ArtifactStore
from dreamdive.llm.client import StructuredLLMClient
from dreamdive.simulation.runtime_store import SimulationRuntimeStore
from dreamdive.simulation.workflow import (
    advance_session,
    initialize_session,
    run_session_tick,
    session_report,
)


class RecordingTransport:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    async def complete(self, profile, prompt):
        schema = prompt.metadata.get("response_schema", "unknown")
        print(f"MOCK CALL #{self.calls}: {schema}")
        response = self.responses[self.calls]
        self.calls += 1
        return response


def build_client(responses):
    return StructuredLLMClient(
        primary=LLMProfileSettings(
            name="moonshot",
            base_url="https://api.moonshot.ai/v1",
            model="kimi-k2.5",
        ),
        fallback=LLMProfileSettings(
            name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            model="gemini-3.1-flash-lite-preview",
        ),
        transport=RecordingTransport(responses),
        retry_attempts=1,
        retry_delay_seconds=0,
    )


class SimulationWorkflowTests(unittest.TestCase):
    def test_initialize_session_and_run_tick_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "novel.md"
            source_path.write_text("# Chapter 1\nArya hides in the yard.", encoding="utf-8")

            artifact_store = ArtifactStore(root / "artifacts")
            artifact_store.save_chapter_snapshot(
                type(
                    "Chapter",
                    (),
                    {"chapter_id": "001", "order_index": 1},
                )(),
                type(
                    "Accumulated",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "characters": [
                                {
                                    "id": "arya",
                                    "name": "Arya Stark",
                                    "aliases": [],
                                    "identity": {"background": "young noble"},
                                    "personality": {
                                        "traits": ["brave"],
                                        "values": ["family"],
                                        "fears": ["capture"],
                                        "desires": ["survive"],
                                    },
                                    "current_state": {
                                        "emotional_state": "afraid",
                                        "physical_state": "tired",
                                        "location": "yard",
                                        "goal_stack": ["stay hidden"],
                                    },
                                    "relationships": [],
                                    "memory_seeds": [],
                                }
                            ],
                            "world": {
                                "setting": "Winterfell",
                                "time_period": "medieval",
                                "locations": ["yard"],
                                "rules_and_constraints": [],
                                "factions": [],
                            },
                            "events": [
                                {
                                    "id": "evt_news",
                                    "time": "t1",
                                    "location": "yard",
                                    "participants": ["arya"],
                                    "summary": "A guard changes the patrol route.",
                                    "consequences": [],
                                    "participant_knowledge": {},
                                }
                            ],
                            "meta": {},
                        }
                    },
                )(),
            )
            artifact_store.save_meta_layer(
                type(
                    "Meta",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "authorial": {
                                "central_thesis": {},
                                "themes": [],
                                "dominant_tone": "tense",
                                "beliefs_about": {},
                                "symbolic_motifs": [],
                                "narrative_perspective": "third_limited",
                            },
                            "writing_style": {
                                "prose_description": "lean and cold",
                                "sentence_rhythm": "clipped",
                                "description_density": "sparse",
                                "dialogue_narration_balance": "dialogue-led",
                                "stylistic_signatures": [],
                                "sample_passages": [],
                            },
                            "language_context": {
                                "primary_language": "English",
                                "language_variety": "close-third literary English",
                                "language_style": "compressed and pressure-driven",
                                "author_style": "spare realism with hard edges",
                                "register_profile": "plain diction with occasional noble formality",
                                "dialogue_style": "short, defensive exchanges",
                                "figurative_patterns": ["cold-weather imagery"],
                                "multilingual_features": [],
                                "translation_notes": ["Keep the surface blunt and the subtext tight."],
                            },
                            "character_voices": [
                                {
                                    "character_id": "arya",
                                    "vocabulary_register": "plain",
                                    "speech_patterns": ["short sentences"],
                                    "rhetorical_tendencies": "declarative",
                                    "gravitates_toward": ["survival"],
                                    "what_they_never_say": "I am afraid",
                                    "emotional_register": "suppressed",
                                    "sample_dialogues": [
                                        {"text": "Not today.", "why_representative": "blunt"}
                                    ],
                                }
                            ],
                            "real_world_context": {
                                "written_when": "",
                                "historical_context": "",
                                "unspeakable_constraints": [],
                                "literary_tradition": "",
                                "autobiographical_elements": "",
                            },
                        }
                    },
                )()
            )
            artifact_store.save_entity_extraction(
                type(
                    "Entities",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "entities": [
                                {
                                    "entity_id": "ent_001",
                                    "name": "The Gate",
                                    "type": "place",
                                    "objective_facts": ["north wall"],
                                    "narrative_role": "constraint",
                                    "absent_figure_details": {
                                        "reason_absent": "",
                                        "most_present_in": [],
                                        "counterfactual": "",
                                    },
                                    "concept_details": {
                                        "definitions_by_character": {},
                                        "who_weaponizes": [],
                                        "who_is_bound_by": [],
                                        "authorial_stance": "",
                                    },
                                    "agent_representations": [
                                        {
                                            "agent_id": "arya",
                                            "belief": "the only exit",
                                            "emotional_charge": "fear",
                                            "goal_relevance": "reach it unseen",
                                            "misunderstanding": "",
                                            "confidence": "EXPLICIT",
                                        }
                                    ],
                                }
                            ]
                        }
                    },
                )()
            )

            client = build_client(
                [
                    json.dumps(
                        {
                            "emotional_state": {
                                "dominant": "fear",
                                "secondary": ["resolve"],
                                "confidence": 0.2,
                            },
                            "immediate_tension": "",
                            "unspoken_subtext": "",
                            "physical_state": {
                                "energy": 0.5,
                                "injuries_or_constraints": "",
                                "location": "yard",
                                "current_activity": "hiding",
                            },
                            "knowledge_state": {
                                "new_knowledge": [],
                                "active_misbeliefs": [],
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "goal_stack": [
                                {
                                    "priority": 1,
                                    "goal": "stay hidden",
                                    "motivation": "survival",
                                    "obstacle": "guards nearby",
                                    "time_horizon": "immediate",
                                    "emotional_charge": "fear",
                                    "abandon_condition": "safe exit appears",
                                }
                            ],
                            "actively_avoiding": "thinking about home",
                            "most_uncertain_relationship": "",
                        }
                    ),
# removed unused projections and collisions
                    json.dumps(
                        {
                            "narrative_summary": "Arya listened as the patrol shifted away from her hiding place.",
                            "outcomes": [
                                {
                                    "agent_id": "arya",
                                    "goal_status": "advanced",
                                    "new_knowledge": "The route changed.",
                                    "emotional_delta": "fear sharpening into focus",
                                }
                            ],
                            "relationship_deltas": [],
                            "unexpected": "",
                        }
                    ),
                    json.dumps(
                        {
                            "emotional_delta": {
                                "dominant_now": "sharp focus",
                                "underneath": "fear",
                                "shift_reason": "The new route creates an opening",
                            },
                            "goal_stack_update": {
                                "top_goal_status": "advanced",
                                "top_goal_still_priority": True,
                                "new_goal": None,
                                "resolved_goal": None,
                            },
                            "relationship_updates": [],
                            "needs_reprojection": False,
                            "reprojection_reason": "",
                        }
                    ),
                    json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
                    json.dumps(
                        {
                            "emotional_delta": {
                                "dominant_now": "sharp focus",
                                "underneath": "fear",
                                "shift_reason": "The new route creates an opening",
                            },
                            "goal_stack_update": {
                                "top_goal_status": "advanced",
                                "top_goal_still_priority": True,
                                "new_goal": None,
                                "resolved_goal": None,
                            },
                            "relationship_updates": [],
                            "needs_reprojection": False,
                            "reprojection_reason": "",
                        }
                    ),
                ]
            )

            session = initialize_session(
                source_path=source_path,
                workspace_dir=root,
                chapter_id="001",
                tick_label="snapshot",
                timeline_index=0,
                llm_client=client,
                character_ids=["arya"],
                max_workers=1,
            )
            store = SimulationRuntimeStore(root)
            store.save(session)
            reloaded = store.load()
            updated = run_session_tick(reloaded, client)

            self.assertIn("arya", updated.agents)
            self.assertEqual(updated.agents["arya"].snapshot.goals[0].goal, "stay hidden")
            self.assertTrue(updated.agents["arya"].voice_samples)
            self.assertEqual(updated.agents["arya"].world_entities[0]["name"], "The Gate")
            self.assertGreaterEqual(updated.current_timeline_index, 0)
            self.assertIn("last_tick_minutes", updated.metadata)
            self.assertIn("tick_cooldown_remaining", updated.metadata)
            self.assertEqual(updated.metadata["language_context"]["primary_language"], "English")
            self.assertIn("Author style: spare realism with hard edges", updated.metadata["language_guidance"])
            self.assertIn("episodic_memories", updated.append_only_log)
            self.assertGreaterEqual(len(updated.append_only_log["episodic_memories"]), 2)
            self.assertIn("state_changes", updated.append_only_log)
            self.assertGreaterEqual(len(updated.append_only_log["state_changes"]), 2)

            follow_up_client = build_client(
                [
                    json.dumps({"goal_tensions": [], "solo_seeds": [], "world_events": []}),
                ]
            )
            second = advance_session(updated, follow_up_client, ticks=1)
            report = session_report(second)

            self.assertGreaterEqual(second.current_timeline_index, updated.current_timeline_index)
            self.assertEqual(report["agent_count"], 1)
            self.assertIn("log_counts", report)
            self.assertGreaterEqual(report["log_counts"]["episodic_memories"], 2)
            self.assertEqual(updated.metadata["tick_count"], 1)
            self.assertEqual(second.metadata["tick_count"], 2)

    def test_initialize_session_requires_language_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "novel.md"
            source_path.write_text("# Chapter 1\n路明非坐在列车里。", encoding="utf-8")

            artifact_store = ArtifactStore(root / "artifacts")
            artifact_store.save_chapter_snapshot(
                type("Chapter", (), {"chapter_id": "001", "order_index": 1})(),
                type(
                    "Accumulated",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "characters": [
                                {
                                    "id": "mingfei",
                                    "name": "路明非",
                                    "aliases": [],
                                    "identity": {"background": "student"},
                                    "personality": {
                                        "traits": ["hesitant"],
                                        "values": ["safety"],
                                        "fears": ["the unknown"],
                                        "desires": ["normalcy"],
                                    },
                                    "current_state": {
                                        "emotional_state": "uneasy",
                                        "physical_state": "tense",
                                        "location": "train",
                                        "goal_stack": ["stay calm"],
                                    },
                                    "relationships": [],
                                    "memory_seeds": [],
                                }
                            ],
                            "world": {
                                "setting": "CC1000列车",
                                "time_period": "2009",
                                "locations": ["train"],
                                "rules_and_constraints": [],
                                "factions": [],
                            },
                            "events": [],
                            "meta": {},
                        }
                    },
                )(),
            )
            artifact_store.save_meta_layer(
                type(
                    "Meta",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "authorial": {
                                "central_thesis": {},
                                "themes": [],
                                "dominant_tone": "",
                                "beliefs_about": {},
                                "symbolic_motifs": [],
                                "narrative_perspective": "",
                            },
                            "writing_style": {
                                "prose_description": "",
                                "sentence_rhythm": "",
                                "description_density": "",
                                "dialogue_narration_balance": "",
                                "stylistic_signatures": [],
                                "sample_passages": [],
                            },
                            "language_context": {
                                "primary_language": "",
                                "language_variety": "",
                                "language_style": "",
                                "author_style": "",
                                "register_profile": "",
                                "dialogue_style": "",
                                "figurative_patterns": [],
                                "multilingual_features": [],
                                "translation_notes": [],
                            },
                            "character_voices": [],
                            "real_world_context": {
                                "written_when": "",
                                "historical_context": "",
                                "unspeakable_constraints": [],
                                "literary_tradition": "",
                                "autobiographical_elements": "",
                            },
                        }
                    },
                )()
            )

            client = build_client([])
            with self.assertRaisesRegex(ValueError, "Language guidance is missing"):
                initialize_session(
                    source_path=source_path,
                    workspace_dir=root,
                    chapter_id="001",
                    tick_label="snapshot",
                    timeline_index=0,
                    llm_client=client,
                    character_ids=["mingfei"],
                )

    def test_short_excerpt_full_loop_persists_two_agent_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            source_path = root / "novel.md"
            source_path.write_text(
                (
                    "# Chapter 1\n"
                    "Arya ducked into the forge just as Gendry barred the side door. "
                    "Both heard boots in the courtyard and realized only one route remained open.\n"
                ),
                encoding="utf-8",
            )

            artifact_store = ArtifactStore(root / "artifacts")
            artifact_store.save_chapter_snapshot(
                type(
                    "Chapter",
                    (),
                    {"chapter_id": "001", "order_index": 1},
                )(),
                type(
                    "Accumulated",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "characters": [
                                {
                                    "id": "arya",
                                    "name": "Arya Stark",
                                    "aliases": [],
                                    "identity": {"background": "runaway noble"},
                                    "personality": {
                                        "traits": ["furtive", "brave"],
                                        "values": ["family"],
                                        "fears": ["capture"],
                                        "desires": ["escape"],
                                    },
                                    "current_state": {
                                        "emotional_state": "tense",
                                        "physical_state": "coiled",
                                        "location": "forge",
                                        "goal_stack": ["escape through the forge"],
                                    },
                                    "relationships": [
                                        {
                                            "target_id": "gendry",
                                            "trust": 0.3,
                                            "sentiment": "uneasy alliance",
                                            "shared_history_summary": "He once helped her hide.",
                                        }
                                    ],
                                    "memory_seeds": ["Gendry helped Arya once before."],
                                },
                                {
                                    "id": "gendry",
                                    "name": "Gendry",
                                    "aliases": [],
                                    "identity": {"background": "smith's apprentice"},
                                    "personality": {
                                        "traits": ["stubborn", "protective"],
                                        "values": ["loyalty"],
                                        "fears": ["betrayal"],
                                        "desires": ["keep the forge safe"],
                                    },
                                    "current_state": {
                                        "emotional_state": "guarded",
                                        "physical_state": "ready",
                                        "location": "forge",
                                        "goal_stack": ["hold the forge door"],
                                    },
                                    "relationships": [
                                        {
                                            "target_id": "arya",
                                            "trust": 0.35,
                                            "sentiment": "protective suspicion",
                                            "shared_history_summary": "Arya arrives with trouble.",
                                        }
                                    ],
                                    "memory_seeds": ["Arya always brings danger with her."],
                                },
                            ],
                            "world": {
                                "setting": "Winterfell forge",
                                "time_period": "medieval",
                                "locations": ["forge", "courtyard"],
                                "rules_and_constraints": [],
                                "factions": [],
                            },
                            "events": [],
                            "meta": {},
                        }
                    },
                )(),
            )
            artifact_store.save_meta_layer(
                type(
                    "Meta",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "authorial": {
                                "central_thesis": {"value": "survival strains trust"},
                                "themes": [{"name": "trust under pressure"}],
                                "dominant_tone": "tight",
                                "beliefs_about": {},
                                "symbolic_motifs": [],
                                "narrative_perspective": "third_limited",
                            },
                            "writing_style": {
                                "prose_description": "lean and urgent",
                                "sentence_rhythm": "clipped",
                                "description_density": "sparse",
                                "dialogue_narration_balance": "balanced",
                                "stylistic_signatures": [],
                                "sample_passages": [],
                            },
                            "character_voices": [
                                {
                                    "character_id": "arya",
                                    "vocabulary_register": "plain",
                                    "speech_patterns": ["blunt", "short clauses"],
                                    "rhetorical_tendencies": "deflective",
                                    "gravitates_toward": ["escape"],
                                    "what_they_never_say": "I need help",
                                    "emotional_register": "suppressed",
                                    "sample_dialogues": [
                                        {"text": "Move.", "why_representative": "compressed urgency"}
                                    ],
                                },
                                {
                                    "character_id": "gendry",
                                    "vocabulary_register": "working-class plain",
                                    "speech_patterns": ["direct", "grounded"],
                                    "rhetorical_tendencies": "protective",
                                    "gravitates_toward": ["duty"],
                                    "what_they_never_say": "I am scared",
                                    "emotional_register": "restrained",
                                    "sample_dialogues": [
                                        {"text": "Not through that door.", "why_representative": "firm boundary"}
                                    ],
                                },
                            ],
                            "real_world_context": {
                                "written_when": "",
                                "historical_context": "",
                                "unspeakable_constraints": [],
                                "literary_tradition": "",
                                "autobiographical_elements": "",
                            },
                        }
                    },
                )()
            )
            artifact_store.save_entity_extraction(
                type(
                    "Entities",
                    (),
                    {
                        "model_dump": lambda self, mode="json": {
                            "entities": [
                                {
                                    "entity_id": "ent_side_door",
                                    "name": "The Side Door",
                                    "type": "place",
                                    "objective_facts": ["opens into the courtyard", "currently barred"],
                                    "narrative_role": "constraint",
                                    "absent_figure_details": {
                                        "reason_absent": "",
                                        "most_present_in": [],
                                        "counterfactual": "",
                                    },
                                    "concept_details": {
                                        "definitions_by_character": {},
                                        "who_weaponizes": [],
                                        "who_is_bound_by": [],
                                        "authorial_stance": "",
                                    },
                                    "agent_representations": [
                                        {
                                            "agent_id": "arya",
                                            "belief": "her last clean escape",
                                            "emotional_charge": "panic",
                                            "goal_relevance": "must reach it first",
                                            "misunderstanding": "",
                                            "confidence": "EXPLICIT",
                                        },
                                        {
                                            "agent_id": "gendry",
                                            "belief": "the one way to keep soldiers out",
                                            "emotional_charge": "protective urgency",
                                            "goal_relevance": "must keep it shut",
                                            "misunderstanding": "",
                                            "confidence": "EXPLICIT",
                                        },
                                    ],
                                }
                            ]
                        }
                    },
                )()
            )

            client = build_client(
                [
                    json.dumps(
                        {
                            "emotional_state": {
                                "dominant": "tense",
                                "secondary": ["alert"],
                                "confidence": 0.1,
                            },
                            "immediate_tension": "Boots are closing in outside.",
                            "unspoken_subtext": "",
                            "physical_state": {
                                "energy": 0.7,
                                "injuries_or_constraints": "",
                                "location": "forge",
                                "current_activity": "watching the side door",
                            },
                            "knowledge_state": {
                                "new_knowledge": [],
                                "active_misbeliefs": [],
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "goal_stack": [
                                {
                                    "priority": 1,
                                    "goal": "escape through the forge",
                                    "motivation": "survive and stay free",
                                    "obstacle": "Gendry blocks the route",
                                    "time_horizon": "immediate",
                                    "emotional_charge": "urgent",
                                    "abandon_condition": "a safer route appears",
                                }
                            ],
                            "actively_avoiding": "asking directly for help",
                            "most_uncertain_relationship": "gendry",
                        }
                    ),
                    json.dumps(
                        {
                            "emotional_state": {
                                "dominant": "guarded",
                                "secondary": ["protective"],
                                "confidence": 0.1,
                            },
                            "immediate_tension": "Someone will force the forge soon.",
                            "unspoken_subtext": "",
                            "physical_state": {
                                "energy": 0.8,
                                "injuries_or_constraints": "",
                                "location": "forge",
                                "current_activity": "bracing the door",
                            },
                            "knowledge_state": {
                                "new_knowledge": [],
                                "active_misbeliefs": [],
                            },
                        }
                    ),
                    json.dumps(
                        {
                            "goal_stack": [
                                {
                                    "priority": 1,
                                    "goal": "hold the forge door",
                                    "motivation": "keep everyone inside alive",
                                    "obstacle": "Arya wants the door open",
                                    "time_horizon": "immediate",
                                    "emotional_charge": "protective",
                                    "abandon_condition": "the soldiers pass by",
                                }
                            ],
                            "actively_avoiding": "admitting he trusts Arya",
                            "most_uncertain_relationship": "arya",
                        }
                    ),
                    json.dumps(
                        {
                            "primary_intention": "slip past Gendry and reach the side door",
                            "motivation": "survive",
                            "immediate_next_action": "edge toward the barred exit",
                            "contingencies": [],
                            "greatest_fear_this_horizon": "being trapped",
                            "abandon_condition": "a different exit opens",
                            "held_back_impulse": "draw her blade",
                            "projection_horizon": "5 ticks",
                        }
                    ),
                    json.dumps(
                        {
                            "primary_intention": "keep Arya from opening the forge",
                            "motivation": "protect the forge",
                            "immediate_next_action": "hold position at the door",
                            "contingencies": [],
                            "greatest_fear_this_horizon": "soldiers rushing in",
                            "abandon_condition": "the danger passes",
                            "held_back_impulse": "shout for the guards",
                            "projection_horizon": "5 ticks",
                        }
                    ),
                    json.dumps(
                        {
                            "goal_tensions": [],
                            "solo_seeds": [],
                            "world_events": [],
                        }
                    ),
                    json.dumps(
                        {
                            "narrative_summary": "Arya and Gendry hold the forge together long enough to hear the patrol move away from the courtyard.",
                            "outcomes": [
                                {
                                    "agent_id": "arya",
                                    "goal_status": "advanced",
                                    "new_knowledge": "The patrol is moving away from the forge.",
                                    "emotional_delta": "fear settling into resolve",
                                },
                                {
                                    "agent_id": "gendry",
                                    "goal_status": "advanced",
                                    "new_knowledge": "Arya will wait if given a real opening.",
                                    "emotional_delta": "protectiveness easing into caution",
                                },
                            ],
                            "relationship_deltas": [],
                            "unexpected": "",
                        }
                    ),
                    json.dumps(
                        {
                            "emotional_delta": {
                                "dominant_now": "focused",
                                "underneath": "fear",
                                "shift_reason": "The threat passed.",
                            },
                            "goal_stack_update": {
                                "top_goal_status": "advanced",
                                "top_goal_still_priority": True,
                                "new_goal": None,
                                "resolved_goal": None,
                            },
                            "relationship_updates": [],
                            "needs_reprojection": False,
                            "reprojection_reason": "",
                        }
                    ),
                    json.dumps(
                        {
                            "emotional_delta": {
                                "dominant_now": "cautious",
                                "underneath": "protective",
                                "shift_reason": "They got away with it.",
                            },
                            "goal_stack_update": {
                                "top_goal_status": "advanced",
                                "top_goal_still_priority": True,
                                "new_goal": None,
                                "resolved_goal": None,
                            },
                            "relationship_updates": [],
                            "needs_reprojection": False,
                            "reprojection_reason": "",
                        }
                    ),
# Next block:
                    json.dumps(
                        {
                            "emotional_delta": {
                                "dominant_now": "steady",
                                "underneath": "protective",
                                "shift_reason": "Holding the forge worked for now.",
                            },
                            "goal_stack_update": {
                                "top_goal_status": "advanced",
                                "top_goal_still_priority": True,
                                "new_goal": None,
                                "resolved_goal": None,
                            },
                            "relationship_updates": [],
                            "needs_reprojection": False,
                            "reprojection_reason": "",
                        }
                    ),
                ]
            )

            session = initialize_session(
                source_path=source_path,
                workspace_dir=root,
                chapter_id="001",
                tick_label="excerpt_start",
                timeline_index=0,
                llm_client=client,
                character_ids=["arya", "gendry"],
                max_workers=1,
            )
            session = session.model_copy(
                update={
                    "arc_state": session.arc_state.model_copy(
                        update={
                            "current_phase": "rising_action",
                            "tension_level": 0.9,
                            "approaching_climax": True,
                            "unresolved_threads": ["who controls the side door"],
                        }
                    )
                }
            )

            store = SimulationRuntimeStore(root)
            store.save(session)
            updated = run_session_tick(store.load(), client)
            store.save(updated)
            reloaded = store.load()
            report = session_report(reloaded)

            self.assertEqual(updated.current_timeline_index, 13)
            self.assertEqual(updated.metadata["last_tick_minutes"], 13)
            self.assertEqual(set(updated.agents.keys()), {"arya", "gendry"})
            self.assertTrue(updated.agents["arya"].voice_samples)
            self.assertTrue(updated.agents["gendry"].voice_samples)
            self.assertEqual(updated.agents["arya"].world_entities[0]["name"], "The Side Door")
            self.assertEqual(updated.agents["gendry"].world_entities[0]["name"], "The Side Door")
            self.assertEqual(updated.metadata["recent_event_failures"], [])
            self.assertEqual(len(updated.append_only_log["event_log"]), 1)
            self.assertTrue(
                all(
                    set(item["participants"]) == {"arya", "gendry"}
                    for item in updated.append_only_log["event_log"]
                )
            )
            self.assertTrue(
                all(item["location"] == "forge" for item in updated.append_only_log["event_log"])
            )
            self.assertGreaterEqual(len(updated.append_only_log["episodic_memories"]), 4)
            self.assertIn("location_threads", updated.metadata)
            self.assertEqual(updated.metadata["location_threads"][0]["location"], "forge")
            self.assertEqual(set(updated.metadata["active_agent_scores"].keys()), {"arya", "gendry"})
            self.assertEqual(report["agent_count"], 2)
            self.assertEqual(report["log_counts"]["event_log"], 1)
            self.assertGreaterEqual(report["log_counts"]["episodic_memories"], 4)
            self.assertEqual(report["metadata"]["last_tick_minutes"], 13)


if __name__ == "__main__":
    unittest.main()
