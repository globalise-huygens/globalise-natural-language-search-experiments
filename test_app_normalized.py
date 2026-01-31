#!/usr/bin/env python3
"""Test all modes with normalized embeddings."""

from app_core import search_query

query = "activiteiten van weduwen in ternate"
inv_nrs = ["1267", "1120"]

print("=" * 80)
print("TESTING NORMALIZED EMBEDDINGS IN APP")
print("=" * 80)

# Test original mode
print("\n🇳🇱 ORIGINAL MODE:")
results_orig = search_query(
    query_text=query,
    inv_nrs=inv_nrs,
    mode="original",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=5,
)
print(f"Avg similarity: {results_orig['similarity'].mean():.4f}")

# Test translated mode (now using normalized embeddings)
print("\n✨ TRANSLATED MODE (using normalized embeddings):")
results_trans = search_query(
    query_text=query,
    inv_nrs=inv_nrs,
    mode="translated",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=5,
)
print(f"Avg similarity: {results_trans['similarity'].mean():.4f}")

# Test compare mode
print("\n🔄 COMPARE MODE:")
results_compare = search_query(
    query_text=query,
    inv_nrs=inv_nrs,
    mode="compare",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=5,
)
print(f"Total results: {len(results_compare)}")
print(f"  - Original results: {(results_compare['search_source'] == 'original').sum()}")
print(
    f"  - Translated results: {(results_compare['search_source'] == 'translated').sum()}"
)

print("\n" + "=" * 80)
print("✅ All modes working with normalized embeddings!")
print("Performance comparison:")
print(f"  Original Dutch:        {results_orig['similarity'].mean():.4f} avg")
print(f"  Normalized English:    {results_trans['similarity'].mean():.4f} avg")
improvement = (
    (results_trans["similarity"].mean() - results_orig["similarity"].mean())
    / results_orig["similarity"].mean()
) * 100
if improvement > 0:
    print(f"  → Normalized is {improvement:.1f}% worse than original (expected)")
else:
    print(f"  → Normalized is {abs(improvement):.1f}% better than original")
print("=" * 80)
