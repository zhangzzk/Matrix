# Domain Attribute System - Implementation Summary

## What Was Built

A comprehensive system for managing domain-specific character and world attributes in story simulations. This solves the problem of representing story-specific concepts like:

- **龙族 (Dragon Raja)**: 言灵 (Word Spirits), bloodline purity, special weapons, academy rankings
- **Game of Thrones**: House allegiances, titles, secret identities, oaths
- **Cultivation novels**: Cultivation levels, spiritual roots, techniques, sect affiliations
- And any other domain-specific systems unique to a fictional world

## Files Created

### 1. Core System ([src/dreamdive/domain_systems.py](src/dreamdive/domain_systems.py))

Defines the schema for domain attributes:

- `DomainAttributeDefinition`: Defines a type of attribute (e.g., "word_spirit", "house_allegiance")
- `DomainAttributeValue`: An instance of an attribute attached to a character
- `DomainAttributeChange`: Records attribute changes during simulation
- `WorldDomainSystem`: World-level systems that govern attribute behavior
- `DomainSystemRegistry`: Complete registry of all domain systems for a story
- `EntityDomainAttributes`: Attributes for non-character entities (locations, items, etc.)

Includes pre-built examples for Dragon Raja and Game of Thrones.

### 2. Runtime Manager ([src/dreamdive/domain_attribute_manager.py](src/dreamdive/domain_attribute_manager.py))

Utilities for working with domain attributes during simulation:

- `DomainAttributeFormatter`: Format attributes for LLM prompts with visibility filtering
- `DomainAttributeQuery`: Query character attributes (has_attribute, get_attribute, compare)
- `DomainAttributeModifier`: Update attributes and create change logs
- Convenience functions for common operations

### 3. Extraction Prompts ([src/dreamdive/prompts/p1_domain_extraction.py](src/dreamdive/prompts/p1_domain_extraction.py))

LLM prompts for P1 ingestion phase:

- `DOMAIN_SYSTEM_IDENTIFICATION_PROMPT`: Identify domain systems in source material
- `DOMAIN_ATTRIBUTE_EXTRACTION_PROMPT`: Extract character-specific attributes
- `ENTITY_DOMAIN_ATTRIBUTES_PROMPT`: Extract attributes for locations, items, etc.

### 4. Documentation ([DOMAIN_ATTRIBUTES_GUIDE.md](DOMAIN_ATTRIBUTES_GUIDE.md))

Complete usage guide with:

- Architecture overview
- Integration with existing system (P1/P2/P3 phases)
- Practical examples for Dragon Raja, Game of Thrones, cultivation novels
- Advanced features (visibility, evolution triggers, structured values)
- Best practices
- Migration path for existing simulations

### 5. Database Migration ([migrations/0002_domain_attributes.sql](migrations/0002_domain_attributes.sql))

SQL schema for PostgreSQL:

- `domain_attribute_changes` table: Logs all attribute changes
- `entity_domain_attributes` table: Stores entity attributes
- Helper functions: `get_current_domain_attribute`, `find_characters_with_attribute`
- Indexes for efficient querying

### 6. Model Integration

Updated existing models to support domain attributes:

- [src/dreamdive/ingestion/models.py](src/dreamdive/ingestion/models.py):
  - Added `domain_attributes` field to `CharacterExtractionRecord`
  - Added `domain_registry` field to `AccumulatedExtraction`

- [src/dreamdive/db/models.py](src/dreamdive/db/models.py):
  - Added documentation to `CharacterRecord.domain_attributes`
  - Added `DomainAttributeChangeRecord` dataclass

- [src/dreamdive/schemas.py](src/dreamdive/schemas.py):
  - Enhanced `CharacterIdentity.domain_attributes` with documentation

## Key Features

### 1. Flexible Schema Definition

Define domain-specific attributes unique to each story:

```python
DomainAttributeDefinition(
    attribute_key="word_spirit",
    display_name="言灵 (Word Spirit)",
    value_type="structured",
    evolution_mode=AttributeEvolutionMode.TRANSFORMATIVE,
    possible_values=["Jun Yan", "Time Zero", ...],
    narrative_weight=1.0,
)
```

### 2. Visibility Control

Attributes can be public, private, faction-only, or hidden:

```python
DomainAttributeValue(
    attribute_key="secret_identity",
    value="Aegon Targaryen",
    visibility=AttributeVisibility.HIDDEN,  # Nobody knows yet
)
```

### 3. Evolution Tracking

Track how attributes change over time:

```python
# Logs when 言灵 evolves, bloodline purifies, identities reveal, etc.
DomainAttributeModifier.create_change_record(
    character_id="chu_zihang",
    attribute_key="word_spirit",
    change_type="evolved",
    old_value={"name": "Jun Yan"},
    new_value={"name": "Jun Yan - Awakened"},
    narrative_reason="Emotional breakthrough protecting Lu Mingfei",
)
```

### 4. Agent Integration

Easy formatting for LLM prompts with automatic visibility filtering:

```python
# Formats as markdown for agent context
domain_text = format_domain_attributes_for_prompt(
    character_id=agent_id,
    domain_attributes=character.domain_attributes,
    viewer_id=agent_id,  # Filter by what this agent can see
)
```

### 5. Query Utilities

Find characters by attributes:

