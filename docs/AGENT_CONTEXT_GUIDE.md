# Dreamdive/Matrix: LLM Agent Context Guide

**Purpose**: This guide provides future LLM agents with essential context about the Dreamdive/Matrix codebase to minimize token usage and maximize efficiency when working on this project.

**Last Updated**: 2026-03-23

---

## 🎯 Project Identity

**Dreamdive** (codename: **Matrix**) is a novel-grounded multi-agent simulation engine that:
1. Ingests novels and extracts structured data (characters, events, metadata)
2. Simulates character-driven narrative events using LLM-powered agents
3. Synthesizes simulation events back into novel-quality prose

**Key Paradigm**: Novel → Structured Extraction → Agent Simulation → Novel Generation

**Primary Language**: Python 3.10+, Type-annotated with Pydantic models

---

## 📁 Architecture Overview

### Core Pipeline Layers

```
P0: User Configuration   →   Convert user preferences to structured config
P1: Ingestion            →   Extract novel → structured data (sequential chapters)
P2: Snapshot Init        →   Bootstrap character states from extraction
P3: Simulation           →   Event-driven agent simulation (tick-based)
P5: Narrative Synthesis  →   Convert events → novel prose
```

### Key Design Principles

1. **Append-Only State**: All simulation state is logged immutably, replay derives snapshots
2. **Sequential Chapter Processing**: Chapters build on accumulated context from prior chapters
3. **Self-Correcting LLM Context**: LLMs warned that context from previous LLM passes may contain errors
4. **META Injection**: User preferences + novel metadata injected into all prompts via `[META]` sections
5. **Salience-Based Event Selection**: Events scored for narrative importance, high-salience events get spotlight treatment
6. **Type Safety**: Pydantic models everywhere for validation

---

## 🗂️ Critical File Map

### Core Directories

```
src/dreamdive/
├── schemas.py              # ALL Pydantic models (Goal, Memory, CharacterSnapshot, etc.)
├── config.py               # Settings (LLM keys, DB URLs, simulation params)
├── cli.py                  # CLI entry point (ingest, init, run, configure, synthesize)
├── cli_config.py           # TOML config parsing (dreamdive.toml)
│
├── ingestion/              # P1: Novel extraction
│   ├── extractor.py        # IngestionPipeline orchestrator
│   ├── backend.py          # LLMExtractionBackend (calls LLM prompts)
│   ├── models.py           # AccumulatedExtraction (includes user_meta)
│   ├── chunker.py          # Text chunking
│   └── source_loader.py    # Load novel files
│
├── prompts/                # Canonical prompt builders, organized by pipeline stage
│   ├── __init__.py         # Central exports + prompt group index
│   ├── p0_configuration.py # P0: Configuration prompts
│   ├── p1_ingestion.py     # P1: Structural scan, chapter extraction, meta, entities
│   ├── p2_character.py     # P2: Snapshot inference, goal seeding, trajectory projection
│   ├── p2_collisions.py    # P2: Goal collision detection
│   ├── p2_scene.py         # P2: Scene simulation + state update prompts
│   ├── p3_memory.py        # P3: Memory compression + narrative arc prompts
│   └── p5_synthesis.py     # P5: Chapter synthesis + summary prompts
│
├── llm/                    # LLM client & transport
│   ├── client.py           # StructuredLLMClient (async, JSON + text responses)
│   ├── prompts.py          # Legacy re-export wrapper; implementations live in prompts/
│   └── openai_transport.py # OpenAI-compatible API wrapper
│
├── simulation/             # P2/P3: Agent simulation
│   ├── workflow.py         # initialize_session(), run_session_tick(), advance_session()
│   ├── tick_runner.py      # SimulationTickRunner (main tick loop)
│   ├── bootstrap.py        # SnapshotBootstrapper (build CharacterSnapshot)
│   ├── initializer.py      # SnapshotInitializer (LLM-powered snapshot creation)
│   ├── trajectory.py       # TrajectoryProjector (agent intention projection)
│   ├── event_simulator.py  # EventSimulator (scene simulation)
│   ├── state_updater.py    # EventStateUpdater (post-event state updates)
│   ├── seed_detector.py    # SeedDetector (find narrative seeds)
│   ├── goal_collision.py   # GoalCollisionDetector (LLM-powered tension detection)
│   ├── world_manager.py    # WorldManager (tick sizing, agent selection)
│   └── session.py          # SimulationSessionState (session data structure)
│
├── db/                     # Data persistence
│   ├── bundle.py           # RepositoryBundle (in-memory or PostgreSQL)
│   ├── replay.py           # StateReplay (reconstruct state from logs)
│   └── session.py          # InMemoryStore (append-only log storage)
│
├── memory/                 # Memory consolidation & retrieval
│   ├── retrieval.py        # Semantic search, ranking
│   └── consolidation.py    # Memory compression
│
├── user_config.py          # P0: UserMeta schema (tone, emphasis, divergence seeds)
├── configuration_processor.py  # P0: LLMConfigurationBackend (conversation → UserMeta)
├── meta_injection.py       # Format [META] sections for prompts
├── narrative_synthesis.py  # P5: Chapter synthesis prompts & backend
├── divergence_seeds.py     # Divergence seed utilities (strong → goals, gentle → salience)
└── event_window_selector.py  # P5: Event selection for chapter synthesis
```

