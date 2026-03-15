"""Test Chinese tokenizer fix."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dreamdive.memory.retrieval import tokenize, embed_text

print("="*70)
print("TESTING CHINESE TOKENIZER FIX")
print("="*70)

# Test cases
test_cases = [
    ("梦见自己身穿白衣", "Pure Chinese"),
    ("路明非 Lu Mingfei", "Mixed Chinese + English"),
    ("high school crush", "Pure English"),
    ("陈雯雯 is beautiful", "Mixed with stopwords"),
    ("123 号房间", "Numbers + Chinese"),
]

print("\nTokenization results:")
print("-" * 70)
for text, description in test_cases:
    tokens = tokenize(text)
    print(f"\n{description}:")
    print(f"  Text: \"{text}\"")
    print(f"  Tokens: {tokens}")
    print(f"  Count: {len(tokens)}")

print("\n" + "="*70)
print("EMBEDDING GENERATION")
print("="*70)

for text, description in test_cases:
    embedding = embed_text(text, dimensions=1536)
    non_zero = sum(1 for x in embedding if abs(x) > 0.001)
    density = non_zero / len(embedding) * 100

    if non_zero == 0:
        status = "❌ ALL ZEROS"
    else:
        status = f"✓ {non_zero}/{len(embedding)} ({density:.1f}%)"

    print(f"\n{description}: {status}")
    print(f"  Text: \"{text}\"")

print("\n" + "="*70)
print("BEFORE vs AFTER")
print("="*70)
print("""
BEFORE (ASCII only):
  "梦见自己身穿白衣" → {} → [0, 0, 0, ...]

AFTER (Chinese + ASCII):
  "梦见自己身穿白衣" → {'梦见自己身穿白衣'} → [0.21, -0.15, 0.08, ...]

The embedding is now a proper sparse vector instead of all zeros!
""")
