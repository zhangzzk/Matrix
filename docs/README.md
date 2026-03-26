# Dreamdive Documentation

Complete documentation for the Dreamdive narrative simulation framework.

---

## 📚 Documentation Index

### Quick Start

- **[CLI_COMMAND_REFERENCE.md](CLI_COMMAND_REFERENCE.md)** - Complete CLI command reference
  - All commands with examples
  - Common patterns and workflows
  - Configuration options

### Core Systems

#### Domain Attributes System
- **[DOMAIN_ATTRIBUTES_GUIDE.md](DOMAIN_ATTRIBUTES_GUIDE.md)** - Complete guide (200+ lines)
- **[DOMAIN_ATTRIBUTES_QUICKREF.md](DOMAIN_ATTRIBUTES_QUICKREF.md)** - Quick reference
- **[DOMAIN_ATTRIBUTES_IMPLEMENTATION.md](DOMAIN_ATTRIBUTES_IMPLEMENTATION.md)** - Implementation summary

Track story-specific attributes like 言灵 (Dragon Raja), bloodlines, houses (Game of Thrones), etc.

#### Narrative Architecture (P0.5)
- **[NARRATIVE_ARCHITECTURE_GUIDE.md](NARRATIVE_ARCHITECTURE_GUIDE.md)** - Complete guide (700+ lines)
- **[NARRATIVE_ARCHITECTURE_QUICKREF.md](NARRATIVE_ARCHITECTURE_QUICKREF.md)** - Quick reference

Design story structure before simulation with gravitational waypoints (not rails).

#### Agent Context System
- **[AGENT_CONTEXT_GUIDE.md](AGENT_CONTEXT_GUIDE.md)** - Agent context and memory

How agents perceive the world and maintain context during simulation.

### Quality & Fidelity

#### Synthesis Fidelity
- **[SYNTHESIS_FIDELITY_GUIDE.md](SYNTHESIS_FIDELITY_GUIDE.md)** - Complete guide (700+ lines)
- **[SYNTHESIS_FIDELITY_QUICKREF.md](SYNTHESIS_FIDELITY_QUICKREF.md)** - Quick reference

Ensure generated chapters follow simulation results (not LLM invention) while matching original style.

#### Prompt Quality
- **[PROMPT_QUALITY_IMPROVEMENTS.md](PROMPT_QUALITY_IMPROVEMENTS.md)** - Complete guide (600+ lines)
- **[PROMPT_IMPROVEMENTS_QUICKREF.md](PROMPT_IMPROVEMENTS_QUICKREF.md)** - Quick reference

Fix repetitive catchphrases, improve chapter quality, proper pacing.

### Optimization

#### Token Optimization
- **[TOKEN_OPTIMIZATION_ANALYSIS.md](TOKEN_OPTIMIZATION_ANALYSIS.md)** - Complete analysis (11,000+ words)
- **[TOKEN_OPTIMIZATION_QUICKREF.md](TOKEN_OPTIMIZATION_QUICKREF.md)** - Quick reference
- **[TOKEN_OPTIMIZATION_SUMMARY.md](TOKEN_OPTIMIZATION_SUMMARY.md)** - Executive summary

Reduce LLM token usage by 40-70% with minimal quality loss.

### Usage Guides

- **[P0_P5_USAGE_GUIDE.md](P0_P5_USAGE_GUIDE.md)** - Complete pipeline walkthrough

### Project Status

- **[IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md)** - Current implementation status
- **[FINAL_IMPLEMENTATION_SUMMARY.md](FINAL_IMPLEMENTATION_SUMMARY.md)** - Summary of completed work
- **[SECURITY_ALERT.md](SECURITY_ALERT.md)** - Security considerations
- **[progress.md](progress.md)** - Development progress notes

---

## 🎯 Where to Start

### New Users

1. **[CLI_COMMAND_REFERENCE.md](CLI_COMMAND_REFERENCE.md)** - Learn the commands
2. **[P0_P5_USAGE_GUIDE.md](P0_P5_USAGE_GUIDE.md)** - Understand the pipeline
3. **[NARRATIVE_ARCHITECTURE_GUIDE.md](NARRATIVE_ARCHITECTURE_GUIDE.md)** - Learn to design stories

### Optimizing Performance

1. **[TOKEN_OPTIMIZATION_QUICKREF.md](TOKEN_OPTIMIZATION_QUICKREF.md)** - Quick wins
2. **[TOKEN_OPTIMIZATION_SUMMARY.md](TOKEN_OPTIMIZATION_SUMMARY.md)** - Implementation guide

### Improving Quality

1. **[SYNTHESIS_FIDELITY_QUICKREF.md](SYNTHESIS_FIDELITY_QUICKREF.md)** - Ensure accuracy
2. **[PROMPT_IMPROVEMENTS_QUICKREF.md](PROMPT_IMPROVEMENTS_QUICKREF.md)** - Fix common issues

### Advanced Features