### Essential Files for Common Tasks

| Task | Files to Read |
|------|---------------|
| **Understanding ingestion** | `ingestion/extractor.py`, `ingestion/backend.py`, `prompts/p1_ingestion.py` |
| **Understanding simulation** | `simulation/workflow.py`, `simulation/tick_runner.py`, `schemas.py` |
| **Adding new prompt** | `prompts/__init__.py`, relevant `prompts/p*_*.py`, `llm/client.py` |
| **Modifying character state** | `schemas.py` (StateChangeLogEntry), `db/replay.py`, `simulation/state_updater.py` |
| **CLI commands** | `cli.py`, `cli_config.py`, `dreamdive.toml` |
| **User configuration** | `user_config.py`, `configuration_processor.py`, `meta_injection.py` |
| **Narrative synthesis** | `narrative_synthesis.py`, `event_window_selector.py`, `prompts/p5_synthesis.py` |

---

## 🔑 Key Concepts

### 1. ReplayKey & Timeline

**Every event/state change has a ReplayKey:**
```python
ReplayKey(
    tick="snapshot",              # Human-readable label
    timeline_index=1440,          # Sortable integer (minutes)
    event_sequence=0              # Within-tick ordering
)
```

**State Replay**: Given a `timeline_index`, replay all state changes ≤ that index to reconstruct agent state.

### 2. CharacterSnapshot

**Core agent state structure** (defined in `schemas.py:369-377`):
```python
CharacterSnapshot(
    identity: CharacterIdentity,       # Name, traits, values, fears
    replay_key: ReplayKey,
    current_state: Dict[str, Any],     # location, emotional_state, physical_state, etc.
    goals: List[Goal],                 # Goal stack (priority-ordered)
    working_memory: List[EpisodicMemory],  # Top 5 most relevant memories
    relationships: List[RelationshipLogEntry],
    inferred_state: Optional[SnapshotInference]  # LLM-inferred subtext
)
```

### 3. Simulation Tick Flow

**High-level tick execution** (`simulation/tick_runner.py:136-604`):
```
1. Select active agents (salience-based)
2. Assemble context packets (memories, relationships, entities)
3. Project trajectories (what agents plan to do)
4. Detect seeds (spatial collisions, goal collisions, solo seeds)
5. Rank seeds by salience
6. Simulate events (spotlight/foreground/background modes)
7. Update agent state (emotions, goals, memories, relationships)
8. Write world snapshot
9. Schedule background maintenance
```

### 4. Ingestion Accumulation

