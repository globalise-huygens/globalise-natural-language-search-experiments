#!/usr/bin/env python
"""
Generate FAISS embeddings for translated text.

This script creates separate FAISS indices for translated (English) text
to enable comparison between original (Dutch) and translated searches.

Usage:
    python generate_translated_embeddings.py [--inv-nr INV_NR]

    If --inv-nr is not provided, generates for all inventories with translations.
"""

import sys
from pathlib import Path
from openai import OpenAI
import argparse

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from app_core import (
    load_or_create_embeddings,
    list_available_inv_nrs,
    DB_PATH,
)


def main():
    parser = argparse.ArgumentParser(
        description="Generate translated embeddings for VOC documents"
    )
    parser.add_argument(
        "--inv-nr",
        type=str,
        help="Specific inventory number to process. If not provided, processes all.",
    )
    args = parser.parse_args()

    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("   Please ensure SQLite database has been built first.")
        sys.exit(1)

    # Initialize OpenAI client
    client = OpenAI()

    # Determine which inventory numbers to process
    if args.inv_nr:
        inv_nrs = [args.inv_nr]
        print(f"📌 Processing specific inventory: {args.inv_nr}")
    else:
        inv_nrs = list_available_inv_nrs()
        print(f"📋 Found {len(inv_nrs)} available inventory numbers")

    print(f"\n🚀 Starting translated embeddings generation...\n")

    success_count = 0
    failed_count = 0
    skipped_count = 0

    for i, inv_nr in enumerate(inv_nrs, 1):
        print(f"[{i}/{len(inv_nrs)}] Processing {inv_nr}...")
        try:
            # Try to load/create translated embeddings
            faiss_idx, chunks = load_or_create_embeddings(
                inv_nr, client, mode="translated", use_cache=False
            )
            print(
                f"    ✅ Generated {len(chunks)} chunks, {faiss_idx.ntotal} embeddings"
            )
            success_count += 1
        except ValueError as e:
            if "No translated text found" in str(e):
                print(f"    ⏭️  Skipped: No translations available")
                skipped_count += 1
            else:
                print(f"    ❌ Error: {e}")
                failed_count += 1
        except Exception as e:
            print(f"    ❌ Unexpected error: {e}")
            failed_count += 1

    print(f"\n" + "=" * 60)
    print(f"📊 RESULTS SUMMARY")
    print(f"=" * 60)
    print(f"✅ Successfully generated: {success_count}")
    print(f"⏭️  Skipped (no translations): {skipped_count}")
    print(f"❌ Failed: {failed_count}")
    print(f"\n📁 Translated embeddings location:")
    print(f"   embeddings/{{inv_nr}}_translated.index")


if __name__ == "__main__":
    main()
