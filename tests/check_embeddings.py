"""Check embedding density in simulation session."""
import json

with open(".dreamdive/simulation_session.main.json") as f:
    data = json.load(f)

# Check working_memory embeddings
for agent_id, agent_data in data["agents"].items():
    memories = agent_data["snapshot"]["working_memory"]
    print(f"\n{agent_id}: {len(memories)} memories")

    zero_count = 0
    for i, mem in enumerate(memories[:5]):  # First 5
        emb = mem.get("embedding", [])
        non_zero = sum(1 for x in emb if abs(x) > 0.001)
        summary = mem.get("summary", "")[:70]

        if non_zero == 0:
            zero_count += 1
            print(f"  ❌ Memory {i}: ALL ZEROS | \"{summary}...\"")
        else:
            density = non_zero / len(emb) * 100
            print(f"  ✓ Memory {i}: {non_zero}/{len(emb)} ({density:.1f}%) | \"{summary}...\"")

    if zero_count > 0:
        print(f"  ⚠️  {zero_count} memories have all-zero embeddings!")

print("\n" + "="*70)
print("WHY ALL ZEROS?")
print("="*70)
print("""
Embeddings are all zeros when the semantic text has no valid tokens.

From retrieval.py:97-123 (embed_text):
1. Tokenize text (extract words, remove stopwords)
2. If no tokens → return zero vector
3. Otherwise → hash each token to vector dimensions

Common causes:
- Empty summary field
- Only stopwords like "the", "a", "and"
- Non-English text without proper tokenization
- Very short text with no meaningful content
""")
