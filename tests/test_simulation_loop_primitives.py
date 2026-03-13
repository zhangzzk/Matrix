import unittest

from dreamdive.schemas import (
    CharacterIdentity,
    CharacterSnapshot,
    Goal,
    NarrativeArcState,
    ReplayKey,
    RelationshipLogEntry,
    SnapshotInference,
)
from dreamdive.simulation.salience import compute_salience, rank_seeds
from dreamdive.simulation.seed_detector import SeedDetector
from dreamdive.simulation.seeds import SimulationSeed
from dreamdive.simulation.world_manager import WorldManager


def make_snapshot(
    *,
    character_id,
    name,
    location,
    confidence=0.0,
    tension="",
    goal_text=None,
):
    inferred = None
    if confidence or tension:
        inferred = SnapshotInference.model_validate(
            {
                "emotional_state": {
                    "dominant": "fear" if confidence else "calm",
                    "secondary": [],
                    "confidence": confidence,
                },
                "immediate_tension": tension,
                "unspoken_subtext": "hidden motive" if tension else "",
                "physical_state": {
                    "energy": 0.7,
                    "injuries_or_constraints": "",
                    "location": location,
                    "current_activity": "waiting",
                },
                "knowledge_state": {
                    "new_knowledge": [],
                    "active_misbeliefs": [],
                },
            }
        )
    goals = []
    if goal_text:
        goals = [
            Goal(
                priority=1,
                goal=goal_text,
                motivation="duty",
                obstacle="risk",
                time_horizon="immediate",
                emotional_charge="urgent",
                abandon_condition="mission complete",
            )
        ]
    return CharacterSnapshot(
        identity=CharacterIdentity(character_id=character_id, name=name),
        replay_key=ReplayKey(tick="chapter_01", timeline_index=1),
        current_state={"location": location},
        goals=goals,
        working_memory=[],
        relationships=[],
        inferred_state=inferred,
    )


