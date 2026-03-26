# Domain Attribute System - Complete Guide

## Overview

The Domain Attribute System provides a robust, flexible framework for managing story-specific information that goes beyond standard character traits. This is essential for simulating complex fictional worlds with unique power systems, social structures, or mechanical rules.

## Why Domain Attributes?

Standard character models have fields like `name`, `background`, `personality`, etc. But many stories have domain-specific concepts that don't fit these generic categories:

### Examples by Genre

**Dragon Raja (龙族)**
- 言灵 (Word Spirits): Supernatural abilities with specific names, power levels, and activation conditions
- 血统纯度 (Bloodline Purity): Numerical value that determines abilities and risks
- 专用武器 (Specialized Weapons): Character-specific arms with unique properties
- 学院等级 (Academy Rank): S, A, B, C rankings that affect status
- Hidden identities: Surface identity vs. true bloodline

**Game of Thrones**
- House Allegiance: Stark, Lannister, Targaryen, etc.
- Titles: Lord Commander, Hand of the King, Warden of the North
- Secret Parentage: Hidden bloodlines revealed over time
- Oaths and Vows: Night's Watch vows, marriage alliances
- Claims to the Throne: Legitimacy and succession rights

**Cultivation Novels**
- Cultivation Level: Foundation Building, Golden Core, Nascent Soul, etc.
- Spiritual Root: Quality and elemental affinity
- Techniques: Sword arts, body cultivation methods
- Sect Affiliation: Which sect the character belongs to
- Karma and Fate: Accumulated merit/sin that affects destiny

**Sci-Fi Settings**
- Cybernetic Implants: Neural interfaces, combat augmentations
- Faction Rank: Corporate hierarchy, military rank
- Access Clearances: What information/areas they can access
- Tech Specialization: Hacker, pilot, engineer, etc.

## Architecture

The system has three main components:

### 1. Domain System Registry

Defines what domain attributes exist in your story world.

```python
from dreamdive.domain_systems import (
    DomainSystemRegistry,
    DomainAttributeDefinition,
    WorldDomainSystem,
    AttributeEvolutionMode,
    AttributeVisibility,
)

# Create a registry for your story
registry = DomainSystemRegistry(
    story_id="dragon_raja",
    attribute_definitions=[
        DomainAttributeDefinition(
            attribute_key="word_spirit",
            display_name="言灵 (Word Spirit)",
            description="Supernatural ability from dragon bloodline",
            value_type="structured",
            evolution_mode=AttributeEvolutionMode.TRANSFORMATIVE,
            narrative_weight=1.0,
            affects_abilities=["combat", "reality_manipulation"],
            constraints="Each character has at most one primary word spirit",
        ),
    ],
    world_systems=[
        WorldDomainSystem(
            system_key="dragon_bloodline",
            display_name="龙族血统系统",
            description="Genetic inheritance determines abilities",
            rules=[
                "Higher bloodline purity grants stronger 言灵",
                "Exceeding 50% purity risks Deadpool transformation",
            ],
            power_scale={
                "S": "Nearly pure dragon blood",
                "A": "Strong hybrid",
                "B": "Normal hybrid",
            },
        ),
    ],
)
```

### 2. Character Domain Attributes

Actual attribute instances attached to characters.

```python
from dreamdive.domain_systems import DomainAttributeValue

# Character Chu Zihang's attributes
chu_zihang_attributes = {
    "word_spirit": DomainAttributeValue(
        attribute_key="word_spirit",
        value={
            "name": "Jun Yan (君焰)",
            "serial_number": "89",
            "description": "Controls fire and combustion",
            "power_level": "high",
        },
        visibility=AttributeVisibility.PUBLIC,
        acquisition_narrative="Awakened during dragon attack on school",
        can_evolve=True,
        evolution_triggers=["bloodline purification", "emotional breakthrough"],
    ),
    "bloodline_purity": DomainAttributeValue(
        attribute_key="bloodline_purity",
        value=0.43,  # 43% dragon blood
        visibility=AttributeVisibility.FACTION,
        can_evolve=True,
        evolution_triggers=["dragon bone refinement", "blood rage"],
    ),
    "weapon_specialization": DomainAttributeValue(
        attribute_key="weapon_specialization",
        value={
            "name": "Murasame (村雨)",
            "type": "katana",
            "special_property": "Cuts through dragon scales",
        },
        visibility=AttributeVisibility.PUBLIC,
        can_evolve=False,
    ),
}
```

### 3. Runtime Modification

Track changes during simulation.

