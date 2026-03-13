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
    trust: Optional[float] = None
    sentiment: Optional[str] = None
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


class WritingStyleRecord(BaseModel):
    prose_description: str = ""
    sentence_rhythm: str = ""
    description_density: str = ""
    dialogue_narration_balance: str = ""
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
    unspeakable_constraints: List[str] = Field(default_factory=list)
    literary_tradition: str = ""
    autobiographical_elements: str = ""


class MetaLayerRecord(BaseModel):
    authorial: AuthorialLayerRecord = Field(default_factory=AuthorialLayerRecord)
    writing_style: WritingStyleRecord = Field(default_factory=WritingStyleRecord)
    language_context: LanguageContextRecord = Field(default_factory=LanguageContextRecord)
    character_voices: List[CharacterVoiceRecord] = Field(default_factory=list)
    real_world_context: RealWorldContextRecord = Field(default_factory=RealWorldContextRecord)


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


class AccumulatedExtraction(BaseModel):
    characters: List[CharacterExtractionRecord] = Field(default_factory=list)
    world: WorldExtractionRecord = Field(default_factory=WorldExtractionRecord)
    events: List[EventExtractionRecord] = Field(default_factory=list)
    entities: List[EntityRecord] = Field(default_factory=list)
    meta: MetaLayerRecord = Field(default_factory=MetaLayerRecord)
