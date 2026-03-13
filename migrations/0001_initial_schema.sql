CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS characters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    background TEXT,
    identity JSONB NOT NULL DEFAULT '{}'::jsonb,
    universal_dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    prominent_dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
    domain_attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS state_change_log (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    character_id TEXT NOT NULL,
    dimension TEXT NOT NULL,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    from_value JSONB,
    to_value JSONB NOT NULL,
    trigger TEXT,
    emotional_tag TEXT,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_state_change_log_replay
    ON state_change_log (character_id, dimension, timeline_index, event_sequence);

CREATE TABLE IF NOT EXISTS goal_stack (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    character_id TEXT NOT NULL,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    goals JSONB NOT NULL DEFAULT '[]'::jsonb,
    actively_avoiding TEXT,
    most_uncertain_relationship TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_goal_stack_replay
    ON goal_stack (character_id, timeline_index, event_sequence);

CREATE TABLE IF NOT EXISTS relationship_log (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    from_character_id TEXT NOT NULL,
    to_character_id TEXT NOT NULL,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    trust_delta DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    trust_value DOUBLE PRECISION NOT NULL,
    sentiment_shift TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_relationship_log_replay
    ON relationship_log (from_character_id, to_character_id, timeline_index, event_sequence);

CREATE TABLE IF NOT EXISTS episodic_memory (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    character_id TEXT NOT NULL,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    event_id TEXT,
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,
    location TEXT,
    summary TEXT NOT NULL,
    emotional_tag TEXT,
    salience DOUBLE PRECISION NOT NULL,
    pinned BOOLEAN NOT NULL DEFAULT FALSE,
    compressed BOOLEAN NOT NULL DEFAULT FALSE,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_replay
    ON episodic_memory (character_id, timeline_index, event_sequence);
CREATE INDEX IF NOT EXISTS idx_episodic_memory_embedding
    ON episodic_memory USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS event_log (
    id BIGSERIAL PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL,
    seed_type TEXT NOT NULL,
    location TEXT NOT NULL DEFAULT '',
    participants JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL,
    salience DOUBLE PRECISION NOT NULL,
    outcome_summary TEXT NOT NULL DEFAULT '',
    resolution_mode TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_event_log_timeline_salience
    ON event_log (timeline_index, salience DESC);

CREATE TABLE IF NOT EXISTS world_snapshot (
    id BIGSERIAL PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    tick TEXT NOT NULL,
    timeline_index BIGINT NOT NULL UNIQUE,
    event_sequence INTEGER NOT NULL DEFAULT 0,
    agent_locations JSONB NOT NULL DEFAULT '{}'::jsonb,
    narrative_arc JSONB NOT NULL DEFAULT '{}'::jsonb,
    unresolved_threads JSONB NOT NULL DEFAULT '[]'::jsonb,
    next_tick_size_minutes INTEGER NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS entity (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    objective_facts JSONB NOT NULL DEFAULT '[]'::jsonb,
    narrative_role TEXT NOT NULL DEFAULT '',
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_entity_embedding
    ON entity USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE TABLE IF NOT EXISTS entity_representation (
    id BIGSERIAL PRIMARY KEY,
    entity_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    meaning TEXT NOT NULL DEFAULT '',
    emotional_charge TEXT NOT NULL DEFAULT '',
    goal_relevance TEXT NOT NULL DEFAULT '',
    misunderstanding TEXT NOT NULL DEFAULT '',
    confidence TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (entity_id, agent_id)
);

CREATE INDEX IF NOT EXISTS idx_entity_representation_agent
    ON entity_representation (agent_id, entity_id);

CREATE TABLE IF NOT EXISTS simulation_session (
    session_id TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    current_tick_label TEXT NOT NULL,
    current_timeline_index BIGINT NOT NULL DEFAULT 0,
    session_payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