**Sequential chapter processing** (`ingestion/extractor.py`):
- Each chapter extraction receives **accumulated context** from all prior chapters
- Context includes: character registry, event timeline, relationship graph
- **CRITICAL**: Prompts warn that context is from prior LLM passes and may contain errors
- LLMs instructed to validate/correct context against current chapter

**Storage** (`ingestion/models.py:190-227`):
```python
AccumulatedExtraction(
    characters: List[CharacterExtractionRecord],  # All characters so far
    world: WorldExtractionRecord,                # Setting, factions, era
    events: List[EventExtractionRecord],         # Event timeline
    meta: MetaLayerRecord,                       # Themes, style, authorial intent
    entities: List[EntityRecord],                # Places, objects, concepts
    user_meta: Optional[UserMeta]                # User preferences (P0)
)
```

### 5. UserMeta & META Injection

**User preferences stored as structured config** (`user_config.py`):
```python
UserMeta(
    tone: TonePreferences,           # Desired output tone vs. original
    emphasis: EmphasisPreferences,   # What to emphasize/deprioritize
    divergence_seeds: List[DivergenceSeed],  # Story changes (strong/gentle)
    focus_characters: List[str],     # Characters to prioritize
    chapter_format: ChapterFormat    # Word count, POV style, pacing
)
```

**[META] sections injected into prompts** (`meta_injection.py`):
```
[META]
Original authorial intent: ...
Original themes: ...
Original tone: ...
User desired tone: ...
User emphasis: ...
Focus characters: ...
```

### 6. Divergence Seeds

**Two types** (`divergence_seeds.py`):

- **Strong seeds**: Inject as high-priority Goals in character's goal stack
  - Example: "Ned Stark decides to confront Cersei privately"
  - Effect: Directly drives agent behavior

- **Gentle seeds**: Increase salience weighting for relevant events (+20%)
  - Example: "More focus on Stark family dynamics"
  - Effect: Makes matching events more likely to be spotlight events

**Focus characters**: +50% salience boost for events involving them

### 7. LLM Prompts

**All prompt builders live in** `src/dreamdive/prompts/`:

| Module | Purpose |
|--------|---------|
| `prompts/p0_configuration.py` | User-facing configuration conversation + P0 config processing |
| `prompts/p1_ingestion.py` | Structural scan, chapter extraction, meta layer, entity extraction |
| `prompts/p2_character.py` | Snapshot inference, goal seeding, trajectory projection |
| `prompts/p2_collisions.py` | Goal collision detection |
| `prompts/p2_scene.py` | Background events, spotlight setup, agent beats, resolution checks, state updates |
| `prompts/p3_memory.py` | Memory compression and narrative arc maintenance |
| `prompts/p5_synthesis.py` | Chapter synthesis and chapter summary |

**Compatibility note**: `llm/prompts.py`, `simulation/prompts.py`, `simulation/event_prompts.py`, and `memory/prompts.py` are now wrappers that re-export the central prompt builders.

**Prompt Structure** (PromptRequest):
```python
PromptRequest(
    system: str,           # System instructions
    user: str,             # User message (main content)
    max_tokens: int,       # Token budget
    stream: bool,          # Streaming mode
    metadata: Dict         # Debug info
)
```

### 8. Event Modes

**Three simulation modes** (`simulation/world_manager.py`):

| Mode | Salience Range | Treatment | Max Beats |
|------|---------------|-----------|-----------|
| **Spotlight** | ≥0.75 | Full scene simulation with dialogue | 8 |
| **Foreground** | 0.40-0.74 | Shorter scene simulation | 4 |
| **Background** | <0.40 | Narrative summary only | N/A |

### 9. Configuration Files

**dreamdive.toml** structure:
```toml
[defaults]
workspace = ".dreamdive"
session_id = "main"

[ingest]
source = "resources/novel.txt"
rerun_structural_scan = false

[init]
chapter_id = "002"
max_workers = 32

[run]
ticks = 50
tick_max_events = 15
max_workers = 32

[configure]
novel_title = "Novel Title"
author = "Author Name"

[synthesize]
start_tick = 0
ticks_per_chapter = 20
output_dir = ".dreamdive/chapters"
```