class SimulationLoopPrimitiveTests(unittest.TestCase):
    def test_seed_detector_finds_spatial_and_solo_seeds(self) -> None:
        detector = SeedDetector()
        arya = make_snapshot(
            character_id="arya",
            name="Arya",
            location="courtyard",
            confidence=0.9,
            tension="Do not get caught",
            goal_text="escape the castle",
        )
        sansa = make_snapshot(
            character_id="sansa",
            name="Sansa",
            location="courtyard",
            confidence=0.2,
            tension="",
            goal_text=None,
        )

        spatial = detector.detect_spatial_collisions([arya, sansa])
        solo = detector.detect_solo_seeds([arya, sansa], threshold=0.6)

        self.assertEqual(len(spatial), 1)
        self.assertEqual(spatial[0].seed_type, "spatial_collision")
        self.assertEqual(len(spatial[0].participants), 2)
        self.assertEqual(len(solo), 1)
        self.assertEqual(solo[0].participants, ["arya"])

    def test_world_manager_selects_only_high_activation_agents(self) -> None:
        manager = WorldManager(activation_threshold=0.45)
        active = make_snapshot(
            character_id="arya",
            name="Arya",
            location="courtyard",
            confidence=0.8,
            tension="Do not get caught",
            goal_text="escape the castle",
        )
        inactive = make_snapshot(
            character_id="hotpie",
            name="Hot Pie",
            location="kitchen",
            confidence=0.0,
            tension="",
            goal_text=None,
        )

        selected = manager.select_active_agents(
            [active, inactive],
            current_timeline_index=60,
        )

        self.assertIn("arya", selected)
        self.assertNotIn("hotpie", selected)
        self.assertGreater(selected["arya"], 0.45)

    def test_world_manager_wakes_same_location_and_socially_connected_agents(self) -> None:
        manager = WorldManager(foreground_threshold=0.4)
        arya = make_snapshot(
            character_id="arya",
            name="Arya",
            location="courtyard",
            confidence=0.8,
            tension="Do not get caught",
            goal_text="escape the castle",
        )
        gendry = make_snapshot(
            character_id="gendry",
            name="Gendry",
            location="smithy",
            confidence=0.0,
            tension="",
            goal_text=None,
        ).model_copy(
            update={
                "relationships": [
                    RelationshipLogEntry(
                        from_character_id="gendry",
                        to_character_id="arya",
                        replay_key=ReplayKey(tick="chapter_01", timeline_index=1),
                        trust_value=0.5,
                        trust_delta=0.1,
                        sentiment_shift="protective",
                        reason="traveling together",
                    )
                ]
            }
        )
        sansa = make_snapshot(
            character_id="sansa",
            name="Sansa",
            location="courtyard",
            confidence=0.0,
            tension="",
            goal_text=None,
        )

        wake_reasons = manager.identify_woken_agents(
            [arya, gendry, sansa],
            participants=["arya"],
            location="courtyard",
            salience=0.75,
        )

        self.assertEqual(wake_reasons["arya"], "event_participant")
        self.assertEqual(wake_reasons["sansa"], "same_location")
        self.assertEqual(wake_reasons["gendry"], "social_graph")

    def test_world_manager_builds_and_interleaves_location_threads(self) -> None:
        manager = WorldManager()
        seeds = [
            SimulationSeed(
                seed_id="courtyard_1",
                seed_type="world",
                participants=["arya"],
                location="courtyard",
                description="Courtyard event one",
                salience=0.9,
            ),
            SimulationSeed(
                seed_id="courtyard_2",
                seed_type="world",
                participants=["sansa"],
                location="courtyard",
                description="Courtyard event two",
                salience=0.5,
            ),
            SimulationSeed(
                seed_id="hall_1",
                seed_type="world",
                participants=["gendry"],
                location="hall",
                description="Hall event one",
                salience=0.8,
            ),
            SimulationSeed(
                seed_id="bridge_1",
                seed_type="world",
                participants=["arya", "gendry"],
                location="",
                description="Bridge event",
                salience=0.6,
            ),
        ]

        threads = manager.build_location_threads(seeds)
        interleaved = manager.interleave_location_threads(threads)

        self.assertEqual([thread.thread_id for thread in threads], ["courtyard", "hall", "__bridge__"])
        self.assertEqual(
            [seed.seed_id for seed in interleaved],
            ["courtyard_1", "hall_1", "bridge_1", "courtyard_2"],
        )

    def test_world_manager_plans_delayed_bridge_events_for_remote_social_contacts(self) -> None:
        manager = WorldManager(foreground_threshold=0.4)
        arya = make_snapshot(
            character_id="arya",
            name="Arya",
            location="courtyard",
            confidence=0.8,
            tension="Do not get caught",
            goal_text="escape the castle",
        )
        gendry = make_snapshot(
            character_id="gendry",
            name="Gendry",
            location="smithy",
            confidence=0.0,
            tension="",
            goal_text=None,
        ).model_copy(
            update={
                "relationships": [
                    RelationshipLogEntry(
                        from_character_id="gendry",
                        to_character_id="arya",
                        replay_key=ReplayKey(tick="chapter_01", timeline_index=1),
                        trust_value=0.5,
                        trust_delta=0.1,
                        sentiment_shift="protective",
                        reason="traveling together",
                    )
                ]
            }
        )

        bridge_events = manager.plan_bridge_events(
            [arya, gendry],
            source_event_id="evt_100_001",
            participants=["arya"],
            source_location="courtyard",
            salience=0.75,
            outcome_summary="Arya makes a dangerous move in the courtyard.",
            replay_timeline_index=100,
        )

        self.assertEqual(len(bridge_events), 1)
        self.assertEqual(bridge_events[0].event_id, "evt_100_001_bridge_gendry")
        self.assertEqual(bridge_events[0].trigger_timeline_index, 130)
        self.assertEqual(bridge_events[0].location, "smithy")
        self.assertEqual(bridge_events[0].affected_agents, ["gendry"])
        self.assertIn("Rumor reaches Gendry", bridge_events[0].description)

    def test_world_manager_localizes_bridge_event_text_for_chinese_sessions(self) -> None:
        manager = WorldManager(foreground_threshold=0.4)
        mingfei = make_snapshot(
            character_id="Lu Mingfei",
            name="路明非",
            location="卧室",
            confidence=0.8,
            tension="别被看见",
            goal_text="离开房间",
        )
        nuonuo = make_snapshot(
            character_id="Chen Motong",
            name="陈墨瞳",
            location="学院",
            confidence=0.0,
            tension="",
            goal_text=None,
        ).model_copy(
            update={
                "relationships": [
                    RelationshipLogEntry(
                        from_character_id="Chen Motong",
                        to_character_id="Lu Mingfei",
                        replay_key=ReplayKey(tick="chapter_01", timeline_index=1),
                        trust_value=0.5,
                        trust_delta=0.1,
                        sentiment_shift="关注",
                        reason="保持联系",
                    )
                ]
            }
        )

        bridge_events = manager.plan_bridge_events(
            [mingfei, nuonuo],
            source_event_id="evt_100_001",
            participants=["Lu Mingfei"],
            source_location="卧室",
            salience=0.75,
            outcome_summary="路明非突然离开了房间。",
            replay_timeline_index=100,
            language_guidance="- Primary language: 中文 (简体)",
        )

        self.assertEqual(len(bridge_events), 1)
        self.assertIn("风声传到陈墨瞳耳中", bridge_events[0].description)

    def test_salience_ranking_orders_more_urgent_seed_first(self) -> None:
        low = SimulationSeed(
            seed_id="a",
            seed_type="solo",
            participants=["a"],
            location="room",
            description="low",
            urgency=0.2,
            conflict=0.2,
            emotional_charge=0.2,
            novelty=0.2,
        )
        high = SimulationSeed(
            seed_id="b",
            seed_type="spatial_collision",
            participants=["a", "b"],
            location="hall",
            description="high",
            urgency=0.9,
            conflict=0.8,
            emotional_charge=0.9,
            world_importance=0.6,
            novelty=0.6,
        )

        ranked = rank_seeds([low, high], narrative_tension=0.7)

        self.assertEqual(ranked[0].seed_id, "b")
        self.assertGreater(ranked[0].salience, ranked[1].salience)
        self.assertGreater(compute_salience(high, narrative_tension=0.7), 0.7)

    def test_world_manager_uses_salience_and_arc_tension_for_tick_size(self) -> None:
        manager = WorldManager()
        arc = NarrativeArcState(
            current_phase="rising_action",
            tension_level=0.2,
            unresolved_threads=[],
            approaching_climax=False,
        )
        quiet_seed = SimulationSeed(
            seed_id="quiet",
            seed_type="solo",
            participants=["a"],
            location="room",
            description="quiet",
            salience=0.1,
        )
        loud_seed = SimulationSeed(
            seed_id="loud",
            seed_type="collision",
            participants=["a", "b"],
            location="hall",
            description="loud",
            salience=0.85,
        )

        quiet_tick = manager.compute_tick_size([quiet_seed], arc)
        loud_tick = manager.compute_tick_size([loud_seed], arc)

        self.assertEqual(quiet_tick, 2280)
        self.assertEqual(loud_tick, 4)

    def test_world_manager_applies_tick_recovery_band_after_spotlight(self) -> None:
        manager = WorldManager(tick_recovery_ticks=2)
        arc = NarrativeArcState(
            current_phase="climax",
            tension_level=1.0,
            unresolved_threads=["escape"],
            approaching_climax=True,
        )

        raw_tick = manager.compute_tick_size([], arc, cooldown_ticks_remaining=0)
        recovery_tick = manager.compute_tick_size([], arc, cooldown_ticks_remaining=2)

        self.assertEqual(raw_tick, 6)
        self.assertEqual(recovery_tick, 60)
        self.assertEqual(
            manager.next_tick_cooldown(current_cooldown_ticks=0, observed_max_salience=0.85),
            2,
        )
        self.assertEqual(
            manager.next_tick_cooldown(current_cooldown_ticks=2, observed_max_salience=0.1),
            1,
        )

    def test_world_manager_uses_prior_salience_as_tick_carryover(self) -> None:
        manager = WorldManager()
        arc = NarrativeArcState(
            current_phase="setup",
            tension_level=0.3,
            unresolved_threads=[],
            approaching_climax=False,
        )

        without_carryover = manager.compute_tick_size([], arc, prior_max_salience=0.0)
        with_carryover = manager.compute_tick_size([], arc, prior_max_salience=0.58)

        self.assertEqual(without_carryover, 1110)
        self.assertLess(with_carryover, without_carryover)
        self.assertEqual(with_carryover, 185)


if __name__ == "__main__":
    unittest.main()
