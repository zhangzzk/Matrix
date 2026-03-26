# P0.5 Narrative Architecture Guide

## Overview

The **P0.5 Narrative Architecture** system is a hierarchical creative design layer that plans the story **BEFORE** simulation begins. It provides gravitational structure that guides emergence while preserving creative freedom.

### Philosophy

> **Design creates GRAVITY (probability bias) not RAILS (determinism)**

Think of it like planning a TV season:
- **Season arc planned**: What's the big question? Major beats?
- **Episodes outlined**: What does each episode accomplish?
- **Scenes emerge**: Actual dialogue and action unfold dynamically

Key principles:
1. **Loyal to source material**: Follow learned patterns from ingestion
2. **Creative on top**: Original ideas that feel native to source
3. **Gravity not rails**: Waypoints create pull, not predetermined paths
4. **Emergent override**: Character dynamics can resist if strong enough

---

## Workflow Integration

### Complete Pipeline

```
P1 (Ingestion) → P0.5 (Architecture) → P0 (Configure) → Init → P2-P4 (Simulate) → P5 (Synthesize)
     ↓                    ↓                                         ↑
Extract patterns    Design continuation                    Apply gravitational guidance
```

### When to Run P0.5

**After P1 ingestion**, before initialization:

```bash
# 1. Ingest source material
dreamdive ingest source.txt --workspace ./workspace

# 2. Design narrative architecture (NEW!)
dreamdive design --workspace ./workspace \
  --continuation-goal "Explore Lu Mingfei's dragon awakening"

# 3. Initialize simulation
dreamdive init source.txt --workspace ./workspace

# 4. Run simulation (with gravity applied automatically)
dreamdive run --workspace ./workspace --ticks 10
```

---

## Three-Level Hierarchy

### MACRO Level: Season Arc Design

**What it is**: Overall story arc with narrative nodes

**Example**:
```json
{
  "arc_name": "The Dragon Awakening Arc",
  "central_dramatic_question": "Can Lu Mingfei accept his dragon heritage?",
  "estimated_chapter_count": 30,
  "narrative_nodes": [
    {
      "node_id": "node_revelation_1",
      "phase": "midpoint",
      "estimated_chapter_range": "Ch 15-20",
      "desired_outcome": "Lu Mingfei discovers his true bloodline",
      "gravity_strength": 0.9,
      "prerequisites": ["Trust established with mentor"],
      "unlocks": ["Internal conflict intensifies"]
    }
  ]
}
```

**Key concepts**:
- **Narrative nodes**: Waypoints that create gravitational pull
- **Gravity strength**: 0.0-1.0 (how inevitable is this?)
  - `1.0` = Must happen for story to work
  - `0.7` = Strong pull (probable but can be delayed)
  - `0.5` = Moderate pull (alternate paths exist)
  - `0.3` = Weak pull (nice if it happens, not essential)

### MESO Level: Chapter Plans

**What it is**: High-level design per chapter (not scripts!)

**Example**:
```json
{
  "chapter_number": 15,
  "purpose": "revelation",
  "advances_toward": ["node_revelation_1"],
  "primary_pov_characters": ["lu_mingfei"],
  "key_character_moments": {
    "lu_mingfei": "Confronts the truth about his heritage"
  },
  "target_emotional_arc": "Denial → Shock → Dawning acceptance",
  "allow_deviation": true,
  "deviation_threshold": 0.3
}
```

**Chapter purposes**:
- `setup`: Establish situation
- `development`: Advance relationships/goals
- `revelation`: Reveal information
- `confrontation`: Direct conflict
- `transition`: Bridge between beats
- `reflection`: Character processing

### MICRO Level: Character Development Trajectories

**What it is**: Growth journey for each main character

**Example**:
```json
{
  "character_id": "lu_mingfei",
  "arc_starting_state": "Reluctant, denying his potential",
  "arc_ending_state": "Accepting responsibility as a hybrid",
  "development_trajectory": "Denial → Resistance → Acceptance → Mastery",
  "milestones": [
    {
      "milestone_id": "m1_first_awakening",
      "description": "First involuntary use of dragon abilities",
      "estimated_timing": "Early arc (Ch 5-8)",
      "trigger_conditions": ["Life-threatening danger", "Emotional peak"],
      "internal_change": "Denial → Can't ignore anymore",
      "manifests_as": ["Eyes turn golden", "Speaks dragon language"]
    }
  ],
  "central_internal_conflict": "Human identity vs. Dragon nature"
}
```

---

## Gravitational Mechanics

### How Gravity Works

During simulation, designed elements create **probability biases**:

1. **Event Seeding (P2)**: Events advancing toward active nodes get probability boost
2. **Scene Selection (P2)**: Scenes serving chapter purpose get salience boost
3. **Milestone Tracking (P3)**: Check if characters progressing as designed
4. **Drift Detection (P4)**: If simulation drifting too far, strengthen gravity

### Gravity vs. Rails

| Aspect | RAILS (❌ Bad) | GRAVITY (✅ Good) |
|--------|--------------|----------------|
| Design | "In chapter 15, Lu Mingfei tells Caesar the secret" | "By mid-arc, the secret should be revealed" |
| Timing | Fixed | Flexible |
| Path | Predetermined | Emergent |
| Override | Cannot deviate | Can deviate if dynamics demand |
| Control | Deterministic | Probabilistic |

### Override Mechanism

Character dynamics can **override gravity** if strong enough:

```python
if character_dynamics_strength >= 0.8:
    # Character logic wins, ignore designed arc
    allow_deviation = True
```

**Example**: If Lu Mingfei's personality strongly resists confrontation, he might delay a planned revelation even if gravity pulls toward it.

### Drift Response

If simulation drifts from design:

```python
drift_factor = compute_drift_severity()
# 1.0 = on track
# 2.0 = significant drift → strengthen gravity
# 0.5 = ahead of plan → relax gravity

gravity_strength = base_gravity * drift_factor
```

This creates **adaptive pull**: Story naturally corrects back toward designed arc.

---

## Architecture Design Process

### 1. Story Arc Design

**Prompt**: `build_story_arc_design_prompt()`

**Inputs**:
- Source material summary
- Meta-layer (themes, patterns, style)
- Fate layer (existing arcs, conflicts)
- User configuration

**Output**: `StoryArcDesign` with:
- Central dramatic question
- 5-8 narrative nodes with gravity strengths
- Creative freedom bounds
- Must-respect constraints

**Agent task**: "If the original author continued this story, how would they structure it?"

### 2. Character Arc Design

**Prompt**: `build_character_arc_design_prompt()`

**Inputs**:
- Character summary (traits, background, goals)
- Story arc (to align character development)
- Meta-layer (character construction patterns)

**Output**: `CharacterArcPlan` with:
- Starting → Ending state
- Development milestones
- Internal conflicts
- Traits to preserve vs. evolve

**Agent task**: "Design growth that feels psychologically realistic while serving the story."

### 3. World Expansion Design

**Prompt**: `build_world_expansion_design_prompt()`

