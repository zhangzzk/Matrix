from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EvidenceValue(BaseModel):
    value: Any = None
    evidence: str = Field(pattern="^(EXPLICIT|INFERRED|CONTEXTUAL)$")


class FactionRecord(BaseModel):
    name: str
    goal: Optional[str] = None
    relationships: Dict[str, str] = Field(default_factory=dict)


class LocationRecord(BaseModel):
    name: str
    description: Optional[str] = None
    narrative_significance: Optional[str] = None


class WorldSkeleton(BaseModel):
    setting: Optional[str] = None
    time_period: Optional[str] = None
    rules_and_constraints: List[str] = Field(default_factory=list)
    factions: List[FactionRecord] = Field(default_factory=list)
    key_locations: List[LocationRecord] = Field(default_factory=list)


class CastMember(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    role: Optional[str] = None
    first_appearance: Optional[str] = None
    tier: int = Field(ge=1, le=3)


class TimelineSkeleton(BaseModel):
    story_start: Optional[str] = None
    pre_story_events: List[str] = Field(default_factory=list)
    known_future_events: List[str] = Field(default_factory=list)


class DomainSystem(BaseModel):
    name: str
    description: Optional[str] = None
    scale: Optional[str] = None


class StructuralScanPayload(BaseModel):
    world: WorldSkeleton
    cast_list: List[CastMember] = Field(default_factory=list)
    timeline_skeleton: TimelineSkeleton
    domain_systems: List[DomainSystem] = Field(default_factory=list)


class CharacterRelationshipState(BaseModel):
    target_id: str
    type: Optional[str] = None
    summary: Optional[str] = None
    shared_history_summary: Optional[str] = None


class CharacterCurrentState(BaseModel):
    emotional_state: Optional[str] = None
    physical_state: Optional[str] = None
    location: Optional[str] = None
    goal_stack: List[str] = Field(default_factory=list)


class CharacterExtractionRecord(BaseModel):
    id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    identity: Dict[str, Any] = Field(default_factory=dict)
    personality: Dict[str, Any] = Field(default_factory=dict)
    current_state: CharacterCurrentState = Field(default_factory=CharacterCurrentState)
    relationships: List[CharacterRelationshipState] = Field(default_factory=list)
    memory_seeds: List[str] = Field(default_factory=list)


class EventExtractionRecord(BaseModel):
    id: str
    time: Optional[str] = None
    location: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    summary: str
    consequences: List[str] = Field(default_factory=list)
    participant_knowledge: Dict[str, Any] = Field(default_factory=dict)


class WorldExtractionRecord(BaseModel):
    setting: Optional[str] = None
    time_period: Optional[str] = None
    locations: List[str] = Field(default_factory=list)
    rules_and_constraints: List[str] = Field(default_factory=list)
    factions: List[str] = Field(default_factory=list)


class ThemeRecord(BaseModel):
    name: str = ""
    description: str = ""
    confidence: str = ""


class SamplePassageRecord(BaseModel):
    text: str = ""
    why_representative: str = ""


class AuthorialLayerRecord(BaseModel):
    central_thesis: Dict[str, str] = Field(default_factory=dict)
    themes: List[ThemeRecord] = Field(default_factory=list)
    dominant_tone: str = ""
    beliefs_about: Dict[str, str] = Field(default_factory=dict)
    symbolic_motifs: List[str] = Field(default_factory=list)
    narrative_perspective: str = ""


class ChapterFormatRecord(BaseModel):
    heading_style: str = ""
    heading_examples: List[str] = Field(default_factory=list)
    opening_pattern: str = ""
    closing_pattern: str = ""
    paragraphing_style: str = ""


class WritingStyleRecord(BaseModel):
    prose_description: str = ""
    sentence_rhythm: str = ""
    description_density: str = ""
    dialogue_narration_balance: str = ""
    chapter_format: ChapterFormatRecord = Field(default_factory=ChapterFormatRecord)
    stylistic_signatures: List[str] = Field(default_factory=list)
    sample_passages: List[SamplePassageRecord] = Field(default_factory=list)


class LanguageContextRecord(BaseModel):
    primary_language: str = ""
    language_variety: str = ""
    language_style: str = ""
    author_style: str = ""
    register_profile: str = ""
    dialogue_style: str = ""
    figurative_patterns: List[str] = Field(default_factory=list)
    multilingual_features: List[str] = Field(default_factory=list)
    translation_notes: List[str] = Field(default_factory=list)


class DialogueSampleRecord(BaseModel):
    text: str = ""
    why_representative: str = ""


class CharacterVoiceRecord(BaseModel):
    character_id: str = ""
    vocabulary_register: str = ""
    speech_patterns: List[str] = Field(default_factory=list)
    rhetorical_tendencies: str = ""
    gravitates_toward: List[str] = Field(default_factory=list)
    what_they_never_say: str = ""
    emotional_register: str = ""
    sample_dialogues: List[DialogueSampleRecord] = Field(default_factory=list)


class RealWorldContextRecord(BaseModel):
    written_when: str = ""
    historical_context: str = ""
    historical_moment: str = ""
    anxieties_encoded: List[str] = Field(default_factory=list)
    what_story_is_secretly_about: str = ""
    biographical_influences: str = ""
    what_author_could_not_conceive: List[str] = Field(default_factory=list)
    unspeakable_constraints: List[str] = Field(default_factory=list)
    literary_tradition: str = ""
    in_dialogue_with: List[str] = Field(default_factory=list)
    autobiographical_elements: str = ""


class ToneAndRegisterRecord(BaseModel):
    dominant_register: str = ""
    emotional_contract: str = ""
    how_author_handles: Dict[str, str] = Field(default_factory=dict)
    what_prose_does_to_reader: str = ""
    tonal_range: str = ""
    sentence_level_markers: List[str] = Field(default_factory=list)
    what_author_refuses_tonally: List[str] = Field(default_factory=list)


class AuthorsTasteRecord(BaseModel):
    recurring_preoccupations: List[str] = Field(default_factory=list)
    finds_interesting: List[str] = Field(default_factory=list)
    finds_uninteresting: List[str] = Field(default_factory=list)
    moral_sensibility_toward_characters: str = ""
    categorical_refusals: List[str] = Field(default_factory=list)
    signature_moves: List[str] = Field(default_factory=list)
    aesthetic_values: str = ""


class CharacterConstructionRecord(BaseModel):
    method: str = ""
    what_makes_character_real: str = ""
    how_change_works: str = ""
    recurring_types: List[str] = Field(default_factory=list)


class WorldBuildingRecord(BaseModel):
    historical_texture: str = ""
    rule_consistency: str = ""
    priorities: List[str] = Field(default_factory=list)
    introduction_method: str = ""


class StoryArchitectureRecord(BaseModel):
    structure_and_pacing: str = ""
    time_management: str = ""
    revelation_strategy: str = ""
    what_makes_scene_good: str = ""
    chapter_architecture: str = ""


class GenreMasterRecord(BaseModel):
    """A reference author whose taste defines the gold standard for a genre."""

    name: str = ""
    why: str = ""


class GenreTasteRecord(BaseModel):
    """Taste benchmark derived from the best practitioners of the material's genre.

    Built by: (1) identifying the genre/style of the input material,
    (2) web-searching for the most acclaimed authors in that genre,
    (3) synthesising their shared qualities into a concise taste guide.
    """

    detected_genres: List[str] = Field(default_factory=list)
    reference_masters: List[GenreMasterRecord] = Field(default_factory=list)
    taste_profile: str = ""


class DesignTendenciesRecord(BaseModel):
    character_construction: CharacterConstructionRecord = Field(
        default_factory=CharacterConstructionRecord
    )
    world_building: WorldBuildingRecord = Field(default_factory=WorldBuildingRecord)
    story_architecture: StoryArchitectureRecord = Field(
        default_factory=StoryArchitectureRecord
    )



class MetaLayerRecord(BaseModel):
    authorial: AuthorialLayerRecord = Field(default_factory=AuthorialLayerRecord)
    writing_style: WritingStyleRecord = Field(default_factory=WritingStyleRecord)
    language_context: LanguageContextRecord = Field(default_factory=LanguageContextRecord)
    character_voices: List[CharacterVoiceRecord] = Field(default_factory=list)
    real_world_context: RealWorldContextRecord = Field(default_factory=RealWorldContextRecord)
    tone_and_register: ToneAndRegisterRecord = Field(default_factory=ToneAndRegisterRecord)
    authors_taste: AuthorsTasteRecord = Field(default_factory=AuthorsTasteRecord)
    design_tendencies: DesignTendenciesRecord = Field(default_factory=DesignTendenciesRecord)
    genre_taste: GenreTasteRecord = Field(default_factory=GenreTasteRecord)


class EntityRepresentationRecord(BaseModel):
    agent_id: str = ""
    belief: str = ""
    emotional_charge: str = ""
    goal_relevance: str = ""
    misunderstanding: str = ""
    confidence: str = ""


class AbsentFigureDetailsRecord(BaseModel):
    reason_absent: str = ""
    most_present_in: List[str] = Field(default_factory=list)
    counterfactual: str = ""


class ConceptDetailsRecord(BaseModel):
    definitions_by_character: Dict[str, str] = Field(default_factory=dict)
    who_weaponizes: List[str] = Field(default_factory=list)
    who_is_bound_by: List[str] = Field(default_factory=list)
    authorial_stance: str = ""


class EntityRecord(BaseModel):
    entity_id: str
    name: str
    type: str
    objective_facts: List[str] = Field(default_factory=list)
    narrative_role: str = ""
    absent_figure_details: AbsentFigureDetailsRecord = Field(default_factory=AbsentFigureDetailsRecord)
    concept_details: ConceptDetailsRecord = Field(default_factory=ConceptDetailsRecord)
    agent_representations: List[EntityRepresentationRecord] = Field(default_factory=list)


class EntityExtractionPayload(BaseModel):
    entities: List[EntityRecord] = Field(default_factory=list)


class WorldTruthRecord(BaseModel):
    id: str = ""
    description: str = ""
    reveal_state: str = "concealed"
    reveal_conditions: List[str] = Field(default_factory=list)
    reveal_cost: str = ""
    knowers: List[str] = Field(default_factory=list)


class CharacterArcRecord(BaseModel):
    character_id: str = ""
    starting_condition: str = ""
    central_tension: str = ""
    designed_transformation: str = ""
    dramatic_question_role: str = ""
    arc_phase: str = "early"
    on_arc: bool = True
    drift_note: str = ""


class MajorConflictRecord(BaseModel):
    id: str = ""
    description: str = ""
    parties: List[str] = Field(default_factory=list)
    current_state: str = "building"


class DramaticBlueprintRecord(BaseModel):
    central_question: str = ""
    thematic_payload: str = ""
    dramatic_clock: str = ""
    current_phase: str = "rising_action"
    world_truths: List[WorldTruthRecord] = Field(default_factory=list)
    character_arcs: List[CharacterArcRecord] = Field(default_factory=list)
    major_conflicts: List[MajorConflictRecord] = Field(default_factory=list)


class ArcExtensionRecord(BaseModel):
    character_id: str = ""
    starting_condition: str = ""
    central_tension: str = ""
    designed_transformation: str = ""
    dramatic_question_role: str = ""
    arc_phase: str = "early"
    on_arc: bool = True
    drift_note: str = ""


class FateExtensionRecord(BaseModel):
    arc_extensions: List[ArcExtensionRecord] = Field(default_factory=list)
    new_hidden_truths: List[WorldTruthRecord] = Field(default_factory=list)
    new_conflicts: List[MajorConflictRecord] = Field(default_factory=list)
    dramatic_clock_extension: str = ""


class FateLayerRecord(BaseModel):
    """Combined fate layer: extracted dramatic blueprint + extension."""
    extracted: DramaticBlueprintRecord = Field(default_factory=DramaticBlueprintRecord)
    extension: FateExtensionRecord = Field(default_factory=FateExtensionRecord)


class AccumulatedExtraction(BaseModel):
    characters: List[CharacterExtractionRecord] = Field(default_factory=list)
    world: WorldExtractionRecord = Field(default_factory=WorldExtractionRecord)
    events: List[EventExtractionRecord] = Field(default_factory=list)
    meta: MetaLayerRecord = Field(default_factory=MetaLayerRecord)
    fate: Optional[FateLayerRecord] = None