1. **[DOMAIN_ATTRIBUTES_GUIDE.md](DOMAIN_ATTRIBUTES_GUIDE.md)** - Story-specific systems
2. **[AGENT_CONTEXT_GUIDE.md](AGENT_CONTEXT_GUIDE.md)** - Agent memory systems

---

## 📖 Documentation by Phase

### P0: User Configuration
- CLI_COMMAND_REFERENCE.md (configure command)

### P0.5: Narrative Design
- **NARRATIVE_ARCHITECTURE_GUIDE.md** ⭐
- NARRATIVE_ARCHITECTURE_QUICKREF.md
- CLI_COMMAND_REFERENCE.md (design command)

### P1: Ingestion
- DOMAIN_ATTRIBUTES_GUIDE.md
- CLI_COMMAND_REFERENCE.md (ingest command)

### P2-P4: Simulation
- AGENT_CONTEXT_GUIDE.md
- TOKEN_OPTIMIZATION guides
- CLI_COMMAND_REFERENCE.md (init, run, tick commands)

### P5: Synthesis
- **SYNTHESIS_FIDELITY_GUIDE.md** ⭐
- PROMPT_QUALITY_IMPROVEMENTS.md
- CLI_COMMAND_REFERENCE.md (synthesize command)

---

## 🔍 Documentation by Topic

### Commands & CLI
- CLI_COMMAND_REFERENCE.md

### Story Design
- NARRATIVE_ARCHITECTURE_GUIDE.md
- NARRATIVE_ARCHITECTURE_QUICKREF.md

### Quality Control
- SYNTHESIS_FIDELITY_GUIDE.md
- SYNTHESIS_FIDELITY_QUICKREF.md
- PROMPT_QUALITY_IMPROVEMENTS.md
- PROMPT_IMPROVEMENTS_QUICKREF.md

### Performance
- TOKEN_OPTIMIZATION_ANALYSIS.md
- TOKEN_OPTIMIZATION_QUICKREF.md
- TOKEN_OPTIMIZATION_SUMMARY.md

### Advanced Systems
- DOMAIN_ATTRIBUTES_GUIDE.md
- DOMAIN_ATTRIBUTES_QUICKREF.md
- AGENT_CONTEXT_GUIDE.md

### Project Info
- IMPLEMENTATION_STATUS.md
- FINAL_IMPLEMENTATION_SUMMARY.md
- SECURITY_ALERT.md

---

## 📊 Documentation Stats

| Category | Files | Total Lines |
|----------|-------|-------------|
| Narrative Architecture | 2 | ~1,000 |
| Token Optimization | 3 | ~15,000 |
| Synthesis Fidelity | 2 | ~1,200 |
| Domain Attributes | 3 | ~800 |
| Prompt Quality | 2 | ~1,000 |
| Agent Context | 1 | ~500 |
| CLI Reference | 1 | ~400 |
| Usage Guides | 1 | ~300 |
| Project Status | 4 | ~500 |
| **Total** | **19** | **~20,700** |

---

## 🎓 Learning Path

### Beginner Path
1. CLI_COMMAND_REFERENCE.md
2. P0_P5_USAGE_GUIDE.md
3. NARRATIVE_ARCHITECTURE_QUICKREF.md
4. Run first simulation

### Intermediate Path
1. NARRATIVE_ARCHITECTURE_GUIDE.md (full)
2. SYNTHESIS_FIDELITY_GUIDE.md (full)
3. TOKEN_OPTIMIZATION_QUICKREF.md
4. DOMAIN_ATTRIBUTES_GUIDE.md

### Advanced Path
1. TOKEN_OPTIMIZATION_ANALYSIS.md (full)
2. AGENT_CONTEXT_GUIDE.md
3. DOMAIN_ATTRIBUTES_IMPLEMENTATION.md
4. Contribute to codebase

---

## 📝 Documentation Conventions

### File Naming
- `*_GUIDE.md` - Comprehensive guides (500+ lines)
- `*_QUICKREF.md` - Quick reference cards
- `*_SUMMARY.md` - Executive summaries
- `*_IMPLEMENTATION.md` - Implementation details

### Symbols
- ⭐ Most important documentation
- ✅ Completed features
- 📋 Designed but not implemented
- 🚧 Work in progress

---

## 🔄 Recent Updates

**March 2026**
- Added Token Optimization system (40-70% savings)
- Added Narrative Architecture (P0.5 design phase)
- Simplified CLI commands (init-snapshot → init, design-architecture → design)
- Added comprehensive CLI command reference

**February 2026**
- Added Synthesis Fidelity system
- Added Prompt Quality improvements
- Added Domain Attributes system

---

## 📬 Getting Help

1. Check relevant guide/quickref
2. Review CLI_COMMAND_REFERENCE.md
3. Search documentation: `grep -r "search term" docs/`
4. Check IMPLEMENTATION_STATUS.md for known issues

---

**Total Documentation**: 19 files, ~20,700 lines
**Last Updated**: March 2026
