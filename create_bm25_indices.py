#!/usr/bin/env python3
"""
Create BM25 indices for VOC corpus.
Run this script to pre-compute BM25 keyword search indices.

Usage:
    python create_bm25_indices.py              # Creates for all inventories
    python create_bm25_indices.py --sample     # Creates for first 5 inventories (quick test)
    python create_bm25_indices.py --limit 20   # Creates for first 20 inventories
"""

import sqlite3
import pickle
from pathlib import Path
from tqdm import tqdm
from rank_bm25 import BM25Okapi
import pandas as pd
import argparse


def create_bm25_indices(limit=None, skip_existing=True):
    """
    Create BM25 indices for all or specified inventory numbers.

    Args:
        limit: Maximum number of inventories to process (None = all)
        skip_existing: Skip inventories that already have indices
    """
    db_path = Path("text-metadata-sqlite/voc_documents.db")
    bm25_dir = Path("bm25_indices")
    bm25_dir.mkdir(exist_ok=True)

    # Get list of all inventory numbers
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        print(
            "   Make sure you're in the right directory and have run the app at least once."
        )
        return

    with sqlite3.connect(db_path) as conn:
        df_inv = pd.read_sql_query(
            "SELECT DISTINCT inv_nr FROM documents ORDER BY inv_nr", conn
        )
        inv_nrs = df_inv["inv_nr"].tolist()

    if limit:
        inv_nrs = inv_nrs[:limit]

    print(f"\n{'=' * 70}")
    print(f"Creating BM25 indices for {len(inv_nrs)} inventory numbers...")
    print(f"{'=' * 70}\n")

    created = 0
    skipped = 0

    for inv_nr in tqdm(inv_nrs, desc="BM25 Index Creation"):
        bm25_file = bm25_dir / f"{inv_nr}.pkl"

        # Skip if already exists
        if bm25_file.exists():
            if skip_existing:
                skipped += 1
                continue

        # Load all chunks for this inventory
        with sqlite3.connect(db_path) as conn:
            df_chunks = pd.read_sql_query(
                "SELECT text FROM documents WHERE inv_nr=? ORDER BY chunk_id",
                conn,
                params=(inv_nr,),
            )

        if df_chunks.empty:
            print(f"⚠️  No data for {inv_nr}")
            continue

        # Prepare texts and tokenize
        texts = df_chunks["text"].fillna("").astype(str).tolist()
        tokenized_corpus = [text.lower().split() for text in texts]

        # Create BM25 index
        bm25 = BM25Okapi(tokenized_corpus)

        # Save to pickle file
        with open(bm25_file, "wb") as f:
            pickle.dump({"bm25": bm25, "texts": texts}, f)

        created += 1

    print(f"\n{'=' * 70}")
    print(f"✅ BM25 indices created: {created}")
    if skipped > 0:
        print(f"⏭️  Indices skipped (already exist): {skipped}")
    print(f"📁 Location: {bm25_dir}/")
    print(f"{'=' * 70}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Create BM25 indices for VOC corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python create_bm25_indices.py              # All inventories
  python create_bm25_indices.py --sample     # First 5 (quick test)
  python create_bm25_indices.py --limit 20   # First 20
        """,
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Create indices for first 5 inventories (quick test)",
    )

    parser.add_argument("--limit", type=int, help="Limit to first N inventories")

    parser.add_argument(
        "--force", action="store_true", help="Recreate all indices, even if they exist"
    )

    args = parser.parse_args()

    limit = None
    if args.sample:
        limit = 5
        print("🚀 Quick test mode: Creating indices for first 5 inventories\n")
    elif args.limit:
        limit = args.limit
        print(f"🚀 Creating indices for first {limit} inventories\n")
    else:
        print("🚀 Full mode: Creating indices for all inventories\n")

    create_bm25_indices(limit=limit, skip_existing=not args.force)


if __name__ == "__main__":
    main()
