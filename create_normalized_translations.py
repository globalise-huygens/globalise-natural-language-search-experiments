#!/usr/bin/env python3
"""
Create normalized translations that only use the English terms from brackets.

Instead of: "Bewinthebberen [Directors/Shareholders]" → "Bewinthebberen Directors/Shareholders"
We want: "Bewinthebberen [Directors/Shareholders]" → "Directors/Shareholders"

This reduces verbosity and keeps only standardized English terminology.
"""

import sqlite3
import re
from pathlib import Path
from tqdm import tqdm

DB_PATH = Path("text-metadata-sqlite/voc_documents.db")


def normalize_translation(text: str) -> str:
    """
    Extract only the normalized English terms from brackets.

    Examples:
    - "Taijuan [Taiwan]" → "Taiwan"
    - "Bewinthebberen [Directors/Shareholders]" → "Directors/Shareholders"
    - "unclear text [unclear]" → "unclear"
    - "some text without brackets" → "some text without brackets"
    """
    if not text or text is None:
        return text if text is not None else ""


def process_all_inventories():
    """Process all inventories and create normalized translations."""

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Add new column if it doesn't exist
    try:
        cursor.execute(
            "ALTER TABLE documents ADD COLUMN text_translated_normalized TEXT"
        )
        print("✅ Added text_translated_normalized column")
    except sqlite3.OperationalError:
        print("ℹ️  text_translated_normalized column already exists")

    # Get all documents with translations
    cursor.execute("""
        SELECT rowid, inv_nr, text_translated_detailed 
        FROM documents 
        WHERE text_translated_detailed IS NOT NULL
    """)

    rows = cursor.fetchall()
    print(f"\n📊 Processing {len(rows):,} documents...\n")

    # Show a few examples before processing
    print("Examples of normalization:")
    print("-" * 80)
    for i, (rowid, inv_nr, detailed) in enumerate(rows[:3]):
        normalized = normalize_translation(detailed)
        print(f"\nInventory {inv_nr}, Row {rowid}:")
        print(f"Detailed: {detailed[:150]}...")
        print(f"Normalized: {normalized[:150]}...")
    print("-" * 80)

    proceed = input("\nProceed with normalization? (y/n): ").strip().lower()
    if proceed != "y":
        print("Cancelled.")
        conn.close()
        return

    # Process all rows
    updated = 0
    for rowid, inv_nr, detailed in tqdm(rows, desc="Normalizing"):
        normalized = normalize_translation(detailed)

        cursor.execute(
            """
            UPDATE documents 
            SET text_translated_normalized = ? 
            WHERE rowid = ?
        """,
            (normalized, rowid),
        )
        updated += 1

    conn.commit()

    # Show statistics
    cursor.execute("""
        SELECT 
            COUNT(*) as total,
            AVG(LENGTH(text_translated_detailed)) as avg_detailed,
            AVG(LENGTH(text_translated_normalized)) as avg_normalized,
            MAX(LENGTH(text_translated_normalized)) as max_normalized
        FROM documents 
        WHERE text_translated_detailed IS NOT NULL
    """)

    total, avg_detailed, avg_normalized, max_normalized = cursor.fetchone()

    print(f"\n✅ Updated {updated:,} documents")
    print(f"\n📊 Statistics:")
    print(f"   Average length (detailed): {avg_detailed:.0f} chars")
    print(f"   Average length (normalized): {avg_normalized:.0f} chars")
    print(f"   Reduction: {(1 - avg_normalized / avg_detailed) * 100:.1f}%")
    print(f"   Max normalized length: {max_normalized:,} chars")

    conn.close()


if __name__ == "__main__":
    process_all_inventories()
