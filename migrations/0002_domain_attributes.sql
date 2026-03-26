-- Migration: Add Domain Attribute System
-- This migration adds support for tracking domain-specific character attributes
-- like 言灵 (Word Spirits), bloodlines, house allegiances, cultivation levels, etc.

-- Table to log domain attribute changes during simulation
CREATE TABLE IF NOT EXISTS domain_attribute_changes (
    id SERIAL PRIMARY KEY,

    -- What changed
    character_id TEXT NOT NULL,
    attribute_key TEXT NOT NULL,

    -- When it changed
    tick TEXT NOT NULL,
    timeline_index INTEGER NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,

    -- What kind of change
    change_type TEXT NOT NULL,  -- acquired | lost | evolved | activated | deactivated | modified

    -- The change details
    old_value JSONB,
    new_value JSONB NOT NULL,

    -- Context
    event_id TEXT,
    narrative_reason TEXT DEFAULT '',

    -- Visibility changes (e.g., secret identity revealed)
    visibility_changed BOOLEAN DEFAULT FALSE,
    old_visibility TEXT,  -- public | private | faction | hidden | revealed
    new_visibility TEXT,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_domain_attr_changes_character
    ON domain_attribute_changes(character_id);

CREATE INDEX IF NOT EXISTS idx_domain_attr_changes_tick
    ON domain_attribute_changes(tick, timeline_index, event_sequence);

CREATE INDEX IF NOT EXISTS idx_domain_attr_changes_attribute
    ON domain_attribute_changes(attribute_key);

CREATE INDEX IF NOT EXISTS idx_domain_attr_changes_event
    ON domain_attribute_changes(event_id)
    WHERE event_id IS NOT NULL;

-- Composite index for replaying a specific character's attribute history
CREATE INDEX IF NOT EXISTS idx_domain_attr_changes_char_attr_time
    ON domain_attribute_changes(character_id, attribute_key, timeline_index, event_sequence);

-- Comments for documentation
COMMENT ON TABLE domain_attribute_changes IS
    'Tracks changes to domain-specific character attributes (言灵, bloodlines, titles, etc.) during simulation';

COMMENT ON COLUMN domain_attribute_changes.change_type IS
    'Type of change: acquired (new attribute), lost (removed), evolved (transformed), activated (became active), deactivated (became inactive), modified (value changed)';

COMMENT ON COLUMN domain_attribute_changes.narrative_reason IS
    'Story-based explanation for why this change happened (e.g., "Awakened word spirit during emotional breakthrough")';

COMMENT ON COLUMN domain_attribute_changes.visibility_changed IS
    'True if this change affected who knows about this attribute (e.g., secret identity revealed)';


-- Table to store entity (non-character) domain attributes
-- Entities are things like locations, items, factions, concepts
CREATE TABLE IF NOT EXISTS entity_domain_attributes (
    id SERIAL PRIMARY KEY,

    -- Entity identification
    entity_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,  -- location | item | faction | concept | artifact
    entity_name TEXT NOT NULL,

    -- Domain attributes (stored as JSONB for flexibility)
    -- Structure: {"attribute_key": {"value": ..., "visibility": ..., "metadata": ...}}
    domain_attributes JSONB DEFAULT '{}',

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    -- Ensure one record per entity
    UNIQUE(entity_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_entity_domain_attrs_type
    ON entity_domain_attributes(entity_type);

CREATE INDEX IF NOT EXISTS idx_entity_domain_attrs_name
    ON entity_domain_attributes(entity_name);

-- GIN index for JSONB querying
CREATE INDEX IF NOT EXISTS idx_entity_domain_attrs_jsonb
    ON entity_domain_attributes USING GIN (domain_attributes);

COMMENT ON TABLE entity_domain_attributes IS
    'Domain-specific attributes for non-character entities (locations, items, factions, concepts)';


-- Add a column to simulation_session to store domain registry
-- This stores the DomainSystemRegistry for the story
ALTER TABLE simulation_session
ADD COLUMN IF NOT EXISTS domain_registry JSONB DEFAULT NULL;

COMMENT ON COLUMN simulation_session.domain_registry IS
    'DomainSystemRegistry JSON defining domain-specific systems for this story (言灵 system, house system, etc.)';


-- Update the characters table if it exists (optional, for PostgreSQL backend)
-- The domain_attributes column already exists in CharacterRecord as a dict
-- But we'll add a comment for clarity
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'characters'
    ) THEN
        COMMENT ON COLUMN characters.domain_attributes IS
            'Domain-specific character attributes stored as JSONB. Keys are attribute_key strings, values are DomainAttributeValue dicts with structure: {attribute_key, value, visibility, can_evolve, evolution_triggers, etc.}';
    END IF;
END $$;


-- Helper function to get current domain attribute value for a character
CREATE OR REPLACE FUNCTION get_current_domain_attribute(
    p_character_id TEXT,
    p_attribute_key TEXT,
    p_tick TEXT DEFAULT NULL,
    p_timeline_index INTEGER DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    latest_change RECORD;
BEGIN
    -- Get the most recent change for this character and attribute
    -- If tick/timeline_index provided, get state at that point
    -- Otherwise get absolute latest

    IF p_tick IS NOT NULL AND p_timeline_index IS NOT NULL THEN
        SELECT new_value INTO latest_change
        FROM domain_attribute_changes
        WHERE character_id = p_character_id
          AND attribute_key = p_attribute_key
          AND (tick, timeline_index) <= (p_tick, p_timeline_index)
        ORDER BY timeline_index DESC, event_sequence DESC
        LIMIT 1;
    ELSE
        SELECT new_value INTO latest_change
        FROM domain_attribute_changes
        WHERE character_id = p_character_id
          AND attribute_key = p_attribute_key
        ORDER BY timeline_index DESC, event_sequence DESC
        LIMIT 1;
    END IF;

    RETURN latest_change.new_value;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_current_domain_attribute IS
    'Get the current value of a domain attribute for a character, optionally at a specific point in time';


-- Helper function to get all characters with a specific attribute value
CREATE OR REPLACE FUNCTION find_characters_with_attribute(
    p_attribute_key TEXT,
    p_attribute_value JSONB DEFAULT NULL
) RETURNS TABLE(character_id TEXT, current_value JSONB) AS $$
BEGIN
    RETURN QUERY
    WITH latest_values AS (
        SELECT DISTINCT ON (dac.character_id)
            dac.character_id,
            dac.new_value
        FROM domain_attribute_changes dac
        WHERE dac.attribute_key = p_attribute_key
        ORDER BY dac.character_id, dac.timeline_index DESC, dac.event_sequence DESC
    )
    SELECT lv.character_id, lv.new_value
    FROM latest_values lv
    WHERE p_attribute_value IS NULL
       OR lv.new_value = p_attribute_value;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_characters_with_attribute IS
    'Find all characters that currently have a specific domain attribute, optionally filtering by value';


-- Example queries for common operations:

-- Get all domain attribute changes for a character
-- SELECT * FROM domain_attribute_changes
-- WHERE character_id = 'chu_zihang'
-- ORDER BY timeline_index, event_sequence;

-- Get all characters with a specific word spirit
-- SELECT * FROM find_characters_with_attribute('word_spirit', '"Jun Yan"'::jsonb);

-- Get attribute value at a specific point in time
-- SELECT get_current_domain_attribute('chu_zihang', 'bloodline_purity', 'ch15_023', 150);

-- Find all secret identities that have been revealed
-- SELECT character_id, attribute_key, narrative_reason
-- FROM domain_attribute_changes
-- WHERE visibility_changed = true
--   AND new_visibility = 'revealed'
--   AND attribute_key = 'secret_identity';
