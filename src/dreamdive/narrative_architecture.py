"""
Narrative Architecture System (P0.5 Phase)

A hierarchical creative design layer that plans the story BEFORE simulation begins.

PHILOSOPHY:
- TV series model: Season arcs planned, episodes outlined, scenes emerge
- Design layer provides GRAVITY (fate), not RAILS (scripts)
- Agents create within constraints: loyal to source + creative on top
- Plans guide emergence, don't dictate it

THREE-LEVEL HIERARCHY:
1. MACRO: Overall story arc (season-level)
2. MESO: Chapter/episode plans (episode-level)
3. MICRO: Scene seeds and character trajectories (guidance for emergence)

KEY PRINCIPLE:
- Designed elements create GRAVITY (pull) not DETERMINISM (force)
- Simulation can deviate if character dynamics demand it
- But gravity pulls story back toward designed arc points

INTEGRATION WITH EXISTING LAYERS:
- Ingestion (P1) → Learns source material, extracts meta-layer, fate layer
- Architecture (P0.5) → Designs continuation based on learned patterns
- Initialization (current) → Sets up first snapshot
- Simulation (P2-P4) → Events emerge under gravitational influence
- Synthesis (P5) → Renders results in original style
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# MACRO LEVEL: Season Arc Design
# ============================================================================

class ArcPhase(str, Enum):
    """Narrative phases following dramatic structure"""
    SETUP = "setup"  # Establish world, characters, conflicts
    RISING_ACTION = "rising_action"  # Escalation, complications
    MIDPOINT = "midpoint"  # Major revelation or shift
    COMPLICATIONS = "complications"  # Darkest hour, highest stakes
    CLIMAX = "climax"  # Confrontation, peak tension
    RESOLUTION = "resolution"  # Aftermath, new equilibrium
    EPILOGUE = "epilogue"  # Looking forward


class ArcNode(BaseModel):
    """
    A planned narrative waypoint that creates gravitational pull.

    Think: "By chapter 20, the secret should be revealed" (gravity)
    Not: "In chapter 20, character X says Y" (determinism)
    """
    node_id: str
    phase: ArcPhase
    estimated_chapter_range: str = Field(
        default="",
        description="e.g., 'Ch 15-20' - flexible timing"
    )

    # What should happen (GRAVITY)
    narrative_significance: str = Field(
        default="",
        description="Why this matters to the story"
    )
    desired_outcome: str = Field(
        default="",
        description="What state the world should reach (not how)"
    )
    dramatic_function: str = Field(
        default="",
        description="Role in overall arc (e.g., 'revelation', 'turning point')"
    )

    # Gravitational strength
    gravity_strength: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="How strongly this pulls the narrative (1.0 = inevitable, 0.5 = probable, 0.2 = possible)"
    )

    # Conditions for reaching this node
    prerequisites: List[str] = Field(
        default_factory=list,
        description="What must happen before this node"
    )

    # What this enables
    unlocks: List[str] = Field(
        default_factory=list,
        description="What becomes possible after this node"
    )


class StoryArcDesign(BaseModel):
    """
    Overall narrative arc design for the simulation.

    Like a TV season outline: planned beats, but episodes unfold dynamically.
    """
    arc_id: str
    arc_name: str = Field(default="", description="e.g., 'The Dragon Awakening Arc'")

    # Central question
    central_dramatic_question: str = Field(
        default="",
        description="What question drives this arc? (e.g., 'Can Lu Mingfei accept his destiny?')"
    )

    # Thematic core
    thematic_payload: str = Field(
        default="",
        description="What this arc explores thematically"
    )

    # Planned nodes
    narrative_nodes: List[ArcNode] = Field(
        default_factory=list,
        description="Waypoints that create gravitational pull"
    )

    # Constraints from source material
    must_respect: List[str] = Field(
        default_factory=list,
        description="Elements from source that cannot be changed"
    )

    # Creative freedom
    can_invent: List[str] = Field(
        default_factory=list,
        description="What agents are allowed to create"
    )

    # Expected duration
    estimated_chapter_count: int = Field(
        default=30,
        description="Rough length (can flex)"
    )


# ============================================================================
# MESO LEVEL: Chapter Plans
# ============================================================================

class ChapterPurpose(str, Enum):
    """What role does this chapter play?"""
    SETUP = "setup"  # Establish situation
    DEVELOPMENT = "development"  # Advance relationships/goals
    REVELATION = "revelation"  # Reveal information
    CONFRONTATION = "confrontation"  # Direct conflict
    TRANSITION = "transition"  # Bridge between major beats
    REFLECTION = "reflection"  # Character processing events


class ChapterPlan(BaseModel):
    """
    High-level design for a single chapter.

    NOT a script - provides direction while allowing emergence.
    """
    chapter_number: int
    purpose: ChapterPurpose

    # Narrative function
    advances_toward: List[str] = Field(
        default_factory=list,
        description="Which arc nodes this chapter pulls toward"
    )

    # Character focus
    primary_pov_characters: List[str] = Field(
        default_factory=list,
        description="Whose perspectives dominate"
    )

    key_character_moments: Dict[str, str] = Field(
        default_factory=dict,
        description="Character ID → intended development (e.g., 'Lu Mingfei confronts fear')"
    )

    # Thematic emphasis
    thematic_threads: List[str] = Field(
        default_factory=list,
        description="Which themes to emphasize"
    )

    # Mood and tone
    target_emotional_arc: str = Field(
        default="",
        description="Emotional journey (e.g., 'hope → despair → determination')"
    )

    # Flexibility
    allow_deviation: bool = Field(
        default=True,
        description="Can simulation diverge from plan if character dynamics demand it?"
    )

    deviation_threshold: float = Field(
        default=0.3,
        ge=0.0,
        le=1.0,
        description="How much deviation allowed (1.0 = complete freedom)"
    )


# ============================================================================
# MICRO LEVEL: Character Development Trajectories
# ============================================================================

class DevelopmentMilestone(BaseModel):
    """
    A point in character's growth journey.

    Creates gravity without forcing exact path.
    """
    milestone_id: str
    description: str = Field(
        default="",
        description="What development occurs (e.g., 'Accepts leadership role')"
    )

    estimated_timing: str = Field(
        default="",
        description="Rough when (e.g., 'Mid-arc', 'After revelation')"
    )

    # What triggers this
    trigger_conditions: List[str] = Field(
        default_factory=list,
        description="What experiences might catalyze this"
    )

    # What changes
    internal_change: str = Field(
        default="",
        description="How character's inner world shifts"
    )

    external_change: str = Field(
        default="",
        description="How character's behavior changes"
    )

    # Evidence
    manifests_as: List[str] = Field(
        default_factory=list,
        description="How we'll see this change (actions, choices, dialogue)"
    )


class CharacterArcPlan(BaseModel):
    """
    Development trajectory for a character across the arc.

    NOT a rigid path - waypoints that create pull.
    """
    character_id: str

    # Starting point
    arc_starting_state: str = Field(
        default="",
        description="Where character begins psychologically"
    )

    # Destination
    arc_ending_state: str = Field(
        default="",
        description="Where character should arrive (if things go as designed)"
    )

    # Journey
    development_trajectory: str = Field(
        default="",
        description="Overall shape of change (e.g., 'Reluctant hero → Willing sacrifice')"
    )

    # Waypoints
    milestones: List[DevelopmentMilestone] = Field(
        default_factory=list,
        description="Key points in development"
    )

    # Core conflict
    central_internal_conflict: str = Field(
        default="",
        description="What tension drives this arc? (e.g., 'Duty vs. desire')"
    )

    # Relationships
    key_relationship_arcs: Dict[str, str] = Field(
        default_factory=dict,
        description="Other character ID → relationship trajectory"
    )

    # Constraints
    must_preserve_traits: List[str] = Field(
        default_factory=list,
        description="Core traits from source that cannot change"
    )

    can_evolve_traits: List[str] = Field(
        default_factory=list,
        description="Traits that can develop"
    )


# ============================================================================
# WORLD EXPANSION DESIGN
# ============================================================================

class NewCharacterDesign(BaseModel):
    """
    Design for a character to be introduced during simulation.

    Follows source material patterns while being original.
    """
    character_id: str
    name: str

    # Narrative function
    role_in_story: str = Field(
        default="",
        description="Why this character exists (e.g., 'Catalyst for Lu Mingfei's growth')"
    )

    introduction_timing: str = Field(
        default="",
        description="When to introduce (e.g., 'Early in rising action')"
    )

    # Design based on source patterns
    archetype_from_source: str = Field(
        default="",
        description="Similar to which source character type?"
    )

    personality_sketch: str = Field(
        default="",
        description="Key traits (designed to fit source style)"
    )

    background_sketch: str = Field(
        default="",
        description="Backstory outline"
    )

    # Relationships
    designed_relationships: Dict[str, str] = Field(
        default_factory=dict,
        description="Character ID → relationship type (e.g., 'mentor', 'rival')"
    )

    # Arc
    character_arc: Optional[CharacterArcPlan] = None

    # Meta-adherence
    matches_source_patterns: List[str] = Field(
        default_factory=list,
        description="Which source patterns this follows (e.g., 'Mysterious mentor archetype')"
    )


class NewLocationDesign(BaseModel):
    """Design for locations to be introduced"""
    location_id: str
    name: str

    # Narrative function
    role_in_story: str = ""
    introduction_timing: str = ""

    # Design
    description_sketch: str = ""
    atmospheric_qualities: List[str] = Field(default_factory=list)

    # Events
    significant_events_here: List[str] = Field(
        default_factory=list,
        description="What major events occur at this location"
    )

    # Meta-adherence
    matches_source_aesthetic: str = Field(
        default="",
        description="How this fits source's world-building style"
    )


class NewPlotThreadDesign(BaseModel):
    """Design for plot threads to be introduced."""

    model_config = ConfigDict(extra="allow")

    thread_id: str = Field(
        default="",
        description="Stable identifier for the new thread"
    )
    role_in_story: str = Field(
        default="",
        description="Narrative function of the thread"
    )
    introduction_timing: str = Field(
        default="",
        description="When to surface this thread"
    )
    summary: str = Field(
        default="",
        description="Concise description of the storyline"
    )
    matches_source_patterns: List[str] = Field(
        default_factory=list,
        description="Which source plot patterns this follows"
    )


class WorldExpansionPlan(BaseModel):
    """
    Plan for introducing new elements during simulation.

    All new elements designed to feel native to source material.
    """
    # New characters
    new_characters: List[NewCharacterDesign] = Field(default_factory=list)

    # New locations
    new_locations: List[NewLocationDesign] = Field(default_factory=list)

    # New plot threads
    new_plot_threads: List[NewPlotThreadDesign] = Field(
        default_factory=list,
        description="New storylines to introduce"
    )

    # Constraints
    must_feel_native: bool = Field(
        default=True,
        description="New elements must feel like they could be from source"
    )

    style_adherence_requirement: float = Field(
        default=0.9,
        ge=0.0,
        le=1.0,
        description="How closely to match source patterns (1.0 = indistinguishable)"
    )


# ============================================================================
# HIDDEN WORLDBUILDING INFERENCE
# ============================================================================

class InferredCharacterAttribute(BaseModel):
    """
    A domain attribute inferred for a character that isn't explicitly
    stated in the source material but is consistent with the world's rules.

    Example: In Dragon Raja, a halfblood character may not have their
    言灵 named in the source — but they should have one.
    """
    character_id: str
    character_name: str = ""
    attribute_key: str = Field(
        default="",
        description="Domain attribute key (e.g., 'word_spirit', 'house', 'patronus')"
    )
    attribute_value: Dict[str, Any] = Field(
        default_factory=dict,
        description="Structured value for this attribute"
    )
    visibility: str = Field(
        default="hidden",
        description="public / private / faction / hidden — defaults to hidden since it's inferred"
    )
    reasoning: str = Field(
        default="",
        description="Why this attribute was inferred (what evidence from source supports it)"
    )
    can_evolve: bool = Field(
        default=False,
        description="Whether this attribute can change during simulation"
    )
    evolution_triggers: List[str] = Field(
        default_factory=list,
        description="What might cause this attribute to change"
    )


class InferredWorldRule(BaseModel):
    """
    A world rule that is implied but not explicitly stated in the source.

    Example: 'Halfbloods whose bloodline purity exceeds a threshold lose
    control' — the threshold may not be stated, but the pattern is implied.
    """
    rule_id: str
    description: str = Field(
        default="",
        description="Natural language description of the inferred rule"
    )
    evidence: List[str] = Field(
        default_factory=list,
        description="What from the source material supports this inference"
    )
    confidence: str = Field(
        default="medium",
        description="How confident we are: high / medium / speculative"
    )
    affects_systems: List[str] = Field(
        default_factory=list,
        description="Which domain systems this rule governs"
    )


class InferredBackstory(BaseModel):
    """
    Hidden backstory for a character that the author likely had in mind
    but didn't fully reveal in the source material.
    """
    character_id: str
    character_name: str = ""
    backstory_elements: List[str] = Field(
        default_factory=list,
        description="Inferred backstory details"
    )
    reasoning: str = Field(
        default="",
        description="Why these elements are consistent with source"
    )


class HiddenWorldbuildingPlan(BaseModel):
    """
    Inferred world-building details that exist in the author's mind
    but aren't explicitly stated in the source material.

    This fills in the invisible settings that make the world feel complete:
    - Character abilities/attributes not yet revealed
    - World rules implied but never stated
    - Hidden backstories consistent with character behavior
    - Faction secrets, prophecy details, power hierarchies

    DESIGN PHILOSOPHY:
    - Be CREATIVE but CONSISTENT with source patterns
    - Infer what the author would have designed, not random additions
    - These details create depth even if they never surface in narrative
    - Some may be revealed through simulation; others stay hidden
    """
    # Inferred attributes for existing characters
    character_attributes: List[InferredCharacterAttribute] = Field(
        default_factory=list,
        description="Domain attributes inferred for characters"
    )

    # Inferred world rules
    world_rules: List[InferredWorldRule] = Field(
        default_factory=list,
        description="World rules implied but not explicitly stated"
    )

    # Hidden backstories
    backstories: List[InferredBackstory] = Field(
        default_factory=list,
        description="Inferred character backstories"
    )

    # Design notes for the simulator
    design_notes: str = Field(
        default="",
        description="Overall notes on the inferred world-building approach"
    )


# ============================================================================
# COMPLETE NARRATIVE ARCHITECTURE
# ============================================================================

class NarrativeArchitecture(BaseModel):
    """
    Complete hierarchical design for narrative continuation.

    CREATED: During P0.5 phase (after ingestion, before initialization)
    INFORMED BY:
        - Source material patterns (meta-layer)
        - Source fate layer (existing arcs, conflicts)
        - User configuration (divergence seeds, focus)
    USED BY:
        - P2 collision detection (arc nodes create goal tensions)
        - P2 scene setup (chapter plans guide scene selection)
        - P3 memory consolidation (milestone tracking)
        - P4 narrative arc updates (tracking progress toward nodes)

    PHILOSOPHY:
    - Designed elements exert GRAVITATIONAL PULL
    - Simulation can deviate if character dynamics demand
    - Gravity eventually pulls narrative back toward designed waypoints
    - Balance: Structure (arc design) + Emergence (character simulation)
    """

    # Identity
    architecture_id: str
    created_for_session: str

    # Macro: Season arc
    story_arc: StoryArcDesign

    # Meso: Chapter plans
    chapter_plans: List[ChapterPlan] = Field(
        default_factory=list,
        description="Rough roadmap per chapter (flexible)"
    )

    # Micro: Character trajectories
    character_arcs: List[CharacterArcPlan] = Field(
        default_factory=list,
        description="Development paths for main characters"
    )

    # World expansion
    world_expansion: WorldExpansionPlan = Field(
        default_factory=WorldExpansionPlan
    )

    # Hidden worldbuilding (inferred settings)
    hidden_worldbuilding: HiddenWorldbuildingPlan = Field(
        default_factory=HiddenWorldbuildingPlan,
        description="Inferred world-building details not explicit in source"
    )

    # Meta-adherence tracking
    source_fidelity_requirements: Dict[str, Any] = Field(
        default_factory=dict,
        description="What must be preserved from source"
    )

    creative_freedom_bounds: Dict[str, Any] = Field(
        default_factory=dict,
        description="Where agents can be creative"
    )

    # Gravitational parameters
    default_gravity_strength: float = Field(
        default=0.7,
        description="Base pull of designed elements (0.0-1.0)"
    )

    allow_emergent_override: bool = Field(
        default=True,
        description="Can character dynamics override design?"
    )

    override_threshold: float = Field(
        default=0.8,
        description="How strong must character dynamics be to override design?"
    )


# ============================================================================
# GRAVITY MECHANICS
# ============================================================================

class NarrativeGravity(BaseModel):
    """
    Represents gravitational pull toward designed narrative waypoints.

    Used during simulation to bias event selection without forcing outcomes.
    """
    source_node_id: str = Field(default="", description="Which arc node creates this pull")

    # Strength and direction
    pull_strength: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How strong the pull (affects probability)"
    )

    pull_toward: str = Field(
        default="",
        description="What outcome this biases toward"
    )

    # Scope
    affects_characters: List[str] = Field(
        default_factory=list,
        description="Which characters feel this pull"
    )

    affects_event_types: List[str] = Field(
        default_factory=list,
        description="Which event types this biases (e.g., 'revelation', 'confrontation')"
    )

    # Timing
    active_chapter_range: Optional[str] = None
    decays_over_time: bool = Field(
        default=False,
        description="Does pull weaken if not achieved?"
    )

    # Application
    bias_mechanism: str = Field(
        default="probability_boost",
        description="How to apply (e.g., 'probability_boost', 'salience_multiplier')"
    )