**Inputs**:
- Story arc (to determine what's needed)
- Existing world and characters
- Meta-layer (world-building patterns, character archetypes)

**Output**: `WorldExpansionPlan` with:
- New characters (if needed)
- New locations (if needed)
- New plot threads (if needed)

**Agent task**: "Create elements that feel **native to source** (readers should think: 'this could be from the original')"

### 4. Chapter Roadmap Design

**Prompt**: `build_chapter_roadmap_prompt()`

**Inputs**:
- Story arc (narrative nodes)
- Character arcs (development needs)
- Estimated chapter count

**Output**: `ChapterPlan[]` with:
- Purpose per chapter
- Which nodes it advances
- Character focus
- Emotional arc

**Agent task**: "Create rough guidance, not scripts. Allow deviation."

---

## Simulation Integration

### Loading Architecture

At simulation start:

```python
from dreamdive.simulation_gravity import load_gravity_manager_for_session

# Load architecture from workspace
gravity_manager = load_gravity_manager_for_session(
    workspace_path=Path("./workspace"),
    current_chapter=1,
)

if gravity_manager:
    print("Gravity enabled!")
else:
    print("Running without architecture")
```

### Applying Gravity During Simulation

#### P2: Event Seeding

```python
# After collision detection generates potential events
potential_seeds = [...]  # From collision detection

if gravity_manager:
    # Apply gravitational bias
    adjusted_seeds = gravity_manager.apply_to_event_seeds(potential_seeds)

    # Now select events from adjusted_seeds
    # Events advancing toward nodes have boosted probability
```

**Effect**: Events like "confrontation with mentor" get higher probability if there's an active node for "revelation through mentor."

#### P2: Scene Selection

```python
# Before choosing which scene to render
potential_scenes = [...]  # Scene candidates

if gravity_manager:
    # Apply chapter purpose bias
    adjusted_scenes = gravity_manager.apply_to_scene_selection(potential_scenes)

    # Scenes serving chapter purpose get salience boost
```

**Effect**: If chapter purpose is "revelation," revelation-type scenes become more likely to be selected.

#### P3: Memory Consolidation

```python
# After updating character state
character_state = {...}  # Current state

if gravity_manager:
    # Track milestone progress
    progress = gravity_manager.track_character_milestone(
        character_id="lu_mingfei",
        character_state=character_state,
    )

    # Log which milestones reached, which blocked
```

**Effect**: System knows if character development is on-track or drifting.

#### P4: Narrative Arc Updates

```python
# Check overall drift
if gravity_manager:
    drift = gravity_manager.compute_current_drift(simulation_state)

    # Update gravitational field for next chapter
    gravity_manager.update_for_chapter(
        chapter_number=next_chapter,
        tick=current_tick,
        simulation_state=simulation_state,
    )
```

**Effect**: Gravity automatically strengthens if simulation drifting.

### Injecting Context into Prompts

```python
from dreamdive.simulation_gravity import inject_gravitational_context_into_prompt

# Before calling agent
base_prompt = "Your character is in this situation..."

# Add gravitational hints
final_prompt = inject_gravitational_context_into_prompt(
    base_prompt=base_prompt,
    gravity_manager=gravity_manager,
    character_id="lu_mingfei",
)

# final_prompt now includes subtle narrative context:
# "## Narrative Context
#  This chapter serves a **Revelation** function...
#
#  ## Character Development Context
#  This character is approaching: First awakening of dragon powers
#  _Your choices may naturally lead toward or away from this development._"
```

**Effect**: Agents aware of narrative direction without being forced.

---

## Data Structures

### NarrativeArchitecture

Complete architecture stored as JSON in workspace:

```python
architecture = NarrativeArchitecture(
    architecture_id="arch_session_001",
    created_for_session="session_001",

    # Macro
    story_arc=StoryArcDesign(...),

    # Meso
    chapter_plans=[ChapterPlan(...)],

    # Micro
    character_arcs=[CharacterArcPlan(...)],

    # Expansion
    world_expansion=WorldExpansionPlan(...),

    # Parameters
    default_gravity_strength=0.7,
    allow_emergent_override=True,
    override_threshold=0.8,
)
```

### GravitationalField

Active at runtime during simulation:

```python
field = GravitationalField(
    current_chapter=15,
    current_tick="ch15_t3",

    # Active pulls
    active_node_pulls=[
        {
            "node_id": "node_revelation_1",
            "desired_outcome": "Secret revealed",
            "gravity_strength": 0.9,
        }
    ],

    active_milestone_pulls=[
        {
            "milestone_id": "m1_first_awakening",
            "description": "First dragon ability manifestation",
        }
    ],

    # Chapter guidance
    chapter_purpose="revelation",
    chapter_emotional_target="Shock → Acceptance",

    # Drift modulation
    drift_factor=1.0,  # On track
)
```

---

## CLI Reference

### design Command

```bash
dreamdive design --workspace ./workspace [OPTIONS]
```

**Options**:
- `--workspace PATH` (required): Directory with P1 extraction
- `--continuation-goal TEXT`: User's story goal (e.g., "Explore dragon awakening")
- `--output PATH`: Save location (default: `workspace/narrative_architecture.json`)
- `--json`: Output machine-readable JSON instead of summary

**Example**:
```bash
dreamdive design \
  --workspace ./dragon_raja_workspace \
  --continuation-goal "Explore Lu Mingfei's acceptance of his hybrid nature and conflict with the dragon kings"
```

**Output**:
```
⠋ Designing narrative architecture...
✓ Architecture designed · The Dragon Awakening Arc · 7 nodes · 3 character arcs · ~30 chapters

✓ Narrative architecture saved to: ./dragon_raja_workspace/narrative_architecture.json

Story Arc: The Dragon Awakening Arc
  Question: Can Lu Mingfei accept his dragon heritage while preserving his humanity?
  Theme: Identity, duality, accepting destiny
  Chapters: ~30

Narrative Nodes: 7
  - node_setup_1: Establish Lu Mingfei's ordinary world (gravity: 0.8)
  - node_catalyst_1: First encounter with dragon threat (gravity: 0.9)
  - node_revelation_1: Discover true bloodline (gravity: 0.9)
  ... and 4 more

Character Arcs: 3
  - lu_mingfei: Reluctant outsider → Accepting hybrid
  - caesar_gattuso: Confident leader → Challenged by Lu's potential
  - chu_zihang: Stoic warrior → Opens up through Lu's influence
```

---

## Best Practices

### 1. Design Before Initialize

Always run P0.5 **after ingestion**, **before initialization**:

```bash
# ✅ Correct order
dreamdive ingest source.txt --workspace ./ws
dreamdive design --workspace ./ws
dreamdive init source.txt --workspace ./ws

# ❌ Wrong - can't design after simulation started
dreamdive init source.txt --workspace ./ws
dreamdive design --workspace ./ws  # Too late!
```

### 2. Set Appropriate Gravity Strengths

Match gravity to narrative importance:

- **1.0**: Story-critical (plot breaks without it)
  - "Protagonist must discover their true identity"
- **0.8-0.9**: Very important (strong pull but slight flexibility)
  - "Major revelation should happen by midpoint"
- **0.5-0.7**: Moderate importance (helpful but alternatives exist)
  - "Romantic subplot should develop"
- **0.3-0.4**: Nice to have (enriches but not essential)
  - "Character learns a secondary skill"

### 3. Allow Deviation When Appropriate

Set `allow_deviation: true` and reasonable thresholds:

```json
{
  "allow_deviation": true,
  "deviation_threshold": 0.3
}
```

**When to be strict** (`deviation_threshold: 0.1`):
- Plot-critical chapters
- Major reveals
- Climactic confrontations

**When to be flexible** (`deviation_threshold: 0.5`):
- Character development chapters
- Transitional chapters
- Setup chapters

### 4. Design Milestones as Conditions, Not Scripts

**❌ Too specific** (script):
```json
{
  "milestone_id": "m1",
  "description": "In chapter 12, during fight with Herzog, Lu Mingfei's eyes turn golden and he speaks ancient dragon language, shocking everyone present"
}
```

**✅ Good** (conditions):
```json
{
  "milestone_id": "m1_first_awakening",
  "description": "First involuntary manifestation of dragon abilities",
  "estimated_timing": "Early-mid arc",
  "trigger_conditions": [
    "Life-threatening situation",
    "Emotional peak (rage or desperation)",
    "No conscious control"
  ],
  "manifests_as": [
    "Physical change (eyes, voice, aura)",
    "Speaks dragon language without knowing it",
    "Surprised by own power"
  ]
}
```

### 5. Match Source Material Patterns

New elements must feel native:

```json
{
  "new_characters": [
    {
      "name": "Chen Wenwen",  // ✅ Matches Chinese naming
      "archetype_from_source": "Mysterious mentor type",  // ✅ Follows pattern
      "matches_source_patterns": [
        "Tied to dragon history",
        "Dual identity",
        "Teaches through cryptic hints"
      ]
    }
  ]
}
```

**Don't**:
- Create characters with names that don't match source conventions
- Introduce plot elements that violate world rules
- Use tones/themes foreign to source

---

## Troubleshooting

### "No architecture found, simulation will run without gravity"

**Cause**: No `narrative_architecture.json` in workspace

**Solution**: Run `dreamdive design` before initialization

### Simulation ignoring designed arc

**Possible causes**:
1. **Gravity too weak**: Increase `gravity_strength` for critical nodes
2. **Character dynamics too strong**: Override threshold too low
3. **Drift not tracked**: Ensure `compute_drift_severity()` called regularly

**Solution**: Check gravity manager logs, adjust strengths/thresholds

### Architecture design fails during LLM call

**Possible causes**:
1. **Extraction incomplete**: Missing meta-layer or fate-layer
2. **LLM timeout**: Architecture design is LLM-intensive
3. **Invalid JSON response**: LLM returned malformed data

**Solution**:
```bash
# Check extraction completeness
jq '.meta, .fate' workspace/extraction.json

# Run with debug mode
dreamdive design --workspace ./ws --debug

# Check debug output
cat debug_*/llm_attempts/*.json
```

### Generated architecture feels off-brand

**Possible causes**:
1. **Meta-layer insufficient**: Ingestion didn't capture style well
2. **Continuation goal conflicts with source**

**Solution**:
- Re-run ingestion with more chapters
- Adjust `--continuation-goal` to align with source themes
- Manually edit `narrative_architecture.json` (it's just JSON!)

---

## Advanced Usage

### Manual Architecture Editing

Architecture is stored as JSON - you can edit directly:

```bash
# Open in editor
vim workspace/narrative_architecture.json

# Or programmatically
python
>>> import json
>>> from pathlib import Path
>>> arch_file = Path("workspace/narrative_architecture.json")
>>> arch = json.loads(arch_file.read_text())
>>> arch['story_arc']['narrative_nodes'][0]['gravity_strength'] = 0.95
>>> arch_file.write_text(json.dumps(arch, indent=2, ensure_ascii=False))
```

### Branching with Different Architectures

Create counterfactual branches with modified architecture:

```bash
# Original simulation
dreamdive design --workspace ./ws_original

# Branch with different goal
dreamdive design --workspace ./ws_branch \
  --continuation-goal "Lu Mingfei rejects dragon heritage and stays human"
```

### Disabling Gravity Temporarily

```python
# In custom simulation code
gravity_manager = None  # Disable gravity for this session
# Simulation proceeds purely emergently
```

---

## Integration with Existing Systems

### With Meta-Layer (P1)

Architecture design **consumes** meta-layer:

```python
# Meta-layer informs design
themes = meta_layer.themes  # Used in arc design
char_construction = meta_layer.design_tendencies.character_construction
# Used in world expansion

# Architecture extends meta
# Meta = "How author writes"
# Architecture = "What to write about"
```

### With Fate Layer (P1.6-P1.7)

Architecture design **extends** fate layer:

```python
# Fate layer from source
extracted_fate.central_question  # Used in arc design
extracted_fate.character_arcs    # Extended in character arc design

# Architecture adds future
agent_designed_fate.arc_extensions      # New arcs
agent_designed_fate.new_hidden_truths   # New secrets
```

### With User Configuration (P0)

User config **guides** architecture:

```python
# User preferences influence design
user_meta.focus_characters  # Which characters get arcs
user_meta.divergence_seeds  # Story branch points
user_meta.tone             # Overall mood

# Architecture respects user choices
```

### With Synthesis (P5)

Architecture doesn't directly affect synthesis, but:

```python
# Simulation influenced by architecture → better events
# Better events → better synthesis

# Indirect effect:
# More coherent story → more on-brand chapters
```

---

## File Locations

```
workspace/
├── extraction.json              # P1 output
├── user_meta.json               # P0 output
├── narrative_architecture.json  # P0.5 output (NEW!)
└── sessions/
    └── session_001/
        ├── snapshots/
        └── ...
```

**narrative_architecture.json** contains:
- Complete `NarrativeArchitecture` object
- All story arc nodes
- All character arc plans
- All chapter plans
- World expansion plans

Size: ~50-200 KB depending on complexity

---

## Theory: Why Gravity Works

### The Creativity Paradox

Pure emergence → Incoherent stories
Pure planning → Lifeless, deterministic stories

**Solution**: Emergence **under constraints**

### Gravity as Soft Constraints

Traditional constraints:
- Hard rules: "Character MUST do X"
- All-or-nothing

Gravitational constraints:
- Probability biases: "Character LIKELY to do X"
- Graduated influence

### Mathematical Model

```python
P(event) = base_probability + (gravity_strength * alignment_score * drift_factor)

# Example:
# Base: 0.3 (30% chance naturally)
# Gravity: 0.8 (strong pull toward this)
# Alignment: 0.7 (event moderately advances node)
# Drift: 1.2 (simulation drifting, strengthen pull)
#
# Result: 0.3 + (0.8 * 0.7 * 1.2) = 0.97 (97% chance!)
```

### Adaptive System

System self-corrects:
1. On track → gravity relaxes → more freedom
2. Drifting → gravity strengthens → pull back
3. Dynamic balance between plan and emergence

---

## Future Enhancements

Potential improvements:

1. **Multi-arc support**: Parallel story arcs with different gravity fields
2. **Dynamic node generation**: Create new nodes mid-simulation based on emergent events
3. **Player choice integration**: User decisions create counter-gravity
4. **Gravity visualization**: Show pull strengths in web UI
5. **Architecture templates**: Pre-built arc structures for common genres

---

## Summary

**P0.5 Narrative Architecture** provides:

✅ **Structure**: TV-season planning model
✅ **Guidance**: Gravitational pull toward designed waypoints
✅ **Freedom**: Character dynamics can override
✅ **Adaptation**: Self-correcting drift response
✅ **Fidelity**: Loyal to source material patterns
✅ **Creativity**: Original content that feels native

**Result**: Coherent, compelling stories that feel both planned and alive.

---

## Quick Start Checklist

- [ ] Complete P1 ingestion
- [ ] Run `dreamdive design`
- [ ] Review generated architecture (edit if needed)
- [ ] Initialize simulation (gravity auto-loaded)
- [ ] Monitor gravity application in logs
- [ ] Check drift metrics periodically
- [ ] Enjoy emergent storytelling with narrative coherence!

---

**Next**: See [NARRATIVE_ARCHITECTURE_EXAMPLES.md](./NARRATIVE_ARCHITECTURE_EXAMPLES.md) for detailed examples and [NARRATIVE_ARCHITECTURE_QUICKREF.md](./NARRATIVE_ARCHITECTURE_QUICKREF.md) for quick reference.