```python
from dreamdive.domain_attribute_manager import DomainAttributeModifier

# When a character's word spirit evolves during the story
change_record = DomainAttributeModifier.create_change_record(
    character_id="chu_zihang",
    attribute_key="word_spirit",
    tick="ch15_023",
    timeline_index=150,
    event_sequence=3,
    change_type="evolved",
    old_value={"name": "Jun Yan", "power_level": "high"},
    new_value={"name": "Jun Yan - Awakened Form", "power_level": "extreme"},
    event_id="evt_bloodline_awakening",
    narrative_reason="Emotional breakthrough when protecting Lu Mingfei",
)

# This creates a log entry that can be replayed to reconstruct state
```

## Integration with Existing System

### During Ingestion (P1 Phase)

Domain attributes are extracted from the source material and stored in the `AccumulatedExtraction`:

```python
# In your extraction results
{
    "characters": [
        {
            "id": "chu_zihang",
            "name": "Chu Zihang",
            "domain_attributes": {
                "word_spirit": {...},
                "bloodline_purity": {...},
            }
        }
    ],
    "domain_registry": {
        "story_id": "dragon_raja",
        "attribute_definitions": [...],
        "world_systems": [...],
    }
}
```

### During Simulation (P2/P3 Phases)

#### 1. Loading into Agent Context

Use `DomainAttributeFormatter` to include domain attributes in agent prompts:

```python
from dreamdive.domain_attribute_manager import format_domain_attributes_for_prompt

# When building agent context
domain_text = format_domain_attributes_for_prompt(
    character_id=agent_id,
    domain_attributes=character.domain_attributes,
    domain_registry=extraction.domain_registry,
    viewer_id=agent_id,  # Filter by visibility
)

# domain_text will be formatted like:
# ## Domain-Specific Attributes
# - **言灵 (Word Spirit)**: Jun Yan (君焰), Controls fire and combustion
# - **血统纯度 (Bloodline Purity)**: 0.43 [Can evolve: dragon bone refinement, blood rage]
# - **专用武器 (Specialized Weapon)**: Murasame (村雨), katana, Cuts through dragon scales
```

#### 2. Querying Attributes

Use `DomainAttributeQuery` to check attributes during event resolution:

```python
from dreamdive.domain_attribute_manager import (
    check_character_has_attribute,
    find_characters_with_attribute,
)

# Check if character can use a specific ability
if check_character_has_attribute(character, "word_spirit", "Time Zero"):
    # This character has Time Zero word spirit
    # Apply special combat logic
    pass

# Find all characters from a specific house
stark_members = find_characters_with_attribute(
    all_characters, "house_allegiance", "Stark"
)

# Find all characters with high bloodline purity
from dreamdive.domain_attribute_manager import DomainAttributeQuery

high_purity_chars = [
    char for char in all_characters
    if DomainAttributeQuery.get_attribute(char, "bloodline_purity")
    and DomainAttributeQuery.get_attribute(char, "bloodline_purity") > 0.5
]
```

#### 3. Modifying Attributes

Use `DomainAttributeModifier` to update attributes during simulation:

```python
from dreamdive.domain_attribute_manager import DomainAttributeModifier

# Update character's attribute
DomainAttributeModifier.update_character_attribute(
    character=character,
    attribute_key="bloodline_purity",
    new_value=0.48,  # Increased from 0.43
    acquisition_narrative="Refined through dragon bone ritual",
    can_evolve=True,
    evolution_triggers=["blood rage", "deadpool threshold"],
    visibility="faction",
)

# Create change log for replay
change_record = DomainAttributeModifier.create_change_record(
    character_id=character.character_id,
    attribute_key="bloodline_purity",
    tick=current_tick,
    timeline_index=timeline_idx,
    event_sequence=event_seq,
    change_type="modified",
    old_value=0.43,
    new_value=0.48,
    narrative_reason="Refined through dragon bone ritual",
)

# Log the change
repository.append_domain_attribute_change(change_record)
```

## Practical Examples

### Example 1: Dragon Raja - Word Spirit Evolution

