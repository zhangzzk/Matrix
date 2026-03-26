"""
Domain-Specific Attribute System

This module provides a flexible framework for managing domain-specific information
attached to characters, entities, and worlds. Examples include:

- Dragon Raja (龙族): 言灵 (Word Spirits), bloodline purity, special weapons
- Game of Thrones: Houses, titles, oaths, prophecies
- Cultivation novels: cultivation levels, techniques, spiritual roots
- Sci-fi: tech implants, faction ranks, access clearances

The system supports:
1. Schema definition at ingestion time (P1 phase)
2. Runtime reading by agents (P2/P3 phases)
3. Dynamic modification during simulation (P2/P3 phases)
4. Historical tracking of attribute changes
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class AttributeVisibility(str, Enum):
    """Who knows about this attribute?"""
    PUBLIC = "public"  # Everyone knows
    PRIVATE = "private"  # Only the character knows
    FACTION = "faction"  # Only faction members know
    REVEALED = "revealed"  # Was private, now revealed
    HIDDEN = "hidden"  # Exists but nobody knows yet (GM-only)


class AttributeEvolutionMode(str, Enum):
    """How can this attribute change over time?"""
    STATIC = "static"  # Never changes (e.g., bloodline)
    INCREMENTAL = "incremental"  # Can increase/decrease (e.g., cultivation level)
    TRANSFORMATIVE = "transformative"  # Can fundamentally change (e.g., class change)
    CONDITIONAL = "conditional"  # Changes based on triggers (e.g., curse activation)


class DomainAttributeDefinition(BaseModel):
    """
    Defines a type of domain attribute that can be attached to characters or entities.

    Example for Dragon Raja 言灵:
    {
        "attribute_key": "word_spirit",
        "display_name": "言灵",
        "description": "Supernatural ability manifested through dragon bloodline",
        "value_type": "structured",
        "evolution_mode": "transformative",
        "possible_values": ["Jun Yan", "Time Zero", "Yanling·Rhine", ...],
        "constraints": "Each character has at most one primary word spirit",
        "visibility_default": "public"
    }
    """
    attribute_key: str = Field(
        description="Unique identifier for this attribute type (e.g., 'word_spirit', 'house_allegiance')"
    )
    display_name: str = Field(
        description="Human-readable name, can be in any language"
    )
    description: str = Field(
        description="What this attribute represents in the story world"
    )
    value_type: str = Field(
        default="string",
        description="Type of value: string, number, boolean, enum, structured"
    )
    evolution_mode: AttributeEvolutionMode = Field(
        default=AttributeEvolutionMode.STATIC
    )
    possible_values: List[str] = Field(
        default_factory=list,
        description="For enum types, list of valid values"
    )
    constraints: str = Field(
        default="",
        description="Narrative or mechanical constraints on this attribute"
    )
    visibility_default: AttributeVisibility = Field(
        default=AttributeVisibility.PUBLIC
    )
    affects_abilities: List[str] = Field(
        default_factory=list,
        description="What capabilities this attribute grants (for agent reasoning)"
    )
    narrative_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="How important this attribute is to the story (0=flavor, 1=critical)"
    )


class DomainAttributeValue(BaseModel):
    """
    A specific instance of a domain attribute attached to a character/entity.

    Example:
    {
        "attribute_key": "word_spirit",
        "value": {
            "name": "Jun Yan (君焰)",
            "serial_number": "89",
            "description": "Controls fire and combustion",
            "power_level": "high",
            "awakening_conditions": "bloodline activation at age 18"
        },
        "visibility": "public",
        "acquired_tick": "ch01_001",
        "acquisition_narrative": "Awakened during the dragon attack on the school",
        "can_evolve": true,
        "evolution_triggers": ["bloodline purification", "emotional breakthrough"]
    }
    """
    attribute_key: str = Field(
        description="Links back to DomainAttributeDefinition"
    )
    value: Union[str, int, float, bool, Dict[str, Any]] = Field(
        description="The actual value - can be simple or structured"
    )
    visibility: AttributeVisibility = Field(
        default=AttributeVisibility.PUBLIC
    )
    acquired_tick: Optional[str] = Field(
        default=None,
        description="When this attribute was acquired (None = had from story start)"
    )
    acquisition_narrative: str = Field(
        default="",
        description="How the character acquired this attribute"
    )
    can_evolve: bool = Field(
        default=False,
        description="Can this specific instance change during simulation?"
    )
    evolution_triggers: List[str] = Field(
        default_factory=list,
        description="Conditions that might cause this to evolve"
    )
    currently_active: bool = Field(
        default=True,
        description="Is this attribute currently in effect? (for conditional attributes)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional domain-specific data"
    )


class DomainAttributeChange(BaseModel):
    """
    Records a change to a domain attribute during simulation.
    This gets logged to enable historical tracking and replay.
    """
    character_id: str
    attribute_key: str
    tick: str
    timeline_index: int
    event_sequence: int
    change_type: str = Field(
        description="acquired | lost | evolved | activated | deactivated | modified"
    )
    old_value: Optional[Union[str, int, float, bool, Dict[str, Any]]] = None
    new_value: Union[str, int, float, bool, Dict[str, Any]]
    trigger_event_id: Optional[str] = None
    narrative_reason: str = Field(
        description="Why this change happened in story terms"
    )
    visibility_changed: bool = Field(
        default=False,
        description="Did the visibility of this attribute change?"
    )
    old_visibility: Optional[AttributeVisibility] = None
    new_visibility: Optional[AttributeVisibility] = None


class WorldDomainSystem(BaseModel):
    """
    Defines a domain-specific system that operates at the world level.

    Example for Dragon Raja bloodline system:
    {
        "system_key": "dragon_bloodline",
        "display_name": "龙族血统系统",
        "description": "Genetic inheritance from dragon species determines abilities",
        "rules": [
            "Higher bloodline purity grants stronger 言灵",
            "Bloodline can be refined through special rituals",
            "Deadpool transformation occurs when bloodline exceeds threshold"
        ],
        "affects_characters": true,
        "power_scale": {
            "S": "Pure dragon blood",
            "A": "Hybrid with dominant dragon genes",
            "B": "Normal hybrid",
            "C": "Weak dragon heritage",
            "D": "Barely detectable"
        }
    }
    """
    system_key: str = Field(
        description="Unique identifier (e.g., 'dragon_bloodline', 'magic_system')"
    )
    display_name: str
    description: str
    rules: List[str] = Field(
        default_factory=list,
        description="How this system works in-world"
    )
    affects_characters: bool = Field(
        default=True,
        description="Does this system attach attributes to characters?"
    )
    power_scale: Dict[str, str] = Field(
        default_factory=dict,
        description="Ranking or level system if applicable"
    )
    interactions: Dict[str, str] = Field(
        default_factory=dict,
        description="How this system interacts with other systems"
    )
    discovery_state: str = Field(
        default="known",
        description="known | partially_known | hidden - how much characters understand this system"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict
    )


class EntityDomainAttributes(BaseModel):
    """
    Domain attributes for non-character entities (items, locations, concepts, etc.)

    Example - Cassell Academy:
    {
        "entity_id": "cassell_academy",
        "entity_type": "location",
        "attributes": {
            "security_level": {
                "attribute_key": "facility_security",
                "value": "AAA",
                "metadata": {"clearance_required": "principal_authorization"}
            },
            "alchemy_equipment": {
                "attribute_key": "research_facility",
                "value": ["dragon_bone_analyzer", "bloodline_sequencer"],
                "visibility": "faction"
            }
        }
    }
    """
    entity_id: str
    entity_type: str = Field(
        description="item | location | faction | concept | artifact"
    )
    entity_name: str
    attributes: Dict[str, DomainAttributeValue] = Field(
        default_factory=dict,
        description="Map of attribute_key to values"
    )


class DomainSystemRegistry(BaseModel):
    """
    Complete registry of all domain systems for a story.
    This gets created during P1 ingestion and stored in the extraction manifest.
    """
    story_id: str
    attribute_definitions: List[DomainAttributeDefinition] = Field(
        default_factory=list,
        description="All attribute types that can be attached to characters/entities"
    )
    world_systems: List[WorldDomainSystem] = Field(
        default_factory=list,
        description="World-level domain systems"
    )
    entity_attributes: List[EntityDomainAttributes] = Field(
        default_factory=list,
        description="Attributes attached to entities (not characters)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Story-specific configuration"
    )
