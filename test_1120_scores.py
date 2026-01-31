#!/usr/bin/env python3
"""Test script to verify 1120 similarity scores after fix."""

from app_core import search_query

# Test search on 1120 in translated mode
print("Testing inventory 1120 in translated mode...")
print("Query: 'activiteiten van weduwen in ternate'\n")

results = search_query(
    query_text="activiteiten van weduwen in ternate",
    inv_nrs=["1120"],
    mode="translated",
    use_bm25=True,
    bm25_weight=0.3,
    top_k=10,
)

if results is not None and len(results) > 0:
    print(f"✅ Search returned {len(results)} results\n")
    print("Top 10 similarity scores:")
    for i, row in results.head(10).iterrows():
        score = row.get("similarity", row.get("combined_score", "N/A"))
        print(f"  {i + 1}. Score: {score:.4f}")

    avg_score = (
        results["similarity"].mean()
        if "similarity" in results.columns
        else results.get("combined_score", [0]).mean()
    )
    max_score = (
        results["similarity"].max()
        if "similarity" in results.columns
        else results.get("combined_score", [0]).max()
    )
    print(f"\n📊 Average score: {avg_score:.4f}")
    print(f"📊 Max score: {max_score:.4f}")

    if 0.70 <= max_score <= 0.85:
        print("\n✅ Scores look GOOD (0.70-0.85 range)")
    elif max_score > 0.85:
        print("\n⚠️  Scores still HIGH (>0.85) - issue may persist")
    else:
        print("\n📊 Scores are LOW (<0.70)")
else:
    print("❌ No results returned")