```python
# During P1 Ingestion: Extract word spirits from novel
extraction = {
    "domain_registry": {
        "attribute_definitions": [
            {
                "attribute_key": "word_spirit",
                "display_name": "言灵",
                "evolution_mode": "transformative",
                "possible_values": ["Jun Yan", "Time Zero", "Yanling·Rhine"],
            }
        ]
    },
    "characters": [
        {
            "id": "chu_zihang",
            "domain_attributes": {
                "word_spirit": {
                    "value": {"name": "Jun Yan", "serial": "89"},
                    "can_evolve": True,
                    "evolution_triggers": ["bloodline awakening"],
                }
            }
        }
    ]
}

# During P2 Simulation: Evolution event
# Agent detects emotional breakthrough -> trigger evolution
if event_type == "emotional_breakthrough" and character.id == "chu_zihang":
    old_value = DomainAttributeQuery.get_attribute(character, "word_spirit")
    new_value = {
        "name": "Jun Yan - Awakened Form",
        "serial": "89",
        "power_multiplier": 3.0,
    }

    # Update and log
    DomainAttributeModifier.update_character_attribute(
        character, "word_spirit", new_value,
        acquisition_narrative="Awakened protecting Lu Mingfei from dragon"
    )

    change_log = DomainAttributeModifier.create_change_record(
        character_id="chu_zihang",
        attribute_key="word_spirit",
        change_type="evolved",
        old_value=old_value,
        new_value=new_value,
        narrative_reason="Emotional breakthrough unlocked true power",
        **replay_coords,
    )
```

### Example 2: Game of Thrones - Secret Identity Reveal

```python
# During P1: Character has hidden parentage
jon_snow_attrs = {
    "public_identity": DomainAttributeValue(
        attribute_key="identity",
        value="Jon Snow, Bastard of Winterfell",
        visibility=AttributeVisibility.PUBLIC,
    ),
    "secret_parentage": DomainAttributeValue(
        attribute_key="secret_identity",
        value="Aegon Targaryen, rightful heir to Iron Throne",
        visibility=AttributeVisibility.HIDDEN,  # Nobody knows yet
        can_evolve=False,  # Truth doesn't change
    ),
    "house_allegiance": DomainAttributeValue(
        attribute_key="house_allegiance",
        value="Stark",
        visibility=AttributeVisibility.PUBLIC,
        can_evolve=True,  # Might change when truth revealed
    ),
}

# During P2: Revelation event
if event_id == "sam_discovers_truth":
    # Change visibility from HIDDEN to REVEALED
    change_record = DomainAttributeModifier.create_change_record(
        character_id="jon_snow",
        attribute_key="secret_identity",
        change_type="activated",  # Now becomes active knowledge
        new_value="Aegon Targaryen, rightful heir",
        visibility_changed=True,
        old_visibility="hidden",
        new_visibility="revealed",
        narrative_reason="Sam discovers truth in ancient scrolls",
        **replay_coords,
    )

    # This triggers cascade: other characters learn, alliances shift, etc.
```

### Example 3: Cultivation Novel - Level Breakthrough

```python
# Domain system for cultivation
cultivation_registry = DomainSystemRegistry(
    story_id="cultivation_world",
    attribute_definitions=[
        DomainAttributeDefinition(
            attribute_key="cultivation_level",
            display_name="修为境界",
            value_type="enum",
            evolution_mode=AttributeEvolutionMode.INCREMENTAL,
            possible_values=[
                "Qi Condensation",
                "Foundation Building",
                "Golden Core",
                "Nascent Soul",
                "Deity Transformation",
            ],
            narrative_weight=1.0,
        ),
    ],
    world_systems=[
        WorldDomainSystem(
            system_key="cultivation_system",
            rules=[
                "Must condense golden core to break through to Golden Core",
                "Heavenly tribulation tests breakthrough to Nascent Soul",
            ],
        ),
    ],
)

# Character breakthrough during simulation
if cultivation_success:
    old_level = DomainAttributeQuery.get_attribute(character, "cultivation_level")
    new_level = "Golden Core"

    DomainAttributeModifier.update_character_attribute(
        character, "cultivation_level", new_level,
        acquisition_narrative="Broke through during tribulation in Thunder Valley",
        can_evolve=True,
        evolution_triggers=["comprehend dao", "survive tribulation"],
    )
```

## Advanced Features

### Visibility System

Attributes can have different visibility levels:

- `PUBLIC`: Everyone knows (e.g., public title, visible weapon)
- `PRIVATE`: Only the character knows (e.g., hidden ability, secret technique)
- `FACTION`: Only faction members know (e.g., sect secrets, house strategies)
- `REVEALED`: Was private, now revealed (e.g., secret identity exposed)
- `HIDDEN`: GM-only, nobody in-world knows yet (e.g.,未揭示的真相)

```python
# When building agent context, visibility is filtered automatically
domain_text = format_domain_attributes_for_prompt(
    character_id="character_A",
    domain_attributes=character_B.domain_attributes,
    viewer_id="character_A",  # A is viewing B's attributes
)
# Only attributes visible to A will be included
```

### Evolution Triggers

Specify conditions that might cause an attribute to change:

