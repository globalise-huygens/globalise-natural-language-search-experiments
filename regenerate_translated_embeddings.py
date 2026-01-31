#!/usr/bin/env python3
"""
Regenerate all translated embeddings with text-embedding-3-small model.

This script fixes the dimension mismatch issue by regenerating all translated
embeddings (currently 3072 dims) with the small model (1536 dims).
"""

import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import numpy as np
import faiss
from tqdm import tqdm

# Configuration
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
EMBEDDINGS_DIR = Path("embeddings")
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# All inventories with translations (including 1120 and 3891)
ALL_INVENTORIES = [1120, 3891]


def get_openai_client() -> OpenAI:
    """Initialize OpenAI client."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def regenerate_translated_embeddings(inv_nr: str) -> faiss.Index:
    """Regenerate translated embeddings for an inventory."""
    print(f"\n🔄 Regenerating translated embeddings for {inv_nr}...")

    # Fetch translated texts from database
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            """
            SELECT rowid, text_translated_clean
            FROM documents
            WHERE inv_nr = ? AND text_translated_clean IS NOT NULL
            ORDER BY rowid
            """,
            (inv_nr,),
        )
        rows = cur.fetchall()
        texts = [row["text_translated_clean"] for row in rows]

    if not texts:
        print(f"   ⚠️  No translated texts found for {inv_nr}, skipping")
        return None

    print(f"   Found {len(texts)} translated texts")

    # Generate embeddings in batches
    client = get_openai_client()
    embeddings = []
    batch_size = 20

    for i in tqdm(range(0, len(texts), batch_size), desc="Embedding batches"):
        batch = texts[i : i + batch_size]
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            # If batch fails, try one at a time
            print(f"\n⚠️  Batch failed at index {i}, processing individually...")
            for j, text in enumerate(batch):
                try:
                    response = client.embeddings.create(
                        model=EMBEDDING_MODEL, input=[text]
                    )
                    embeddings.append(response.data[0].embedding)
                except Exception as e2:
                    # Truncate if still too long
                    print(
                        f"⚠️  Text at index {i + j} too long ({len(text)} chars), truncating..."
                    )
                    truncated = text[:15000]
                    response = client.embeddings.create(
                        model=EMBEDDING_MODEL, input=[truncated]
                    )
                    embeddings.append(response.data[0].embedding)

    # Create FAISS index
    embeddings_array = np.array(embeddings, dtype="float32")
    index = faiss.IndexFlatIP(EMBEDDING_DIM)
    faiss.normalize_L2(embeddings_array)
    index.add(embeddings_array)

    # Save index
    index_file = EMBEDDINGS_DIR / f"{inv_nr}_translated.index"
    faiss.write_index(index, str(index_file))
    print(f"   ✅ Saved {index.ntotal} embeddings to {index_file}")

    return index


def main():
    print("=" * 60)
    print("REGENERATE TRANSLATED EMBEDDINGS")
    print("=" * 60)
    print(f"Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM} dimensions)")
    print(f"Inventories: {len(ALL_INVENTORIES)}")
    print()

    completed = []
    skipped = []

    for inv_nr in ALL_INVENTORIES:
        try:
            index = regenerate_translated_embeddings(str(inv_nr))
            if index:
                completed.append(inv_nr)
            else:
                skipped.append(inv_nr)
        except Exception as e:
            print(f"❌ Error processing {inv_nr}: {e}")
            skipped.append(inv_nr)

    # Summary
    print("\n" + "=" * 60)
    print("✅ REGENERATION COMPLETE")
    print("=" * 60)
    print(f"Completed: {len(completed)}/{len(ALL_INVENTORIES)}")
    if completed:
        print(f"Success: {completed}")
    if skipped:
        print(f"Skipped: {skipped}")


if __name__ == "__main__":
    main()
