# Domain Attributes Quick Reference

## Common Use Cases

### Check if character has attribute
```python
from dreamdive.domain_attribute_manager import check_character_has_attribute

if check_character_has_attribute(character, "word_spirit", "Jun Yan"):
    # Character has Jun Yan word spirit
    apply_fire_combat_bonus()
```

### Find all characters with attribute
```python
from dreamdive.domain_attribute_manager import find_characters_with_attribute

# Find all House Stark members
stark_members = find_characters_with_attribute(
    all_characters, "house_allegiance", "Stark"
)

# Find all characters with any word spirit
word_spirit_users = find_characters_with_attribute(
    all_characters, "word_spirit"  # No value = match any
)
```

### Format for agent prompt
```python
from dreamdive.domain_attribute_manager import format_domain_attributes_for_prompt

# When building agent context
domain_text = format_domain_attributes_for_prompt(
    character_id=character.character_id,
    domain_attributes=character.domain_attributes,
    domain_registry=extraction.domain_registry,
    viewer_id=viewing_agent_id,  # Filters by visibility
)

# Add to prompt
prompt = f"""
{identity_section}

{domain_text}

{scene_context}
"""
```

### Update an attribute
```python
from dreamdive.domain_attribute_manager import DomainAttributeModifier

# Update character's bloodline purity
DomainAttributeModifier.update_character_attribute(
    character=character,
    attribute_key="bloodline_purity",
    new_value=0.48,  # Increased
    acquisition_narrative="Refined through dragon bone ritual",
    can_evolve=True,
    evolution_triggers=["blood rage", "deadpool threshold"],
    visibility="faction",
)
```

### Log attribute change
```python
from dreamdive.domain_attribute_manager import DomainAttributeModifier

# Create change record for replay
change_log = DomainAttributeModifier.create_change_record(
    character_id=character.character_id,
    attribute_key="word_spirit",
    tick=current_tick,
    timeline_index=timeline_idx,
    event_sequence=event_seq,
    change_type="evolved",  # acquired|lost|evolved|activated|deactivated|modified
    old_value={"name": "Jun Yan"},
    new_value={"name": "Jun Yan - Awakened"},
    event_id=event_id,
    narrative_reason="Awakened protecting Lu Mingfei from dragon",
)

# Store the change
repository.append_domain_attribute_change(change_log)
```

### Get attribute value
```python
from dreamdive.domain_attribute_manager import DomainAttributeQuery

# Get the value
bloodline = DomainAttributeQuery.get_attribute(character, "bloodline_purity")
if bloodline and bloodline > 0.5:
    trigger_deadpool_warning()
```

### Compare attributes between characters
```python
from dreamdive.domain_attribute_manager import DomainAttributeQuery

comparison = DomainAttributeQuery.compare_attributes(
    char1, char2, "cultivation_level"
)
# Returns: "char1 has cultivation_level=Golden Core, char2 has Foundation Building"
```

## Creating Domain Systems (P1)

### Dragon Raja Example
```python
from dreamdive.domain_systems import create_dragon_raja_system

# Use pre-built example
registry = create_dragon_raja_system()

# Or create custom
from dreamdive.domain_systems import (
    DomainSystemRegistry,
    DomainAttributeDefinition,
    AttributeEvolutionMode,
)

registry = DomainSystemRegistry(
    story_id="my_story",
    attribute_definitions=[
        DomainAttributeDefinition(
            attribute_key="word_spirit",
            display_name="言灵",
            value_type="structured",
            evolution_mode=AttributeEvolutionMode.TRANSFORMATIVE,
            narrative_weight=1.0,
        ),
    ],
)
```

### Assigning to Characters
```python
from dreamdive.domain_systems import DomainAttributeValue, AttributeVisibility

character.domain_attributes = {
    "word_spirit": DomainAttributeValue(
        attribute_key="word_spirit",
        value={
            "name": "Jun Yan",
            "serial": "89",
            "element": "fire",
        },
        visibility=AttributeVisibility.PUBLIC,
        can_evolve=True,
        evolution_triggers=["bloodline awakening"],
    ),
}
```

## Visibility Levels

- `PUBLIC`: Everyone knows (visible weapon, public title)
- `PRIVATE`: Only the character knows (hidden ability, secret technique)
- `FACTION`: Faction members know (sect secrets, house strategies)
- `REVEALED`: Was hidden, now revealed (secret identity exposed)
- `HIDDEN`: GM-only, nobody knows (未揭示的真相)

When using `format_domain_attributes_for_prompt`, attributes are automatically filtered by visibility based on `viewer_id`.

## Change Types

- `acquired`: Character gains new attribute
- `lost`: Attribute removed
- `evolved`: Attribute transforms (e.g., 言灵 awakens)
- `activated`: Dormant attribute becomes active
- `deactivated`: Active attribute becomes dormant
- `modified`: Value changes (e.g., bloodline increases)

## SQL Queries

### Get attribute history for character
```sql
SELECT * FROM domain_attribute_changes
WHERE character_id = 'chu_zihang'
ORDER BY timeline_index, event_sequence;
```

### Find all characters with attribute
```sql
SELECT * FROM find_characters_with_attribute('word_spirit');
```

### Get current attribute value
```sql
SELECT get_current_domain_attribute('chu_zihang', 'bloodline_purity');
```

### Find secret identity reveals
```sql
SELECT character_id, narrative_reason, tick
FROM domain_attribute_changes
WHERE visibility_changed = true
  AND new_visibility = 'revealed'
  AND attribute_key = 'secret_identity';
```

## Pre-built Examples

### Dragon Raja
```python
from dreamdive.domain_systems import create_dragon_raja_system
registry = create_dragon_raja_system()
# Includes: word_spirit, bloodline_purity, academy_rank, weapon_specialization
```

### Game of Thrones
```python
from dreamdive.domain_systems import create_game_of_thrones_system
registry = create_game_of_thrones_system()
# Includes: house_allegiance, titles, secret_identity
```

## Files to Reference

- **Full Guide**: [DOMAIN_ATTRIBUTES_GUIDE.md](DOMAIN_ATTRIBUTES_GUIDE.md)
- **Implementation**: [DOMAIN_ATTRIBUTES_IMPLEMENTATION.md](DOMAIN_ATTRIBUTES_IMPLEMENTATION.md)
- **Core Schema**: [src/dreamdive/domain_systems.py](src/dreamdive/domain_systems.py)
- **Runtime Utils**: [src/dreamdive/domain_attribute_manager.py](src/dreamdive/domain_attribute_manager.py)
- **Prompts**: [src/dreamdive/prompts/p1_domain_extraction.py](src/dreamdive/prompts/p1_domain_extraction.py)
- **Migration**: [migrations/0002_domain_attributes.sql](migrations/0002_domain_attributes.sql)
