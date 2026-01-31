#!/usr/bin/env python3
"""
Generate embeddings from normalized translations (text_translated_normalized).
Uses OpenAI text-embedding-3-small model.
"""

import os
import sqlite3
from pathlib import Path
from typing import List
from dotenv import load_dotenv
import openai
from openai import OpenAI
import numpy as np
import faiss
from tqdm import tqdm

load_dotenv()

# Configuration
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
EMBEDDINGS_DIR = Path("embeddings")
EMBEDDINGS_DIR.mkdir(exist_ok=True)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BATCH_SIZE = 100

# All inventories with translations
ALL_INVENTORIES = [
    1120,
    1267,
    1274,
    1539,
    1547,
    1557,
    2448,
    2548,
    2555,
    2775,
    3142,
    3891,
    7923,
    8023,
    8121,
    8237,
    8276,
    8284,
    8697,
    8834,
]


def get_embedding_batch(texts: List[str], client: OpenAI) -> List[List[float]]:
    """Get embeddings for a batch of texts with retry logic."""
    texts = [text.replace("\n", " ")[:8192] for text in texts]  # Limit to 8192 tokens

    try:
        response = client.embeddings.create(input=texts, model=EMBEDDING_MODEL)
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"\n⚠️  Batch embedding failed: {e}")
        # Retry individually
        embeddings = []
        for text in texts:
            try:
                response = client.embeddings.create(input=[text], model=EMBEDDING_MODEL)
                embeddings.append(response.data[0].embedding)
            except Exception as e2:
                print(f"⚠️  Individual embedding failed: {e2}, using zero vector")
                embeddings.append([0.0] * EMBEDDING_DIM)
        return embeddings


def generate_embeddings_for_inventory(inv_nr: int, client: OpenAI):
    """Generate normalized embeddings for one inventory."""

    print(f"\n{'=' * 80}")
    print(f"Processing inventory {inv_nr}")
    print(f"{'=' * 80}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if normalized translations exist
    cursor.execute(
        """
        SELECT COUNT(*) 
        FROM documents 
        WHERE inv_nr = ? AND text_translated_normalized IS NOT NULL
    """,
        (str(inv_nr),),
    )

    count = cursor.fetchone()[0]
    if count == 0:
        print(f"❌ No normalized translations found for inventory {inv_nr}")
        conn.close()
        return

    # Get all normalized translations
    cursor.execute(
        """
        SELECT rowid, text_translated_normalized 
        FROM documents 
        WHERE inv_nr = ? AND text_translated_normalized IS NOT NULL
        ORDER BY rowid
    """,
        (str(inv_nr),),
    )

    rows = cursor.fetchall()
    # Filter out any None values
    rows = [(rowid, text) for rowid, text in rows if text is not None]
    print(f"📊 Found {len(rows)} chunks with normalized translations")

    # Check text lengths
    lengths = [len(text) for _, text in rows]
    print(
        f"📊 Text lengths: avg={np.mean(lengths):.0f}, max={max(lengths):,}, min={min(lengths)}"
    )

    if max(lengths) > 20000:
        long_count = sum(1 for l in lengths if l > 8000)
        print(f"⚠️  Warning: {long_count} chunks exceed 8000 chars (will be truncated)")

    # Generate embeddings in batches
    all_embeddings = []
    texts = [text for _, text in rows]

    print(f"\n🧠 Generating embeddings...")
    for i in tqdm(range(0, len(texts), BATCH_SIZE), desc=f"Embedding {inv_nr}"):
        batch = texts[i : i + BATCH_SIZE]
        embeddings = get_embedding_batch(batch, client)
        all_embeddings.extend(embeddings)

    # Convert to numpy array
    embeddings_array = np.array(all_embeddings, dtype=np.float32)

    # Normalize embeddings for cosine similarity
    faiss.normalize_L2(embeddings_array)

    # Create FAISS index
    index = faiss.IndexFlatIP(
        EMBEDDING_DIM
    )  # Inner product = cosine similarity after normalization
    index.add(embeddings_array)

    # Save index
    output_path = EMBEDDINGS_DIR / f"{inv_nr}_translated_normalized.index"
    faiss.write_index(index, str(output_path))

    print(f"✅ Saved normalized embeddings: {output_path}")
    print(f"   {index.ntotal:,} vectors, dimension {index.d}")

    conn.close()


def main():
    """Generate embeddings for all inventories."""

    client = OpenAI()

    print(f"📊 Generating normalized embeddings for {len(ALL_INVENTORIES)} inventories")
    print(f"🤖 Model: {EMBEDDING_MODEL} ({EMBEDDING_DIM} dimensions)")

    for inv_nr in ALL_INVENTORIES:
        try:
            generate_embeddings_for_inventory(inv_nr, client)
        except Exception as e:
            print(f"❌ Error processing inventory {inv_nr}: {e}")
            continue

    print(f"\n{'=' * 80}")
    print("✅ All embeddings generated!")
    print(f"{'=' * 80}")


if __name__ == "__main__":
    main()