```python
DomainAttributeValue(
    attribute_key="bloodline_purity",
    value=0.43,
    can_evolve=True,
    evolution_triggers=[
        "dragon bone refinement",
        "blood rage",
        "deadpool transformation risk at >50%",
    ],
)
```

Agents can reference these triggers when deciding actions or predicting outcomes.

### Structured vs. Simple Values

Domain attributes can be simple or complex:

```python
# Simple value
DomainAttributeValue(
    attribute_key="cultivation_level",
    value="Golden Core",  # Just a string
)

# Structured value
DomainAttributeValue(
    attribute_key="word_spirit",
    value={
        "name": "Jun Yan",
        "serial_number": "89",
        "element": "fire",
        "danger_level": "high",
        "known_users": ["Chu Zihang"],
    },
)
```

## Database Schema

Domain attributes are stored in:

1. **Character table**: `domain_attributes` JSONB field
2. **Domain attribute change log**: New `domain_attribute_changes` table

```sql
CREATE TABLE domain_attribute_changes (
    id SERIAL PRIMARY KEY,
    character_id TEXT NOT NULL,
    attribute_key TEXT NOT NULL,
    tick TEXT NOT NULL,
    timeline_index INTEGER NOT NULL,
    event_sequence INTEGER NOT NULL,
    change_type TEXT NOT NULL,  -- acquired|lost|evolved|activated|deactivated|modified
    old_value JSONB,
    new_value JSONB NOT NULL,
    event_id TEXT,
    narrative_reason TEXT,
    visibility_changed BOOLEAN DEFAULT FALSE,
    old_visibility TEXT,
    new_visibility TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_domain_attr_changes_char ON domain_attribute_changes(character_id);
CREATE INDEX idx_domain_attr_changes_tick ON domain_attribute_changes(tick, timeline_index, event_sequence);
```

## Best Practices

### 1. Define Domain Systems Early (P1)

Extract and define your domain systems during ingestion:
- What attributes exist?
- What values are possible?
- How do they evolve?
- What do they affect?

### 2. Use Consistent Keys

Use clear, consistent `attribute_key` values:
- ✅ `word_spirit`, `bloodline_purity`, `house_allegiance`
- ❌ `ws`, `blood`, `house` (too cryptic)
- ❌ `Word Spirit`, `word_Spirit` (inconsistent casing)

### 3. Leverage Visibility

Don't give agents information their characters shouldn't have:
```python
# Bad: Show everything
domain_text = format_domain_attributes_for_prompt(
    character_id=villain.id,
    domain_attributes=hero.domain_attributes,
    viewer_id=None,  # No filtering!
)

# Good: Filter by viewer
domain_text = format_domain_attributes_for_prompt(
    character_id=hero.id,
    domain_attributes=hero.domain_attributes,
    viewer_id=villain.id,  # Villain only sees public attributes
)
```

### 4. Log All Changes

Always create change records when attributes evolve:
```python
# Enables replay, debugging, and narrative reconstruction
change_log = DomainAttributeModifier.create_change_record(...)
repository.append_domain_attribute_change(change_log)
```

### 5. Use Narrative Weight

Set appropriate `narrative_weight` to guide agents:
- `1.0`: Critical to story (e.g., secret identity, main power)
- `0.7`: Important but not central (e.g., titles, rank)
- `0.5`: Moderate importance (e.g., preferred weapon)
- `0.3`: Flavor only (e.g., favorite food, minor hobby)

## Migration Path

For existing simulations without domain attributes:

1. **Add empty registries** to `AccumulatedExtraction`:
   ```python
   extraction.domain_registry = DomainSystemRegistry(story_id="legacy")
   ```

2. **Migrate existing data** from `domain_attributes` dict to structured form:
   ```python
   # Old format (generic dict)
   character.domain_attributes = {"word_spirit": "Jun Yan"}

   # New format (structured)
   character.domain_attributes = {
       "word_spirit": DomainAttributeValue(
           attribute_key="word_spirit",
           value="Jun Yan",
       )
   }
   ```

3. **Backward compatibility**: The system accepts both dict and object forms, so existing code continues to work.

## Summary

The Domain Attribute System provides:

✅ **Flexible schema** - Define your own attribute types per story
✅ **Structured storage** - Characters, entities, and world systems
✅ **Evolution tracking** - Log all changes with narrative reasons
✅ **Visibility control** - Characters know different things
✅ **Agent integration** - Easy formatting for prompts
✅ **Query utilities** - Find characters by attributes
✅ **Modification helpers** - Update and log changes
✅ **Replay support** - Reconstruct state from logs

This enables rich simulation of complex fictional worlds with domain-specific rules, powers, and social structures!