```python
# Find all Stark house members
stark_members = find_characters_with_attribute(
    characters, "house_allegiance", "Stark"
)

# Check if character has specific 言灵
has_jun_yan = check_character_has_attribute(
    character, "word_spirit", "Jun Yan"
)
```

## Integration Points

### Phase P1 (Ingestion)

1. **Identify domain systems** in source material
   - Run `DOMAIN_SYSTEM_IDENTIFICATION_PROMPT`
   - Creates `DomainSystemRegistry`

2. **Extract character attributes**
   - Run `DOMAIN_ATTRIBUTE_EXTRACTION_PROMPT` per character
   - Populates `CharacterExtractionRecord.domain_attributes`

3. **Extract entity attributes** (locations, items, etc.)
   - Run `ENTITY_DOMAIN_ATTRIBUTES_PROMPT`
   - Creates `EntityDomainAttributes` records

4. **Store in AccumulatedExtraction**
   - `extraction.domain_registry` = registry
   - `extraction.characters[i].domain_attributes` = attributes

### Phase P2/P3 (Simulation)

1. **Load into agent context**
   ```python
   domain_section = format_domain_attributes_for_prompt(...)
   prompt = f"{identity_section}\n\n{domain_section}\n\n{scene_context}"
   ```

2. **Query during event resolution**
   ```python
   if check_character_has_attribute(char, "word_spirit"):
       # Apply word spirit combat logic
   ```

3. **Modify during simulation**
   ```python
   # When bloodline evolves
   DomainAttributeModifier.update_character_attribute(...)
   change_log = DomainAttributeModifier.create_change_record(...)
   repository.append_domain_attribute_change(change_log)
   ```

4. **Replay support**
   - All changes logged to `domain_attribute_changes` table
   - Can reconstruct attribute state at any tick

## Example: Dragon Raja 言灵 System

### P1 Extraction

```json
{
  "domain_registry": {
    "attribute_definitions": [
      {
        "attribute_key": "word_spirit",
        "display_name": "言灵",
        "evolution_mode": "transformative"
      }
    ]
  },
  "characters": [
    {
      "id": "chu_zihang",
      "domain_attributes": {
        "word_spirit": {
          "value": {"name": "Jun Yan", "serial": "89"},
          "can_evolve": true,
          "evolution_triggers": ["bloodline awakening"]
        }
      }
    }
  ]
}
```

### P2 Agent Context

```markdown
## Domain-Specific Attributes
- **言灵 (Word Spirit)**: Jun Yan (君焰), Controls fire and combustion
  [Can evolve: bloodline awakening, emotional breakthrough]
- **血统纯度 (Bloodline Purity)**: 0.43
  [Can evolve: dragon bone refinement, blood rage]
```

### P2 Evolution Event

```python
# When 言灵 evolves during emotional scene
if emotional_breakthrough:
    old_value = DomainAttributeQuery.get_attribute(char, "word_spirit")
    new_value = {"name": "Jun Yan - Awakened", "power": 3.0}

    DomainAttributeModifier.update_character_attribute(
        char, "word_spirit", new_value
    )

    change_log = DomainAttributeModifier.create_change_record(
        character_id="chu_zihang",
        change_type="evolved",
        old_value=old_value,
        new_value=new_value,
        narrative_reason="Awakened protecting Lu Mingfei",
        **replay_coords,
    )
```

## Next Steps

### To Use This System

1. **Run the migration**:
   ```bash
   psql < migrations/0002_domain_attributes.sql
   ```

2. **During P1 ingestion**, add domain extraction step:
   ```python
   # After character extraction
   domain_registry = extract_domain_systems(source_material)
   for character in characters:
       character.domain_attributes = extract_character_domain_attrs(
           character, domain_registry, source_material
       )
   extraction.domain_registry = domain_registry
   ```

3. **During P2 simulation**, use the utilities:
   ```python
   from dreamdive.domain_attribute_manager import (
       format_domain_attributes_for_prompt,
       check_character_has_attribute,
       DomainAttributeModifier,
   )

   # In agent context builder
   domain_text = format_domain_attributes_for_prompt(...)

   # In event resolution
   if check_character_has_attribute(char, "word_spirit", "Time Zero"):
       # Apply Time Zero effects

   # When attributes change
   change_log = DomainAttributeModifier.create_change_record(...)
   ```

### Future Enhancements

- **Automatic detection**: Train a model to auto-identify domain systems
- **Conflict resolution**: Rules for when attributes interact (e.g., two 言灵 clash)
- **Attribute dependencies**: Some attributes require others (e.g., must have bloodline to have 言灵)
- **Temporal attributes**: Attributes that only exist during certain time periods
- **Shared attributes**: Attributes that link multiple characters (e.g., twins sharing power)

## Benefits

✅ **Generalizable**: Works for any story with domain-specific systems
✅ **Extensible**: Easy to add new attribute types mid-simulation
✅ **Trackable**: Full history of all changes with narrative reasons
✅ **Integrated**: Seamlessly fits into existing P1/P2/P3 pipeline
✅ **Queryable**: Easy to find characters by attributes, compare values
✅ **Visible-aware**: Respects what each character knows vs. doesn't know
✅ **Replay-compatible**: Can reconstruct state at any point in time

This system makes it possible to faithfully simulate complex fictional worlds with unique power systems, social structures, and mechanical rules!
