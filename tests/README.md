# Tests & Diagnostic Scripts

This directory contains unit tests and diagnostic utilities for DreamDive.

## Unit Tests

Standard pytest test suite:
- `test_*.py` - Unit tests for various modules
- Run with: `pytest tests/`

## Diagnostic Scripts

Standalone scripts for debugging and analysis:

### Embedding Analysis
- **check_embeddings.py** - Check embedding density in simulation session
- **fix_existing_embeddings.py** - Recompute embeddings with fixed tokenizer
- **test_chinese_tokenizer.py** - Test Chinese tokenization and embedding generation

### LLM Performance
- **diagnose_timing.py** - Analyze LLM latency and performance
- **diagnose_moonshot.py** - Debug Moonshot API issues
- **debug_json_responses.py** - Debug JSON parsing errors
- **quick_moonshot_test.py** - Quick Moonshot API connectivity test

### Batching & Concurrency
- **explain_batching.py** - Explain batching strategy
- **when_batching_helps.py** - Analyze batching performance
- **verify_sequential_safety.py** - Verify sequential dependency handling

## Running Diagnostic Scripts

Most scripts can be run from the project root:

```bash
# Check embeddings in current session
python tests/check_embeddings.py

# Test Chinese tokenizer
python tests/test_chinese_tokenizer.py

# Analyze LLM timing
python tests/diagnose_timing.py
```

Some scripts may require updating file paths if run from different directories.