---

## ⚡ Common Patterns

### Pattern 1: Adding a New Pydantic Model

1. Define in `schemas.py`
2. Add to relevant repositories in `db/queries.py`
3. Update serialization in `simulation/workflow.py` (if append-only log)

### Pattern 2: Adding a New Prompt

1. Add prompt builder function to the relevant module under `src/dreamdive/prompts/`
2. Re-export it from `prompts/__init__.py` if it should be part of the public prompt surface
3. Return `PromptRequest` with system + user messages
4. Call via `StructuredLLMClient.call_json()` for JSON or `.call_text()` for prose
5. Add validation/error handling

### Pattern 3: Modifying Character State

1. Create `StateChangeLogEntry` with new dimension
2. Append to `state_repo`
3. Update `normalize_current_state()` in `simulation/state_normalization.py` if needed
4. Replay will automatically reconstruct state

### Pattern 4: Adding CLI Command

1. Add subparser in `cli.py:build_parser()`
2. Add defaults to `CLI_DEFAULTS` in `cli_config.py`
3. Implement handler in `cli.py`
4. Update `dreamdive.toml.example` with example config

---

## 🐛 Debugging Tips

### Reading Debug Output

**Debug mode** (`--debug --debug-dir /path`):
- Writes `events.jsonl` with high-level flow milestones
- Writes LLM calls to `llm/` directory (request, response, parsed JSON, metadata)
- Useful for diagnosing extraction/simulation issues

**Key log locations**:
```
debug/
├── events.jsonl           # Timeline of operations
├── llm/
│   ├── 001_request.json
│   ├── 001_response.txt
│   ├── 001_parsed.json
│   └── 001_metadata.json
```

### Common Issues

| Symptom | Likely Cause | Fix Location |
|---------|--------------|--------------|
| **"Chapter not found"** | Structural scan didn't detect chapter | `ingestion/chunker.py`, check chapter delimiter |
| **"No accumulated extraction"** | Ingestion incomplete | Run `dreamdive ingest` first |
| **Agent state replay mismatch** | State change log corruption | Check `db/replay.py`, verify timeline_index ordering |
| **LLM validation error** | JSON schema mismatch | Check relevant file in `prompts/`, verify Pydantic model |
| **Memory not retrieved** | Embedding not computed | Check `memory/retrieval.py:embed_text()` |

### Useful CLI Commands

```bash
# Full ingestion from scratch
PYTHONPATH=src python3 -m dreamdive.cli ingest --rerun-structural-scan --rerun-chapters

# Initialize snapshot with debug
PYTHONPATH=src python3 -m dreamdive.cli init --debug --max-workers 4

# Run simulation for 10 ticks
PYTHONPATH=src python3 -m dreamdive.cli run --ticks 10

# Branch simulation to earlier point
PYTHONPATH=src python3 -m dreamdive.cli branch --timeline-index 1000 --output-session-id branched

# View simulation state
PYTHONPATH=src python3 -m dreamdive.cli visualize
```

---

## 🧩 Integration Points

### Where User Preferences Flow

```
P0: configure command
  ↓ (conversation → UserMeta)
P1: ingest command (AccumulatedExtraction.user_meta = ...)
  ↓ (LLMExtractionBackend.__init__(user_meta=...))
  ↓ (All ingestion prompts receive user_meta)
  ↓ ([META] sections injected)
P2: init (strong seeds → Goals, focus chars → identity)
  ↓ (SnapshotInitializer applies user preferences)
P3: simulation tick (gentle seeds → salience modifiers)
  ↓ (apply_all_salience_modifiers())
P5: synthesize command (events → prose with user tone/format)
  ↓ (build_chapter_synthesis_prompt(user_meta=...))
```

