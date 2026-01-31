#!/usr/bin/env python3
"""
Test normalized embeddings vs original and standard translated embeddings.
Compare performance across different embedding approaches.
"""

from app_core import search_query
import pandas as pd

query = "activiteiten van weduwen in ternate"
inv_nrs = ["1267", "1120"]

print(f"Query: '{query}'\n")
print("=" * 80)

# Test 1: Original Dutch embeddings
print("\n🇳🇱 ORIGINAL MODE (Dutch embeddings):")
try:
    results_orig = search_query(
        query_text=query,
        inv_nrs=inv_nrs,
        mode="original",
        use_bm25=True,
        bm25_weight=0.3,
        top_k=5,
    )
    if results_orig is not None and len(results_orig) > 0:
        scores_orig = results_orig["similarity"].head(5).tolist()
        print(f"Top 5 scores: {[f'{s:.4f}' for s in scores_orig]}")
        print(f"Average: {results_orig['similarity'].mean():.4f}")
    else:
        print("No results")
        results_orig = None
except Exception as e:
    print(f"Error: {e}")
    results_orig = None

# Test 2: Standard translated embeddings (with original terms + translations)
print("\n🇬🇧 TRANSLATED MODE (verbose English embeddings):")
try:
    results_trans = search_query(
        query_text=query,
        inv_nrs=inv_nrs,
        mode="translated",
        use_bm25=True,
        bm25_weight=0.3,
        top_k=5,
    )
    if results_trans is not None and len(results_trans) > 0:
        scores_trans = results_trans["similarity"].head(5).tolist()
        print(f"Top 5 scores: {[f'{s:.4f}' for s in scores_trans]}")
        print(f"Average: {results_trans['similarity'].mean():.4f}")
    else:
        print("No results")
        results_trans = None
except Exception as e:
    print(f"Error: {e}")
    results_trans = None

# Test 3: Normalized embeddings (English only, no original terms)
print("\n✨ NORMALIZED MODE (clean English embeddings):")
print("Note: This is a NEW mode using embeddings from text_translated_normalized")
print("which contains ONLY the English translations without original Dutch terms.")
print("Manually loading indices...")

import faiss
import numpy as np
from openai import OpenAI

client = OpenAI()

# Generate query embedding (English)
query_en = "activities of widows in ternate"
response = client.embeddings.create(input=[query_en], model="text-embedding-3-small")
query_embedding = np.array([response.data[0].embedding], dtype=np.float32)
faiss.normalize_L2(query_embedding)

# Search in normalized embeddings
results_norm = []
for inv_nr in inv_nrs:
    index = faiss.read_index(f"embeddings/{inv_nr}_translated_normalized.index")
    distances, indices = index.search(query_embedding, 5)
    results_norm.extend(distances[0].tolist())

scores_norm = sorted(results_norm, reverse=True)[:5]
print(f"Top 5 scores: {[f'{s:.4f}' for s in scores_norm]}")
print(f"Average: {np.mean(scores_norm):.4f}")

# Summary
print("\n" + "=" * 80)
print("\n📊 COMPARISON:")
print("-" * 80)
print(f"{'Mode':<30} {'Avg Score':<12} {'Max Score':<12} {'Status'}")
print("-" * 80)

if results_orig is not None:
    avg_orig = results_orig["similarity"].mean()
    max_orig = results_orig["similarity"].max()
    print(f"{'Original (Dutch)':<30} {avg_orig:<12.4f} {max_orig:<12.4f} ✅")
else:
    print(f"{'Original (Dutch)':<30} {'N/A':<12} {'N/A':<12} ❌")

if results_trans is not None:
    avg_trans = results_trans["similarity"].mean()
    max_trans = results_trans["similarity"].max()
    print(
        f"{'Translated (verbose English)':<30} {avg_trans:<12.4f} {max_trans:<12.4f} ✅"
    )
else:
    print(f"{'Translated (verbose English)':<30} {'N/A':<12} {'N/A':<12} ❌")

avg_norm = np.mean(scores_norm)
max_norm = max(scores_norm)
print(f"{'Normalized (clean English)':<30} {avg_norm:<12.4f} {max_norm:<12.4f} ✨")

print("-" * 80)

# Determine winner
if results_orig is not None:
    if avg_norm > avg_orig:
        improvement = ((avg_norm - avg_orig) / avg_orig) * 100
        print(
            f"\n✨ Normalized embeddings are {improvement:.1f}% better than original!"
        )
    elif avg_orig > avg_norm:
        diff = ((avg_orig - avg_norm) / avg_norm) * 100
        print(f"\n🇳🇱 Original embeddings are still {diff:.1f}% better than normalized")
    else:
        print(f"\n🤝 Normalized and original perform similarly")
