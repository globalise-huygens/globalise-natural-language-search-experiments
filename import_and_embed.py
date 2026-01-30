#!/usr/bin/env python3
"""
Import batch-translated chunks into the database and generate embeddings.

This script handles the post-processing steps after batch translation:
1. Import translations from JSON files into SQLite database
2. Generate OpenAI embeddings for both original and translated text
3. Create FAISS indices for semantic search

Usage:
    # Import and embed a single inventory
    python import_and_embed.py --inv-nr 1267

    # Import and embed all inventories
    python import_and_embed.py --all
"""

import os
import json
import sqlite3
from pathlib import Path
from typing import List, Dict
from datetime import datetime
from dotenv import load_dotenv
import openai
from openai import OpenAI
import numpy as np
import faiss
from tqdm import tqdm

# Configuration
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
TRANSLATIONS_DIR = Path("translations")
EMBEDDINGS_DIR = Path("embeddings")
EMBEDDINGS_DIR.mkdir(exist_ok=True)

# OpenAI embedding model
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

# Inventories to process (excluding already completed 1120 and 3891)
ALL_INVENTORIES = [
    1267,
    1274,
    1419,
    1539,
    1547,
    1557,
    2448,
    2548,
    2555,
    2775,
    3142,
    7923,
    8023,
    8121,
    8237,
    8276,
    8284,
    8697,
    8834,
]


def get_openai_client() -> OpenAI:
    """Initialize OpenAI client."""
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set in environment")
    return OpenAI(api_key=api_key)


def import_translations_from_json(inv_nr: str) -> int:
    """Import translations from JSON file into database."""
    json_file = TRANSLATIONS_DIR / f"{inv_nr}_translations.json"

    if not json_file.exists():
        raise FileNotFoundError(f"Translation file not found: {json_file}")

    print(f"\n📥 Importing translations from {json_file}...")

    with open(json_file) as f:
        translations = json.load(f)

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        for trans in translations:
            cur.execute(
                """
                UPDATE documents 
                SET text_translated_detailed = ?,
                    text_translated_clean = ?,
                    translation_model = ?,
                    translation_date = ?
                WHERE rowid = ?
            """,
                (
                    trans["text_translated_detailed"],
                    trans["text_translated_clean"],
                    trans["translation_model"],
                    trans["translation_date"],
                    trans["rowid"],
                ),
            )

        conn.commit()

    print(f"✅ Imported {len(translations)} translations")
    return len(translations)


def load_or_create_embeddings(inv_nr: str, mode: str = "original") -> faiss.Index:
    """
    Load or create embeddings for an inventory.

    Args:
        inv_nr: Inventory number
        mode: "original" (Dutch text) or "translated" (English text)

    Returns:
        FAISS index
    """
    suffix = "_translated" if mode == "translated" else ""
    index_file = EMBEDDINGS_DIR / f"{inv_nr}{suffix}.index"

    # Load if exists
    if index_file.exists():
        print(f"📂 Loading existing FAISS index from {index_file}")
        index = faiss.read_index(str(index_file))
        print(f"✅ Loaded {index.ntotal} vectors")
        return index

    # Create new embeddings
    print(f"🧠 Generating {mode} embeddings for inventory {inv_nr}...")

    # Load texts from database
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if mode == "translated":
            cur.execute(
                """
                SELECT rowid, text_translated_clean as text
                FROM documents
                WHERE inv_nr = ?
                AND text_translated_clean IS NOT NULL
                ORDER BY rowid
            """,
                (inv_nr,),
            )
        else:
            cur.execute(
                """
                SELECT rowid, text
                FROM documents
                WHERE inv_nr = ?
                ORDER BY rowid
            """,
                (inv_nr,),
            )

        rows = cur.fetchall()
        texts = [row["text"] for row in rows]

    if not texts:
        raise ValueError(f"No texts found for inventory {inv_nr}, mode={mode}")

    print(f"   Found {len(texts)} texts to embed")

    # Generate embeddings in batches
    client = get_openai_client()
    embeddings = []
    batch_size = 20

    for i in tqdm(range(0, len(texts), batch_size)):
        batch = texts[i : i + batch_size]
        try:
            response = client.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            batch_embeddings = [item.embedding for item in response.data]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            # If batch fails (e.g., too long), try one at a time
            print(f"\n⚠️  Batch failed at index {i}, processing individually...")
            for j, text in enumerate(batch):
                try:
                    response = client.embeddings.create(
                        model=EMBEDDING_MODEL, input=[text]
                    )
                    embeddings.append(response.data[0].embedding)
                except Exception as e2:
                    # If still too long, truncate to safe limit (OpenAI limit is 8192 tokens)
                    print(
                        f"⚠️  Text at index {i + j} too long ({len(text)} chars), truncating to 15000 chars..."
                    )
                    truncated = text[:15000]  # ~3750 tokens, very safe
                    response = client.embeddings.create(
                        model=EMBEDDING_MODEL, input=[truncated]
                    )
                    embeddings.append(response.data[0].embedding)

    # Create FAISS index
    embeddings_array = np.array(embeddings, dtype="float32")
    index = faiss.IndexFlatL2(EMBEDDING_DIM)
    index.add(embeddings_array)

    # Save index
    faiss.write_index(index, str(index_file))
    print(f"💾 Saved FAISS index to {index_file}")
    print(f"✅ {mode.capitalize()} embeddings: {index.ntotal} vectors")

    return index


def process_inventory(inv_nr: int):
    """Import translations and generate embeddings for one inventory."""
    inv_nr_str = str(inv_nr)

    print(f"\n{'=' * 60}")
    print(f"📦 Processing inventory {inv_nr}")
    print(f"{'=' * 60}")

    # 1. Import translations
    try:
        count = import_translations_from_json(inv_nr_str)
    except FileNotFoundError as e:
        print(f"⚠️  Translation file not found, skipping: {e}")
        return False

    # 2. Generate original (Dutch) embeddings
    print(f"\n📊 Original (Dutch) embeddings...")
    original_index = load_or_create_embeddings(inv_nr_str, "original")

    # 3. Generate translated (English) embeddings
    print(f"\n📊 Translated (English) embeddings...")
    translated_index = load_or_create_embeddings(inv_nr_str, "translated")

    print(f"\n✨ Inventory {inv_nr} complete!")
    print(f"   Translations: {count}")
    print(f"   Original embeddings: {original_index.ntotal}")
    print(f"   Translated embeddings: {translated_index.ntotal}")

    return True


def process_all_inventories():
    """Process all remaining inventories."""
    print(f"\n🚀 Processing {len(ALL_INVENTORIES)} inventories")
    print(f"   Inventories: {ALL_INVENTORIES}\n")

    completed = []
    skipped = []

    for inv_nr in ALL_INVENTORIES:
        try:
            success = process_inventory(inv_nr)
            if success:
                completed.append(inv_nr)
            else:
                skipped.append(inv_nr)
        except Exception as e:
            print(f"❌ Error processing inventory {inv_nr}: {e}")
            skipped.append(inv_nr)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✅ PROCESSING COMPLETE")
    print(f"{'=' * 60}")
    print(f"   Completed: {len(completed)}/{len(ALL_INVENTORIES)}")
    if completed:
        print(f"   Success: {completed}")
    if skipped:
        print(f"   Skipped: {skipped}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Import translations and generate embeddings"
    )
    parser.add_argument("--inv-nr", type=int, help="Process single inventory")
    parser.add_argument("--all", action="store_true", help="Process all inventories")

    args = parser.parse_args()

    if args.all:
        process_all_inventories()
    elif args.inv_nr:
        process_inventory(args.inv_nr)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