### Where [META] Sections Are Injected

**All LLM prompts that shape narrative direction**:
- Structural scan
- Chapter extraction
- Meta layer extraction
- Entity extraction
- Trajectory projection
- Event simulation
- State updates
- Chapter synthesis

**Implementation**: `meta_injection.py:format_meta_section()`

---

## 🚀 Quick Start for Common Tasks

### Task: Add Support for a New State Dimension

**Example**: Add "hunger_level" to character state

1. **No schema changes needed** (current_state is Dict[str, Any])
2. **Update normalization** (optional, if dimension has default):
   ```python
   # In simulation/state_normalization.py
   def normalize_current_state(state, inferred):
       return {
           "hunger_level": state.get("hunger_level", 0.5),  # Add this
           **state
       }
   ```
3. **Update relevant prompts** to mention the new dimension
4. **LLMs will start populating it** via StateChangeLogEntry

### Task: Add a New CLI Command

**Example**: Add `dreamdive export` command

```python
# In cli.py:build_parser()
export = subparsers.add_parser("export", help="Export simulation data")
export.add_argument("--format", choices=["json", "csv"], default="json")
export.add_argument("--output", help="Output file path")

# In cli_config.py:CLI_DEFAULTS
"export": {
    "workspace": ".dreamdive",
    "format": "json",
    "output": "",
}

# In cli.py (handler)
def handle_export(args):
    # Implementation
    pass

# In main()
elif args.command == "export":
    handle_export(args)
```

### Task: Modify Ingestion Prompt

**Example**: Change structural scan to extract more setting detail

1. Edit `prompts/p1_ingestion.py:build_structural_scan_prompt()`
2. Update user message section describing setting extraction
3. Update expected JSON schema if needed (add fields to WorldExtractionRecord)
4. Rerun ingestion: `dreamdive ingest --rerun-structural-scan`

### Task: Add a New Background Job Type

**Example**: Add "relationship_consolidation" job

1. **Define job type** in `simulation/background_jobs.py`:
   ```python
   class RelationshipConsolidationJob(BackgroundJob):
       job_type = "relationship_consolidation"

       def execute(self, session, llm_client):
           # Implementation
           pass
   ```
2. **Add to planner** in `BackgroundJobPlanner.plan_all()`
3. **Add handler** in `BackgroundMaintenanceRunner.run_due_jobs()`

---

## 📊 Performance Considerations

### Parallelization

- **Chapter extraction**: Parallelized via `ThreadPoolExecutor` (max_workers=4 default)
- **Agent initialization**: Parallelized per-agent
- **Event simulation**: Sequential (maintains narrative coherence)
- **Trajectory projection**: Batched for high-priority agents, sequential for low-priority

### Token Optimization

- **Accumulated extraction**: Grows with each chapter, can become large
- **Solution**: Compression/summarization after N chapters (not yet implemented)
- **Memory retrieval**: Top-k semantic search (default k=20) to limit context

### LLM Call Budgeting

**Per tick**:
- N trajectory projections (N = active agents)
- 1 goal collision detection (batched)
- M event simulations (M = ranked seeds, typically 3-10)
- M × P state updates (P = participants per event)

**Rough estimate**: 50-200 LLM calls per simulation tick depending on agent count and event complexity

---

## 🎓 Learning Path for New Contributors

### Level 1: Understanding Data Flow
1. Read `schemas.py` (all models)
2. Read `ingestion/models.py` (AccumulatedExtraction)
3. Read `simulation/session.py` (SimulationSessionState)
4. Trace: Novel → AccumulatedExtraction → CharacterSnapshot → Tick → Updated Snapshot

### Level 2: Understanding Ingestion
1. Read `ingestion/extractor.py` (IngestionPipeline)
2. Read `ingestion/backend.py` (LLMExtractionBackend)
3. Read `prompts/p1_ingestion.py` (all P1 prompts)
4. Run: `dreamdive ingest --debug` and inspect output

