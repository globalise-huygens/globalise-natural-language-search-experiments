#!/usr/bin/env python3
"""Retry translating the 5 missing chunks with batch_size=1"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime

from translate_chunks import (
    get_anthropic_client,
    translate_batch,
    remove_brackets_content,
    preprocess_text,
)


def main():
    # Connect to database
    db_path = Path("text-metadata-sqlite/voc_documents.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the 5 missing chunks
    missing_rowids = [15155, 15156, 15157, 15158, 15159]
    cursor.execute(
        f"SELECT rowid, inv_nr, tanap_id, chunk_id, text FROM documents WHERE rowid IN ({','.join('?' * len(missing_rowids))})",
        missing_rowids,
    )
    chunks = cursor.fetchall()

    print(f"🔄 Retrying {len(chunks)} missing chunks with batch_size=1...\n")

    # Load existing translations
    translations_file = Path("translations/3891_translations.json")
    existing = json.loads(translations_file.read_text())
    print(f"   Loaded {len(existing)} existing translations")

    # Translate each missing chunk with batch_size=1
    client = get_anthropic_client()
    total_cost = 0
    successful = 0

    for row in chunks:
        chunk_id = row["chunk_id"]
        rowid = row["rowid"]

        print(f"   Retrying chunk {chunk_id} (rowid {rowid})...")

        try:
            # Translate this single chunk (convert to dict format expected by translate_batch)
            chunk_dict = {
                "rowid": rowid,
                "inv_nr": row["inv_nr"],
                "tanap_id": row["tanap_id"],
                "chunk_id": chunk_id,
                "text": row["text"],
            }

            results, stats = translate_batch(client, [chunk_dict], batch_size=1)

            if results:
                trans_entry = results[0]
                total_cost += stats.get("cost", 0)

                # Add to existing translations
                existing.append(trans_entry)
                print(f"      ✓ Translated successfully (${stats.get('cost', 0):.4f})")
                successful += 1
            else:
                print(f"      ✗ Failed - no translation in response")
        except Exception as e:
            print(f"      ✗ Error: {e}")

    # Save all translations back
    translations_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    print(f"\n{'─' * 50}")
    print(f"✅ Retry complete")
    print(f"   Successfully retried: {successful}/{len(chunks)}")
    print(f"   Total cost: ${total_cost:.4f}")
    print(f"   Total translations: {len(existing)}/583")

    conn.close()


if __name__ == "__main__":
    main()
