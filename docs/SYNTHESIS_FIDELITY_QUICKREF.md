# Synthesis Fidelity - Quick Reference

## Core Principle

**Synthesis = RENDERING (not CREATING)**

Think: Cinematographer (not screenwriter)
- ✅ Follow the screenplay (simulation events) exactly
- ✅ Film in director's style (original author's voice)
- ❌ Don't change the plot

## Two Requirements

### 1. Follow Simulation Exactly

**Content comes from simulation, not invention.**

✅ **Allowed**:
- Add sensory details
- Invent internal monologue (if consistent with character state)
- Add brief transitions

❌ **Forbidden**:
- Change outcomes
- Invent new plot points
- Alter character actions
- Add dialogue not from simulation

### 2. Match Original Style

**Style comes from original author.**

✅ Match:
- Sentence rhythm
- Descriptive techniques
- Narrative voice
- Metaphor patterns

## Quick Integration

### Basic Usage

```python
from dreamdive.prompts.p5_synthesis_fidelity import build_fidelity_first_synthesis_prompt

# Collect beat details from simulation
beat_details_by_event = {
    "evt_001": [
        {"character_id": "路明非", "dialogue": "真烦.", "physical_action": "按下开关"},
    ],
}

state_changes_by_event = {
    "evt_001": [
        {"character_id": "路明非", "dimension": "location", "to_value": "passage"},
    ],
}

# Build prompt
prompt = build_fidelity_first_synthesis_prompt(
    event_window=window,
    novel_meta=meta,
    user_meta=user_meta,
    beat_details_by_event=beat_details_by_event,
    state_changes_by_event=state_changes_by_event,
)

# Generate
chapter = llm_client.generate(prompt)
```

### With Validation

```python
from dreamdive.prompts.p5_synthesis_fidelity import build_synthesis_validation_prompt

# Validate after generation
validation_prompt = build_synthesis_validation_prompt(
    chapter_text=chapter,
    grounded_events=grounded_events,
    constraints=constraints,
)

result = llm_client.generate(validation_prompt)
# Returns fidelity_score, missing_facts, contradictions
```

## What Gets Grounded

Events are enhanced with **mandatory facts**:

```python
GroundedEventSummary(
    event_id="evt_001",
    description="Lu Mingfei activates mechanism",
    outcome_summary="Passage opens",
    mandatory_facts=[
        "Lu Mingfei pressed the switch",  # 🔴 MUST appear
        "Passage state → open",  # 🔴 MUST appear
    ],
    canonical_dialogue=[
        {"speaker": "诺诺", "line": "准备好了吗?"},  # EXACT wording
    ],
)
```

## Prompt Structure

1. **Grounded Events** (WHAT to write) - Simulation facts
2. **Style Template** (HOW to write) - Original author patterns
3. **Synthesis Instructions** (length, density, etc.)

## Constraints Configuration

```python
from dreamdive.synthesis_fidelity import SynthesisConstraints

# STRICT (highest fidelity)
constraints = SynthesisConstraints(
    allow_internal_monologue_invention=False,
    allow_dialogue_paraphrasing=False,
    allow_transitional_scenes=False,
)

# BALANCED (recommended)
constraints = SynthesisConstraints(
    allow_internal_monologue_invention=True,  # If consistent
    allow_dialogue_paraphrasing=False,
    allow_transitional_scenes=True,  # Brief only
)
```

## Extracting Beat Details

### From Scene Resolution

```python
beat_details_by_event = {}
for event in events:
    if event.resolution_mode == "scene":
        beats = []
        for agent_beat in event.agent_beats:
            beats.append({
                "character_id": agent_beat.character_id,
                "dialogue": agent_beat.external.dialogue,
                "physical_action": agent_beat.external.physical_action,
            })
        beat_details_by_event[event.event_id] = beats
```

### From Background Events

```python
# Background events have narrative_summary
# Use that as the mandatory fact
```

## Common Issues

| Problem | Cause | Solution |
|---------|-------|----------|
| Generated chapter invents plot | No grounding | Pass `beat_details_by_event` |
| Wrong style | No style examples | Extract more from meta-layer |
| Missing dialogue | Not marked mandatory | Include in `canonical_dialogue` |
| Changed outcomes | Weak constraints | Use stricter `SynthesisConstraints` |

## Validation

Check fidelity score:

```json
{
    "fidelity_score": 0.95,  // >0.85 = good
    "missing_facts": [],
    "contradictions": [],
    "invented_content": [],
}
```

## Files

- [src/dreamdive/synthesis_fidelity.py](src/dreamdive/synthesis_fidelity.py) - Core system
- [src/dreamdive/prompts/p5_synthesis_fidelity.py](src/dreamdive/prompts/p5_synthesis_fidelity.py) - Prompts
- [SYNTHESIS_FIDELITY_GUIDE.md](SYNTHESIS_FIDELITY_GUIDE.md) - Full guide

## Summary

**Before**: LLM invents plot, changes outcomes, loses simulation continuity
**After**: LLM renders simulation faithfully in original style

**Key**: Make simulation facts explicit and enforceable
