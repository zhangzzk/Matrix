# P0.5 Narrative Architecture - Quick Reference

## One-Line Summary

**Design story structure before simulation, creating gravitational waypoints that guide emergence without forcing outcomes.**

---

## Quick Start

```bash
# After ingestion, before initialization
dreamdive design --workspace ./ws \
  --continuation-goal "Your story goal here"
```

---

## Core Concept

| Traditional | Gravity System |
|-------------|----------------|
| "Character X tells secret in Ch 15" | "Secret should be revealed by mid-arc" |
| Fixed timeline | Flexible timing |
| Predetermined | Emergent under pull |
| Cannot deviate | Can override if dynamics demand |

**Gravity = Probability bias, not determinism**

---

## Three Levels

### MACRO: Story Arc
- Overall dramatic question
- 5-8 narrative nodes (waypoints)
- Gravity strengths (0.0-1.0)
- ~30 chapters

### MESO: Chapter Plans
- Purpose per chapter (setup/revelation/confrontation/etc.)
- Which nodes it advances
- Character focus
- Allow deviation

### MICRO: Character Arcs
- Starting → Ending state
- Development milestones
- Internal conflicts
- Trigger conditions

---

## Gravity Strengths

| Value | Meaning | Example |
|-------|---------|---------|
| 1.0 | Inevitable | Protagonist must discover true identity |
| 0.8-0.9 | Very likely | Major revelation by midpoint |
| 0.5-0.7 | Probable | Romantic subplot develops |
| 0.3-0.4 | Possible | Character learns secondary skill |

---

## How Gravity Works

### During Simulation

1. **Event Seeding**: Events advancing toward nodes → +probability
2. **Scene Selection**: Scenes serving chapter purpose → +salience
3. **Milestone Tracking**: Check character development progress
4. **Drift Detection**: If drifting → strengthen gravity

### Override Mechanism

```python
if character_dynamics_strength >= 0.8:
    # Character wins, ignore design
    allow_override = True
```

### Adaptive Pull

```python
drift_factor = compute_drift()
# 1.0 = on track
# 2.0 = drifting → strengthen
# 0.5 = ahead → relax

final_gravity = base_gravity * drift_factor
```

---

## File Structure

```
workspace/
├── extraction.json              # P1
├── narrative_architecture.json  # P0.5 (NEW!)
├── user_meta.json               # P0
└── sessions/
```

---

## CLI Commands

```bash
# Design architecture
dreamdive design --workspace ./ws

# With custom goal
dreamdive design --workspace ./ws \
  --continuation-goal "Explore character's dark transformation"

# JSON output
dreamdive design --workspace ./ws --json
```

---

## Integration Points

### Load at Simulation Start

```python
from dreamdive.simulation_gravity import load_gravity_manager_for_session

gravity_manager = load_gravity_manager_for_session(
    workspace_path=Path("./workspace"),
    current_chapter=1,
)
```

### Apply During Simulation

```python
# P2: Event seeding
adjusted_seeds = gravity_manager.apply_to_event_seeds(potential_seeds)

# P2: Scene selection
adjusted_scenes = gravity_manager.apply_to_scene_selection(potential_scenes)

# P3: Milestone tracking
progress = gravity_manager.track_character_milestone(char_id, char_state)

# P4: Drift detection
drift = gravity_manager.compute_current_drift(sim_state)
```

### Inject into Prompts

```python
from dreamdive.simulation_gravity import inject_gravitational_context_into_prompt

final_prompt = inject_gravitational_context_into_prompt(
    base_prompt=prompt,
    gravity_manager=gravity_manager,
    character_id="character_id",
)
```

---

## Design Patterns

### ✅ Good Design

**Waypoint (gravity)**:
```json
{
  "node_id": "revelation_1",
  "desired_outcome": "Secret revealed to protagonist",
  "estimated_chapter_range": "Ch 15-20",
  "gravity_strength": 0.9,
  "prerequisites": ["Trust established"],
  "unlocks": ["Internal conflict"]
}
```

**Milestone (conditions)**:
```json
{
  "milestone_id": "m1_awakening",
  "description": "First power manifestation",
  "trigger_conditions": ["Life threat", "Emotional peak"],
  "manifests_as": ["Physical change", "Loses control"]
}
```

