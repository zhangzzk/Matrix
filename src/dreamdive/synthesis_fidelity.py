"""
Synthesis Fidelity System

Ensures generated chapters strictly follow simulation results while matching original style.

TWO CRITICAL REQUIREMENTS:
1. SIMULATION FIDELITY: Prose must reflect simulated events exactly
   - Don't invent new plot points
   - Don't change outcomes
   - Don't alter character states
   - Synthesize = render events into prose, NOT create new story

2. STYLE TRANSFER: Top-level style must match original material
   - Sentence rhythm, tone, voice
   - Descriptive techniques
   - Narrative perspective
   - BUT: content comes from simulation, NOT from inventing new scenes
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class SimulationFact(BaseModel):
    """
    A canonical fact from simulation that MUST appear in prose.
    Synthesis is NOT allowed to contradict or omit these.
    """
    fact_type: str = Field(
        description="state_change | dialogue | action | location_change | relationship_change | knowledge_gain"
    )
    character_ids: List[str] = Field(default_factory=list)
    fact_statement: str = Field(
        description="Canonical fact that must be preserved"
    )
    source_event_id: str = Field(
        description="Which simulation event produced this fact"
    )
    is_mandatory: bool = Field(
        default=True,
        description="Must this appear on-page or can it be implied?"
    )
    salience: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Importance for on-page rendering"
    )


class GroundedEventSummary(BaseModel):
    """
    Event summary WITH mandatory facts extracted.
    This prevents synthesis from drifting away from simulation.
    """
    event_id: str
    tick: str
    seed_type: str
    location: str
    participants: List[str]

    # Simulation-grounded content
    description: str = Field(description="What happened (from simulation)")
    outcome_summary: str = Field(description="Result (from simulation)")

    # Extracted mandatory facts
    mandatory_facts: List[SimulationFact] = Field(
        default_factory=list,
        description="Facts that MUST appear in prose"
    )

    # State changes that must be preserved
    state_changes: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Character state changes from this event"
    )

    # Dialogue that occurred
    canonical_dialogue: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Actual dialogue from simulation (speaker, line)"
    )

    # High-level guidance
    salience: float = Field(ge=0.0, le=1.0)
    resolution_mode: str = ""


class SynthesisConstraints(BaseModel):
    """
    Hard constraints that synthesis MUST obey.
    """
    # Content constraints
    must_include_events: List[str] = Field(
        default_factory=list,
        description="Event IDs that must appear on-page"
    )

    forbidden_inventions: List[str] = Field(
        default_factory=list,
        description="What synthesis is NOT allowed to create"
    )

    mandatory_outcomes: List[str] = Field(
        default_factory=list,
        description="Outcomes that must be preserved exactly"
    )

    # Fidelity rules
    allow_scene_expansion: bool = Field(
        default=True,
        description="Can add sensory details not in simulation?"
    )

    allow_internal_monologue_invention: bool = Field(
        default=True,
        description="Can invent character thoughts (as long as consistent with state)?"
    )

    allow_dialogue_paraphrasing: bool = Field(
        default=False,
        description="Can rephrase dialogue or must use exact wording?"
    )

    allow_transitional_scenes: bool = Field(
        default=True,
        description="Can add brief transitions between simulated events?"
    )


class StyleTemplate(BaseModel):
    """
    Style patterns extracted from original material.
    These guide HOW to write, while simulation dictates WHAT to write.
    """
    # Sentence-level patterns
    sentence_rhythm_examples: List[str] = Field(
        default_factory=list,
        description="Example sentences showing rhythm/cadence"
    )

    description_technique_examples: List[str] = Field(
        default_factory=list,
        description="How original author describes scenes/actions"
    )

    dialogue_formatting_examples: List[str] = Field(
        default_factory=list,
        description="How dialogue is presented in original"
    )

    # Paragraph-level patterns
    scene_opening_examples: List[str] = Field(
        default_factory=list,
        description="How original opens scenes"
    )

    action_sequence_examples: List[str] = Field(
        default_factory=list,
        description="How original renders action"
    )

    emotional_moment_examples: List[str] = Field(
        default_factory=list,
        description="How original handles emotional beats"
    )

    # Voice characteristics
    narrative_voice_description: str = ""
    pov_style: str = ""
    tense: str = ""


def extract_mandatory_facts_from_event(
    event: Dict[str, Any],
    beat_details: Optional[List[Dict[str, Any]]] = None,
) -> List[SimulationFact]:
    """
    Extract facts from simulation event that MUST appear in synthesis.

    Args:
        event: EventLogRecord dict with description, outcome_summary, etc.
        beat_details: Optional detailed beat information from scene resolution

    Returns:
        List of mandatory facts
    """
    facts: List[SimulationFact] = []
    event_id = event.get("event_id", "")
    participants = event.get("participants", [])

    # Fact 1: The event itself happened
    facts.append(
        SimulationFact(
            fact_type="action",
            character_ids=participants,
            fact_statement=event.get("description", ""),
            source_event_id=event_id,
            is_mandatory=True,
            salience=event.get("salience", 0.5),
        )
    )

    # Fact 2: The outcome occurred
    if event.get("outcome_summary"):
        facts.append(
            SimulationFact(
                fact_type="action",
                character_ids=participants,
                fact_statement=event.get("outcome_summary", ""),
                source_event_id=event_id,
                is_mandatory=True,
                salience=event.get("salience", 0.5),
            )
        )

    # Extract facts from beat details if available
    if beat_details:
        for beat in beat_details:
            # Dialogue
            if beat.get("dialogue"):
                speaker = beat.get("character_id", "")
                facts.append(
                    SimulationFact(
                        fact_type="dialogue",
                        character_ids=[speaker],
                        fact_statement=f"{speaker} said: \"{beat['dialogue']}\"",
                        source_event_id=event_id,
                        is_mandatory=True,
                        salience=0.8,  # Dialogue is usually important
                    )
                )

            # Physical actions
            if beat.get("physical_action"):
                actor = beat.get("character_id", "")
                facts.append(
                    SimulationFact(
                        fact_type="action",
                        character_ids=[actor],
                        fact_statement=f"{actor} {beat['physical_action']}",
                        source_event_id=event_id,
                        is_mandatory=True,
                        salience=0.7,
                    )
                )

            # State changes
            if beat.get("state_change"):
                facts.append(
                    SimulationFact(
                        fact_type="state_change",
                        character_ids=[beat.get("character_id", "")],
                        fact_statement=beat["state_change"],
                        source_event_id=event_id,
                        is_mandatory=True,
                        salience=0.9,  # State changes are critical
                    )
                )

    return facts


def build_grounded_event_summary(
    event: Dict[str, Any],
    beat_details: Optional[List[Dict[str, Any]]] = None,
    state_change_log: Optional[List[Dict[str, Any]]] = None,
    relationship_changes: Optional[List[Dict[str, Any]]] = None,
) -> GroundedEventSummary:
    """
    Build event summary with explicit grounding to simulation.

    This is what gets passed to synthesis - it makes simulation facts explicit
    so LLM can't ignore or contradict them.
    """
    mandatory_facts = extract_mandatory_facts_from_event(event, beat_details)

    # Extract dialogue
    canonical_dialogue = []
    if beat_details:
        for beat in beat_details:
            if beat.get("dialogue"):
                canonical_dialogue.append({
                    "speaker": beat.get("character_id", ""),
                    "line": beat["dialogue"],
                })

    # Extract state changes
    state_changes = state_change_log or []

    return GroundedEventSummary(
        event_id=event.get("event_id", ""),
        tick=event.get("tick", ""),
        seed_type=event.get("seed_type", ""),
        location=event.get("location", ""),
        participants=event.get("participants", []),
        description=event.get("description", ""),
        outcome_summary=event.get("outcome_summary", ""),
        mandatory_facts=mandatory_facts,
        state_changes=state_changes,
        canonical_dialogue=canonical_dialogue,
        salience=event.get("salience", 0.5),
        resolution_mode=event.get("resolution_mode", ""),
    )


def format_grounded_events_for_synthesis(
    grounded_events: List[GroundedEventSummary],
    constraints: SynthesisConstraints,
) -> str:
    """
    Format grounded events with explicit fidelity requirements.

    Returns markdown that makes simulation facts crystal clear.
    """
    lines = ["# SIMULATION EVENTS (CANONICAL - MUST FOLLOW EXACTLY)", ""]

    lines.append("## ⚠️ CRITICAL FIDELITY RULES")
    lines.append("")
    lines.append("Your job is to **RENDER** these simulated events into prose, NOT to **INVENT** new story.")
    lines.append("")
    lines.append("**ALLOWED**:")
    if constraints.allow_scene_expansion:
        lines.append("- ✅ Add sensory details (sights, sounds, smells) to make scenes vivid")
    if constraints.allow_internal_monologue_invention:
        lines.append("- ✅ Invent internal monologue (as long as consistent with character state)")
    if constraints.allow_transitional_scenes:
        lines.append("- ✅ Add brief transitions between events")
    lines.append("- ✅ Use literary techniques to make prose engaging")
    lines.append("")

    lines.append("**FORBIDDEN**:")
    lines.append("- ❌ Change outcomes of events")
    lines.append("- ❌ Invent new plot points not in simulation")
    lines.append("- ❌ Alter character locations or states")
    lines.append("- ❌ Add dialogue not from simulation")
    if not constraints.allow_dialogue_paraphrasing:
        lines.append("- ❌ Rephrase dialogue - use exact wording")
    lines.append("- ❌ Skip high-salience events")
    lines.append("")

    lines.append("---")
    lines.append("")

    # List each event with mandatory facts
    for i, event in enumerate(grounded_events, 1):
        lines.append(f"## Event {i}: {event.event_id}")
        lines.append(f"**Location**: {event.location}")
        lines.append(f"**Participants**: {', '.join(event.participants)}")
        lines.append(f"**Salience**: {event.salience:.2f}")
        lines.append("")

        lines.append(f"**What happened (from simulation)**:")
        lines.append(f"{event.description}")
        lines.append("")

        if event.outcome_summary:
            lines.append(f"**Outcome (from simulation)**:")
            lines.append(f"{event.outcome_summary}")
            lines.append("")

        # Mandatory facts
        if event.mandatory_facts:
            lines.append(f"**Mandatory facts (MUST appear in prose)**:")
            for j, fact in enumerate(event.mandatory_facts, 1):
                marker = "🔴" if fact.salience >= 0.8 else "🟡"
                lines.append(f"{j}. {marker} [{fact.fact_type}] {fact.fact_statement}")
            lines.append("")

        # Canonical dialogue
        if event.canonical_dialogue:
            lines.append(f"**Dialogue (use exact wording)**:")
            for dlg in event.canonical_dialogue:
                lines.append(f"- **{dlg['speaker']}**: \"{dlg['line']}\"")
            lines.append("")

        # State changes
        if event.state_changes:
            lines.append(f"**State changes (must be reflected)**:")
            for change in event.state_changes:
                char = change.get("character_id", "")
                dim = change.get("dimension", "")
                to_val = change.get("to_value", "")
                lines.append(f"- {char}: {dim} → {to_val}")
            lines.append("")

        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def extract_style_template_from_meta(
    meta_layer: Dict[str, Any],
    sample_passages: Optional[List[Dict[str, str]]] = None,
) -> StyleTemplate:
    """
    Extract style patterns from meta-layer and sample passages.

    These guide HOW to write (style) while simulation dictates WHAT (content).
    """
    writing_style = meta_layer.get("writing_style", {})

    # Collect example passages
    sentence_examples = []
    description_examples = []
    dialogue_examples = []

    if sample_passages:
        for passage in sample_passages:
            text = passage.get("text", "")
            why = passage.get("why_representative", "")

            # Categorize based on why
            if "sentence" in why.lower() or "rhythm" in why.lower():
                sentence_examples.append(text)
            elif "description" in why.lower() or "sensory" in why.lower():
                description_examples.append(text)
            elif "dialogue" in why.lower():
                dialogue_examples.append(text)
            else:
                sentence_examples.append(text)  # Default

    # Get more examples from meta
    sample_passages_from_meta = writing_style.get("sample_passages", [])
    for sample in sample_passages_from_meta:
        text = sample.get("text", "")
        if text:
            sentence_examples.append(text)

    return StyleTemplate(
        sentence_rhythm_examples=sentence_examples[:5],
        description_technique_examples=description_examples[:5],
        dialogue_formatting_examples=dialogue_examples[:3],
        narrative_voice_description=writing_style.get("prose_description", ""),
        pov_style=meta_layer.get("authorial", {}).get("narrative_perspective", ""),
        tense="past",  # Most novels use past tense
    )


def format_style_template_for_synthesis(template: StyleTemplate) -> str:
    """
    Format style template as synthesis guidance.

    This teaches HOW to write without dictating WHAT to write.
    """
    lines = ["# STYLE TEMPLATE (Match original author's writing style)", ""]

    lines.append("Your job is to write in THIS style while rendering the simulation events above.")
    lines.append("")

    if template.narrative_voice_description:
        lines.append(f"**Narrative voice**: {template.narrative_voice_description}")
        lines.append("")

    if template.pov_style:
        lines.append(f"**POV**: {template.pov_style}")
        lines.append("")

    lines.append(f"**Tense**: {template.tense}")
    lines.append("")

    if template.sentence_rhythm_examples:
        lines.append("## Sentence Rhythm Examples (from original)")
        lines.append("")
        lines.append("Study these to match the author's rhythm and cadence:")
        lines.append("")
        for i, ex in enumerate(template.sentence_rhythm_examples, 1):
            # Truncate if too long
            display = ex[:200] + "..." if len(ex) > 200 else ex
            lines.append(f"{i}. {display}")
            lines.append("")

    if template.description_technique_examples:
        lines.append("## Description Technique Examples (from original)")
        lines.append("")
        lines.append("Notice how the author renders sensory details and atmosphere:")
        lines.append("")
        for i, ex in enumerate(template.description_technique_examples, 1):
            display = ex[:200] + "..." if len(ex) > 200 else ex
            lines.append(f"{i}. {display}")
            lines.append("")

    if template.dialogue_formatting_examples:
        lines.append("## Dialogue Formatting (from original)")
        lines.append("")
        for i, ex in enumerate(template.dialogue_formatting_examples, 1):
            display = ex[:150] + "..." if len(ex) > 150 else ex
            lines.append(f"{i}. {display}")
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("**Your task**: Render the simulation events in THIS writing style.")
    lines.append("- Match the rhythm, tone, and techniques shown above")
    lines.append("- But the CONTENT must come from simulation, not invention")
    lines.append("- Think: 'If the original author had to describe these simulation events, how would they write it?'")

    return "\n".join(lines)
