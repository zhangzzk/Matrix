"""Recompute all embeddings in simulation_session.main.json with fixed tokenizer."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.memory.retrieval import embed_text, build_memory_semantic_text
from dreamdive.schemas import EpisodicMemory

# Load session
session_path = Path(".dreamdive/simulation_session.main.json")
print(f"Loading {session_path}...")
with open(session_path) as f:
    data = json.load(f)

# Count updates
total_memories = 0
updated_memories = 0
zero_before = 0
zero_after = 0

# Recompute embeddings for all memories
for agent_id, agent_data in data["agents"].items():
    memories = agent_data["snapshot"]["working_memory"]
    print(f"\nProcessing {agent_id}: {len(memories)} memories")

    for mem in memories:
        total_memories += 1

        # Check if currently all zeros
        old_embedding = mem.get("embedding", [])
        old_non_zero = sum(1 for x in old_embedding if abs(x) > 0.001)
        if old_non_zero == 0:
            zero_before += 1

        # Recompute embedding
        # The memory summary is used for semantic text
        semantic_text = mem.get("summary", "")
        new_embedding = embed_text(semantic_text, dimensions=1536)

        # Update
        mem["embedding"] = new_embedding

        # Check new embedding
        new_non_zero = sum(1 for x in new_embedding if abs(x) > 0.001)
        if new_non_zero == 0:
            zero_after += 1

        if old_non_zero != new_non_zero:
            updated_memories += 1
            print(f"  ✓ Updated: {old_non_zero} → {new_non_zero} non-zero dims | \"{semantic_text[:50]}...\"")

print(f"\n{'='*70}")
print(f"SUMMARY")
print(f"{'='*70}")
print(f"Total memories: {total_memories}")
print(f"All-zero before: {zero_before} ({zero_before/total_memories*100:.1f}%)")
print(f"All-zero after: {zero_after} ({zero_after/total_memories*100:.1f}%)")
print(f"Updated: {updated_memories}")

# Save backup
backup_path = session_path.with_suffix(".json.backup")
print(f"\nSaving backup to {backup_path}...")
with open(backup_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# Save updated session
print(f"Saving updated session to {session_path}...")
with open(session_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("\n✓ Done! All embeddings recomputed with Chinese tokenizer support.")
