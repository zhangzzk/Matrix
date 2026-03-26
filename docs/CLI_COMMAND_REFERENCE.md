# Dreamdive CLI Command Reference

Quick reference for all Dreamdive CLI commands.

---

## Complete Workflow

```bash
# 1. Ingest source material
dreamdive ingest source.txt --workspace ./workspace

# 2. Configure user preferences (optional)
dreamdive configure --workspace ./workspace

# 3. Design narrative architecture
dreamdive design --workspace ./workspace \
  --continuation-goal "Your story goal"

# 4. Initialize simulation
dreamdive init source.txt --workspace ./workspace \
  --chapter-id chapter_001

# 5. Run simulation
dreamdive run --workspace ./workspace --ticks 10

# 6. Synthesize chapters
dreamdive synthesize --workspace ./workspace
```

---

## Command List

### P1: Ingestion

**`dreamdive ingest`** - Extract world, characters, and meta-information

```bash
dreamdive ingest source.txt --workspace ./workspace

# Options:
#   --skip-structural-scan
#   --skip-meta-layer
#   --skip-entities
#   --skip-fate-layer
#   --rerun-structural-scan
#   --rerun-chapters
#   --max-workers N
```

### P0: Configuration

**`dreamdive configure`** - Set user preferences for simulation

```bash
dreamdive configure --workspace ./workspace

# Interactive prompt for:
#   - Tone preferences
#   - Focus characters
#   - Divergence seeds
#   - Chapter format
```

### P0.5: Architecture Design

**`dreamdive design`** - Design narrative architecture before simulation

```bash
dreamdive design --workspace ./workspace \
  --continuation-goal "Explore character's transformation"

# Options:
#   --workspace PATH (required)
#   --continuation-goal TEXT
#   --output PATH
```

**Output**: `narrative_architecture.json` with:
- Story arc with narrative nodes
- Character development trajectories
- Chapter roadmap
- World expansion plans

### P2: Initialization

**`dreamdive init`** - Initialize simulation session from a chapter

```bash
dreamdive init source.txt --workspace ./workspace \
  --chapter-id chapter_001

# Options:
#   --workspace PATH
#   --chapter-id ID (required)
#   --tick-label TEXT
#   --timeline-index N
#   --character-id ID (can repeat)
#   --session-id ID
#   --overwrite
#   --max-workers N
```

### P2-P4: Simulation

**`dreamdive tick`** - Advance simulation by one tick

```bash
dreamdive tick --workspace ./workspace --session-id session_001

# Options:
#   --workspace PATH
#   --session-id ID
#   --overwrite
#   --tick-max-events N
#   --max-workers N
```

**`dreamdive run`** - Advance simulation by multiple ticks

```bash
dreamdive run --workspace ./workspace --ticks 10

# Options:
#   --workspace PATH
#   --ticks N (required)
#   --session-id ID
#   --overwrite
#   --tick-max-events N
#   --max-workers N
```

**`dreamdive background`** - Run background maintenance jobs

```bash
dreamdive background --workspace ./workspace

# Options:
#   --workspace PATH
#   --max-jobs N
#   --session-id ID
#   --overwrite
```

### P5: Synthesis

**`dreamdive synthesize`** - Generate novel chapters from simulation

```bash
dreamdive synthesize --workspace ./workspace --session-id session_001

# Options:
#   --workspace PATH
#   --session-id ID
#   --start-tick N (default: 0)
#   --end-tick N
#   --output-dir PATH
#   --ticks-per-chapter N (0 = auto-detect)
```

### Utilities

**`dreamdive branch`** - Create counterfactual branch

```bash
dreamdive branch --workspace ./workspace \
  --output-workspace ./workspace_branch \
  --timeline-index 10

# Options:
#   --workspace PATH
#   --output-workspace PATH
#   --session-id ID
#   --output-session-id ID
#   --timeline-index N (or --before-event-id)
#   --overwrite
```

**`dreamdive migrate`** - Apply database schema migrations

```bash
dreamdive migrate --database-url postgresql://...
```

**`dreamdive visualize`** - Start web visualization server

```bash
dreamdive visualize --workspace ./workspace

# Options:
#   --workspace PATH
#   --session-id ID
#   --host HOST (default: localhost)
#   --port PORT (default: 8000)
```

---

## Common Patterns

### Complete New Simulation

```bash
# Start from scratch
dreamdive ingest novel.txt --workspace ./work
dreamdive design --workspace ./work --continuation-goal "Continue the story"
dreamdive init novel.txt --workspace ./work --chapter-id ch_001
dreamdive run --workspace ./work --ticks 50
dreamdive synthesize --workspace ./work
```

### Resume Existing Simulation

```bash
# Continue from last tick
dreamdive run --workspace ./work --ticks 10
```

### Counterfactual Branch

```bash
# Branch from tick 20, try different outcome
dreamdive branch --workspace ./work \
  --output-workspace ./work_alt \
  --timeline-index 20

dreamdive run --workspace ./work_alt --ticks 10
```

### Quality Check

```bash
# Visualize to check story coherence
dreamdive visualize --workspace ./work

# Open browser to http://localhost:8000
```

---

## Global Options

Available for all commands:

```bash
--debug              # Enable debug mode
--debug-dir PATH     # Custom debug output directory
--config PATH        # Custom config file
--profile PROFILE    # LLM profile to use
--json               # Machine-readable JSON output
```

---

## Configuration Files

### dreamdive.toml

Default configuration (place in working directory or `~/.config/dreamdive/`):

```toml
[cli]
workspace = "./workspace"
source = "./novel.txt"

[simulation]
tick_max_events = 5
max_workers = 4

[llm]
primary_provider = "openai"
primary_model = "gpt-4"
```

### Environment Variables

```bash
OPENAI_API_KEY=...          # OpenAI API key
ANTHROPIC_API_KEY=...       # Anthropic API key
DREAMDIVE_CONFIG=...        # Path to config file
DREAMDIVE_WORKSPACE=...     # Default workspace directory
```

---

## Command Aliases (Old → New)

For backward compatibility reference:

| Old Command | New Command | Status |
|-------------|-------------|--------|
| `init-snapshot` | `init` | ✅ Use `init` |
| `design-architecture` | `design` | ✅ Use `design` |

---

## Typical Session

```bash
# 1. Ingest novel (one time)
dreamdive ingest dragon_raja.txt --workspace ./dragon_ws

# 2. Design continuation (one time per story)
dreamdive design --workspace ./dragon_ws \
  --continuation-goal "Explore Lu Mingfei's dragon awakening"

# 3. Initialize from a chapter
dreamdive init dragon_raja.txt --workspace ./dragon_ws \
  --chapter-id chapter_050

# 4. Simulate (iterative)
dreamdive run --workspace ./dragon_ws --ticks 20

# 5. Synthesize chapters (iterative)
dreamdive synthesize --workspace ./dragon_ws

# 6. Review results
dreamdive visualize --workspace ./dragon_ws
```

---

## Help

Get help for any command:

```bash
dreamdive --help
dreamdive ingest --help
dreamdive init --help
dreamdive design --help
```

---

## Exit Codes

- `0`: Success
- `1`: Error (check stderr for details)
- `2`: Invalid arguments

---

**Updated**: March 2026 with simplified command names
