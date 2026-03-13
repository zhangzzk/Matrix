# Dreamdive

This repository bootstraps the foundation of the novel-grounded multi-agent
simulation engine described in Notion.

The current implementation focuses on the first layer the guide says everything
else depends on:

- project structure and configuration
- immutable log schemas
- replay utilities for deriving state at any snapshot
- in-memory repository interfaces for append-only state writes
- lazy PostgreSQL repository adapters and migration runner for the production path
- snapshot bootstrap assembly
- tests for replay and diff integrity

## Layout

```text
src/dreamdive/
  config.py
  schemas.py
  db/
  ingestion/
  llm/
  memory/
  simulation/
tests/
```

## Design Notes

- State is append-only. Replay is the source of truth.
- `tick` is stored as a human-readable label and `timeline_index` is stored as a
  sortable integer so replay logic never depends on lexicographic ordering.
- LLM integration is wrapped behind a transport protocol so validation and retry
  logic can be tested without a live API.
- The runtime scaffold is dependency-light so it works in this workspace now.
  The SQL migration and Postgres repositories target PostgreSQL/pgvector for the
  production path, but `psycopg` is not installed in this workspace yet.
- Simulation checkpoints can now live either in local JSON files or in a
  PostgreSQL `simulation_session` table, keyed by session ID.

## Configuration

The CLI now reads `DREAMDIVE_*` settings from a local `.env` file in the current
working directory, with real environment variables taking precedence.

Start from [.env.example](/Users/Zekang.Zhang/Documents/dreamdive2/.env.example) and create a `.env` file such as:

```dotenv
DREAMDIVE_LLM_PRIMARY_API_KEY="your_moonshot_key"
DREAMDIVE_LLM_FALLBACK_API_KEY="your_gemini_key"
```

The loader searches upward for `.env`, so running from `src/` can still use a repo-root `.env`.

## CLI Config File

For repeatable command defaults, Dreamdive can also read a local TOML config file.
This is a good place for non-secret settings like workspace, session ID, debug flags,
and default tick counts.

Dreamdive searches upward for either:

- `dreamdive.toml`
- `.dreamdive/config.toml`

Start from [dreamdive.toml.example](/Users/Zekang.Zhang/Documents/dreamdive2/dreamdive.toml.example).

Example:

```toml
[defaults]
workspace = ".dreamdive"
session_id = "main"

[ingest]
source = "resources/redcliff.txt"

[init-snapshot]
source = "resources/redcliff.txt"
chapter_id = "001"

[run]
ticks = 10

[profiles.debug]
debug = true
debug_dir = "/tmp/dreamdive-debug"
```

Then you can run:

```bash
PYTHONPATH=src python3 -m dreamdive.cli ingest
PYTHONPATH=src python3 -m dreamdive.cli init-snapshot
PYTHONPATH=src python3 -m dreamdive.cli run
PYTHONPATH=src python3 -m dreamdive.cli run --profile debug
```

Precedence is:

1. CLI flags
2. selected profile values from `dreamdive.toml`
3. command/default values from `dreamdive.toml`
4. built-in CLI defaults

## Debug Mode

Most CLI commands support `--debug` and `--debug-dir`.

Example:

```bash
PYTHONPATH=src python3 -m dreamdive.cli ingest novel.md --workspace .dreamdive --debug
```

When debug mode is enabled:
- high-level flow milestones are printed to stderr
- a `events.jsonl` timeline is written under the debug directory
- each LLM attempt is captured under `llm/` with request, raw response, parsed JSON, and result metadata

If `--debug-dir` is not provided, Dreamdive creates a temporary debug directory automatically.

## Next Recommended Steps

1. Install `psycopg` and point `DREAMDIVE_DATABASE_URL` at a live PostgreSQL instance.
2. Run `python3 -m dreamdive.cli migrate` to apply `migrations/0001_initial_schema.sql`.
3. Run the CLI with `DREAMDIVE_PERSISTENCE_BACKEND=postgres` and a `--session-id`
   to store simulation checkpoints in PostgreSQL instead of local JSON.
4. Add a real broker-backed background worker on top of the queue backend.
5. Exercise pgvector-backed retrieval against a live database.

## Visualization Prototype

The repository now includes a desktop-first visualization prototype at
[`visualization/index.html`](/Users/Zekang.Zhang/Documents/dreamdive2/visualization/index.html).
It reads the local append-only simulation session and renders:

- a master timeline with persisted and scheduled events
- a tension curve from world snapshots and arc state
- a relationship graph at the current cursor
- character swimlanes with location continuity and goal focus
- a right-side slide-in detail panel for events and characters

Serve it locally from the repo root with:

```bash
PYTHONPATH=src python3 -m dreamdive.cli visualize --workspace .dreamdive
```

The command prints a local URL like `http://127.0.0.1:8000/visualization/`.
You can override the session file with `?session=../path/to/simulation_session.json`
if you want the same UI to inspect another run.
