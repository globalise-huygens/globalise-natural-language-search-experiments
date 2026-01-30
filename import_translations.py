#!/usr/bin/env python3
"""
Import translations from JSON files into the SQLite database.

This script:
1. Adds translation columns to the database if needed
2. Imports translations from translations/ directory
3. Updates existing document rows with translated text

Run this after generating translations with translate_chunks.py
"""

from pathlib import Path
from app_core import import_translations_from_json


def main():
    translations_dir = Path("translations")

    if not translations_dir.exists():
        print("❌ translations/ directory not found")
        return

    # Find all translation JSON files
    json_files = sorted(translations_dir.glob("*_translations.json"))

    if not json_files:
        print("❌ No translation JSON files found in translations/")
        return

    print(f"\n📋 Found {len(json_files)} translation file(s):")
    for f in json_files:
        print(f"   - {f.name}")

    print(f"\n{'=' * 60}")
    print("🔄 Importing translations into database...")
    print(f"{'=' * 60}\n")

    total_imported = 0
    for json_file in json_files:
        try:
            count = import_translations_from_json(json_file)
            total_imported += count
            print()
        except Exception as e:
            print(f"❌ Error importing {json_file.name}: {e}\n")

    print(f"{'=' * 60}")
    print(f"✅ IMPORT COMPLETE: {total_imported} total translations imported")
    print(f"{'=' * 60}")
    print(f"\n📝 Next steps:")
    print(f"   1. Generate embeddings for translated text (Task 2)")
    print(f"   2. Update search logic (Task 3)")
    print(f"   3. Add UI toggle (Task 4)")


if __name__ == "__main__":
    main()