### ❌ Bad Design

**Script (too specific)**:
```json
{
  "node_id": "bad_example",
  "desired_outcome": "In chapter 15, character X tells character Y the secret during dinner at the Red Dragon Inn, and Y responds with anger",
  // Too rigid! This is a RAIL not GRAVITY
}
```

---

## Best Practices

1. **Design before initialize** - Can't add architecture mid-simulation
2. **Set appropriate gravity** - Match strength to importance
3. **Allow deviation** - Set reasonable thresholds (0.3-0.5)
4. **Match source patterns** - New elements must feel native
5. **Milestones as conditions** - Not scripts
6. **Monitor drift** - Check logs for drift severity

---

## Common Issues

### "No architecture found"
→ Run `design` before `init`

### Simulation ignoring design
→ Increase gravity strengths or check override threshold

### Design feels off-brand
→ Re-run ingestion with more chapters
→ Manually edit `narrative_architecture.json`

### LLM fails during design
→ Check extraction completeness (`jq '.meta, .fate' extraction.json`)
→ Run with `--debug` flag

---

## Key Classes

```python
# Architecture
NarrativeArchitecture(
    story_arc: StoryArcDesign,
    chapter_plans: List[ChapterPlan],
    character_arcs: List[CharacterArcPlan],
    world_expansion: WorldExpansionPlan,
)

# Runtime
GravitationalField(
    active_node_pulls: List[Dict],
    active_milestone_pulls: List[Dict],
    chapter_purpose: str,
    drift_factor: float,
)

# Manager
SimulationGravityManager(
    architecture: NarrativeArchitecture,
    current_chapter: int,
)
```

---

## Gravity Formula

```python
P(event) = base_prob + (gravity_strength × alignment_score × drift_factor)

# Example:
# Base: 0.3 (30% natural chance)
# Gravity: 0.8 (strong pull)
# Alignment: 0.7 (moderately aligned)
# Drift: 1.2 (drifting, strengthen)
# Result: 0.3 + (0.8 × 0.7 × 1.2) = 0.97 (97%!)
```

---

## Workflow

```
┌─────────────┐
│ P1: Ingest  │ Extract patterns from source
└──────┬──────┘
       │
┌──────▼──────┐
│ P0.5: Design│ Create architecture (NEW!)
└──────┬──────┘
       │
┌──────▼──────┐
│   P0: Config│ User preferences
└──────┬──────┘
       │
┌──────▼──────┐
│    Init     │ First snapshot
└──────┬──────┘
       │
┌──────▼──────┐
│ P2-P4: Sim  │ Apply gravity ← Architecture influences here
└──────┬──────┘
       │
┌──────▼──────┐
│ P5: Synth   │ Generate chapters
└─────────────┘
```

---

## Philosophy

> **"Design creates GRAVITY (pulls/fate) not RAILS (scripts/determinism)"**

- **Loyal to source**: Follow learned patterns
- **Creative on top**: Original but native-feeling
- **Emergent paths**: Character dynamics choose route
- **Designed destination**: Gravity pulls toward waypoints
- **Adaptive balance**: System self-corrects

---

## Example Output

```
✓ Architecture designed · The Dragon Awakening Arc · 7 nodes · 3 character arcs · ~30 chapters

Story Arc: The Dragon Awakening Arc
  Question: Can Lu Mingfei accept his dragon heritage?
  Nodes: 7 waypoints (avg gravity: 0.78)
  Characters: 3 main arcs
  Chapters: ~30
```

---

## See Also

- [NARRATIVE_ARCHITECTURE_GUIDE.md](./NARRATIVE_ARCHITECTURE_GUIDE.md) - Complete guide
- [gravitational_guidance.py](./src/dreamdive/gravitational_guidance.py) - Gravity mechanics
- [narrative_architecture.py](./src/dreamdive/narrative_architecture.py) - Data structures
- [architecture_integration.py](./src/dreamdive/architecture_integration.py) - Workflow
- [simulation_gravity.py](./src/dreamdive/simulation_gravity.py) - Runtime integration

---

**Remember**: Architecture provides **structure** + **freedom** = Coherent emergence
