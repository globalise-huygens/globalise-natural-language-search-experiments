#!/usr/bin/env python3
"""Compare original vs translated mode performance."""

from app_core import search_query
import pandas as pd

query = "activiteiten van weduwen in ternate"
inv_nrs = ["1267", "1120"]  # Test on two inventories

print(f"Query: '{query}'\n")
print("=" * 80)

# Test original mode
print("\n🇳🇱 ORIGINAL MODE (Dutch embeddings):")
results_orig = search_query(
    query_text=query,
    inv_nrs=inv_nrs,
    mode="original",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=5,
)

if results_orig is not None and len(results_orig) > 0:
    print(f"Top 5 scores: {results_orig['similarity'].head(5).tolist()}")
    print(f"Average: {results_orig['similarity'].mean():.4f}")
    print(f"Max: {results_orig['similarity'].max():.4f}")
else:
    print("No results")

# Test translated mode
print("\n🇬🇧 TRANSLATED MODE (English embeddings):")
results_trans = search_query(
    query_text=query,
    inv_nrs=inv_nrs,
    mode="translated",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=5,
)

if results_trans is not None and len(results_trans) > 0:
    print(f"Top 5 scores: {results_trans['similarity'].head(5).tolist()}")
    print(f"Average: {results_trans['similarity'].mean():.4f}")
    print(f"Max: {results_trans['similarity'].max():.4f}")
else:
    print("No results")

print("\n" + "=" * 80)
print("\n📊 ANALYSIS:")
if results_orig is not None and results_trans is not None:
    diff = results_orig["similarity"].mean() - results_trans["similarity"].mean()
    print(f"Average score difference: {diff:.4f} (original - translated)")
    if diff > 0:
        print(
            f"✅ Original is {diff:.4f} points higher ({(diff / results_trans['similarity'].mean() * 100):.1f}% better)"
        )
    else:
        print(f"✅ Translated is {abs(diff):.4f} points higher")
