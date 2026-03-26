# Prompt Quality Improvements - Quick Reference

## Problem Summary

1. **Repetitive catchphrases**: "真烦" and "麦乐鸡" overused in every scene
2. **Too short**: Chapters only 500-1000 words instead of 3000+
3. **No titles**: Missing poetic chapter headings
4. **Poor pacing**: Feels like summary, not full dramatization

## Solution: 3 New Modules

### 1. Context Salience ([context_salience.py](src/dreamdive/context_salience.py))

Prevents overuse of signature phrases by labeling them as RARE.

```python
from dreamdive.context_salience import apply_signature_phrase_filtering

# Filter based on recent usage
filtered_context = apply_signature_phrase_filtering(
    character_id=char_id,
    context_packet=packet,
    recent_output_history=last_3_chapters,
)
```

### 2. Enhanced Synthesis ([enhanced_synthesis.py](src/dreamdive/enhanced_synthesis.py))

Extracts target length, pacing, and title style from meta-layer.

```python
from dreamdive.enhanced_synthesis import extract_synthesis_meta_context

meta_context = extract_synthesis_meta_context(meta_layer_dict)
# Automatically knows: 3000 words, high density, poetic titles
```

### 3. Enhanced Prompts ([p5_synthesis_enhanced.py](src/dreamdive/prompts/p5_synthesis_enhanced.py))

Combines everything into improved synthesis prompts.

```python
from dreamdive.prompts.p5_synthesis_enhanced import build_enhanced_chapter_synthesis_prompt

prompt = build_enhanced_chapter_synthesis_prompt(
    event_window=window,
    novel_meta=meta,
    user_meta=user_meta,
    recent_chapter_outputs=[ch1, ch2, ch3],  # For filtering
)
```

## Quick Integration

### Replace Old Synthesis

**Before**:
```python
from dreamdive.prompts.p5_synthesis import build_chapter_synthesis_prompt
prompt = build_chapter_synthesis_prompt(...)
```

**After**:
```python
from dreamdive.prompts.p5_synthesis_enhanced import build_enhanced_chapter_synthesis_prompt

recent_chapters = []
for window in windows:
    prompt = build_enhanced_chapter_synthesis_prompt(
        event_window=window,
        novel_meta=meta,
        user_meta=user_meta,
        chapter_number=i,
        recent_chapter_outputs=recent_chapters[-3:],  # Track last 3
    )
    chapter = llm.generate(prompt)
    recent_chapters.append(chapter)
```

### Add to Agent Prompts

For P2 character agents:

```python
from dreamdive.context_salience import (
    convert_legacy_context_to_salience_aware,
    format_salience_aware_context,
)

# Convert to salience-aware
packet = convert_legacy_context_to_salience_aware(
    legacy_identity=char.identity.model_dump(),
    meta_layer=meta_dict,
)

# Format with warnings
context_text = format_salience_aware_context(packet)
# Includes: "⚠️ USE SPARINGLY" warnings for signatures
```

## Expected Results

### Before
- 500 words
- "真烦" used 4x per chapter
- No title
- Feels like summary

### After
- 3000 words
- "真烦" used 0-1x per chapter (only when appropriate)
- Poetic title: "第六十七幕 废墟中的麦辣鸡腿堡"
- Full dramatization with scenes

## Files Created

1. [src/dreamdive/context_salience.py](src/dreamdive/context_salience.py) - Salience system
2. [src/dreamdive/enhanced_synthesis.py](src/dreamdive/enhanced_synthesis.py) - Meta extraction
3. [src/dreamdive/prompts/p5_synthesis_enhanced.py](src/dreamdive/prompts/p5_synthesis_enhanced.py) - New prompts
4. [PROMPT_QUALITY_IMPROVEMENTS.md](PROMPT_QUALITY_IMPROVEMENTS.md) - Full guide

## Configuration

### Adjust Target Length

```python
from dreamdive.enhanced_synthesis import ChapterDensityMetrics

custom = ChapterDensityMetrics(
    average_word_count=2000,  # Shorter
    description_density="low",  # Less detail
)
synthesis_meta.density_metrics = custom
```

### Add Custom Catchphrases

```python
from dreamdive.context_salience import ContextElement, UsageFrequency, COMMON_SIGNATURE_GUIDANCE

COMMON_SIGNATURE_GUIDANCE["你的口头禅"] = ContextElement(
    content="Your catchphrase",
    usage_frequency=UsageFrequency.RARE,
    usage_guidance="Only when dramatically appropriate",
)
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Still too short | Increase `max_tokens` to 10_000 in [p5_synthesis_enhanced.py](src/dreamdive/prompts/p5_synthesis_enhanced.py#L109) |
| Still repetitive | Pass `recent_chapter_outputs` parameter |
| Wrong title style | Pass `source_heading_examples` from ingestion |
| Too slow | Normal - 3x longer output takes 2x time |

## Next Steps

1. Test with your Dragon Raja simulation
2. Compare old vs. new chapters side-by-side
3. Adjust density metrics if needed
4. Integrate into main CLI workflow

Read [PROMPT_QUALITY_IMPROVEMENTS.md](PROMPT_QUALITY_IMPROVEMENTS.md) for complete details.
