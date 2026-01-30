#!/usr/bin/env python
"""Quick test of dual-mode search functionality."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app_core import search_query, get_translations_by_chunks

# Test original mode
print("=" * 60)
print("TEST 1: Original (Dutch) mode")
print("=" * 60)
results_original = search_query(
    query_text="handel spierijen",
    inv_nrs=["1120"],
    top_k=5,
    translate_if_not_dutch=False,
    mode="original",
)
print(f"\nFound {len(results_original)} results")
if len(results_original) > 0:
    cols = ["tanap_id", "chunk_id", "similarity"]
    print(results_original[cols].head(3))

# Test translated mode
print("\n" + "=" * 60)
print("TEST 2: Translated (English) mode")
print("=" * 60)
results_translated = search_query(
    query_text="handel spierijen",
    inv_nrs=["1120"],
    top_k=5,
    translate_if_not_dutch=False,
    mode="translated",
)
print(f"\nFound {len(results_translated)} results")
if len(results_translated) > 0:
    cols = ["tanap_id", "chunk_id", "similarity"]
    print(results_translated[cols].head(3))

# Test both mode
print("\n" + "=" * 60)
print("TEST 3: Comparison (Both) mode")
print("=" * 60)
results_both = search_query(
    query_text="handel spierijen",
    inv_nrs=["1120"],
    top_k=5,
    translate_if_not_dutch=False,
    mode="both",
)
print(f"\nFound {len(results_both)} results (combined from both modes)")
if len(results_both) > 0:
    print(f"Columns in results: {list(results_both.columns)}")
    cols_available = ["tanap_id", "chunk_id", "similarity"]
    if "search_source" in results_both.columns:
        cols_available.append("search_source")
    print(results_both[cols_available].head(10))
    if "search_source" in results_both.columns:
        print(
            f"\nOriginal mode: {len(results_both[results_both['search_source'] == 'original'])} results"
        )
        print(
            f"Translated mode: {len(results_both[results_both['search_source'] == 'translated'])} results"
        )
    else:
        print("⚠️  Note: search_source column not found")

# Test translation fetching
print("\n" + "=" * 60)
print("TEST 4: Translation fetching")
print("=" * 60)
if len(results_original) > 0:
    first_result = results_original.iloc[0]
    inv_nr = first_result["inv_nr"]
    tanap_id = first_result["tanap_id"]
    chunk_id = first_result["chunk_id"]

    translations = get_translations_by_chunks(
        str(inv_nr), [int(chunk_id)], tanap_id=str(tanap_id)
    )
    key = (str(inv_nr), int(chunk_id))

    if key in translations:
        print(f"✅ Found translation for chunk {chunk_id}")
        trans_data = translations[key]

        # Show first 100 chars of each
        print(f"\nOriginal text (first 100 chars):")
        print(f"  {first_result['text'][:100]}...")

        print(f"\nTranslated text (first 100 chars):")
        print(f"  {trans_data['text_translated_clean'][:100]}...")
    else:
        print(f"⚠️  No translation found for chunk {chunk_id}")

print("\n✅ All tests completed!")