### Level 3: Understanding Simulation
1. Read `simulation/workflow.py` (initialize_session, run_session_tick)
2. Read `simulation/tick_runner.py` (SimulationTickRunner.run_tick)
3. Read `simulation/event_simulator.py` (EventSimulator)
4. Run: `dreamdive run --ticks 1 --debug` and inspect event timeline

### Level 4: Understanding User Configuration
1. Read `user_config.py` (UserMeta schema)
2. Read `configuration_processor.py` (P0 backend)
3. Read `meta_injection.py` (META section formatting)
4. Read `prompts/p0_configuration.py` and `prompts/p5_synthesis.py`
5. Trace: User conversation → UserMeta → [META] → Prompts

---

## 🔮 Future Architecture Notes

### Planned Features (Not Yet Implemented)

- **Multi-turn configuration refinement**: Iterative conversation to refine UserMeta
- **Adaptive pacing**: Vary chapter length based on narrative tension
- **Interactive mode (Mode B)**: Real-time user input during simulation
- **Memory consolidation**: Automatic compression of old memories
- **PostgreSQL persistence**: Full production persistence backend (partially implemented)

### Extension Points

- **Custom event seeds**: Add new seed types in `simulation/seeds.py`
- **Custom LLM backends**: Implement LLMTransport protocol in `llm/openai_transport.py`
- **Custom repositories**: Implement Repository protocols in `db/queries.py`
- **Custom maintenance jobs**: Extend `BackgroundJob` in `simulation/background_jobs.py`

---

## 📝 Code Style & Conventions

### Naming Conventions

- **Modules**: `snake_case.py`
- **Classes**: `PascalCase`
- **Functions**: `snake_case()`
- **Constants**: `UPPER_SNAKE_CASE`
- **Private members**: `_leading_underscore()`

### Type Annotations

**Required** for all public functions:
```python
def process_chapter(
    chapter: ChapterSource,
    *,
    accumulated: AccumulatedExtraction,
    user_meta: Optional[UserMeta] = None,
) -> CharacterExtractionRecord:
    ...
```

### Pydantic Model Patterns

```python
class MyModel(BaseModel):
    required_field: str
    optional_field: Optional[str] = None
    list_field: List[str] = Field(default_factory=list)
    validated_field: int = Field(ge=0, le=100)

    model_config = ConfigDict(
        frozen=True,  # For immutable models (like ReplayKey)
        extra="forbid",  # Reject unknown fields
    )
```

### Error Handling

- **Ingestion**: Raise descriptive errors, let CLI catch and format
- **Simulation**: Log errors to debug session, continue simulation with degraded state
- **LLM calls**: Retry with exponential backoff (handled in client)

---

## 🎯 Token-Saving Summary

**If you need to work on Dreamdive/Matrix, remember these essentials**:

1. **Core flow**: P0 (config) → P1 (ingest) → P2 (init) → P3 (simulate) → P5 (synthesize)
2. **All models**: `schemas.py`
3. **All prompts**: `src/dreamdive/prompts/`
4. **Main simulation loop**: `simulation/tick_runner.py`
5. **CLI entry**: `cli.py`
6. **Config file**: `dreamdive.toml`

**For specific tasks**:
- **Modifying extraction**: `ingestion/backend.py` + `prompts/p1_ingestion.py`
- **Modifying simulation**: `simulation/tick_runner.py` + `simulation/event_simulator.py`
- **Adding user features**: `user_config.py` + `meta_injection.py` + update prompts
- **Debugging**: Use `--debug` flag, check `debug/events.jsonl` and `debug/llm/`

**Key invariants**:
- State is append-only, replay reconstructs snapshots
- Chapters processed sequentially with accumulated context
- LLMs warned about self-correcting context
- User preferences flow via [META] sections

---

**End of Guide**

This guide should enable future LLM agents to quickly orient themselves in the Dreamdive codebase without reading all files. When in doubt, refer to this guide first, then read specific files as needed.
