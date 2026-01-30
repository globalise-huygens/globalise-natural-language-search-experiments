#!/usr/bin/env python3
"""Import all 3891 translations and regenerate embeddings"""

import os
from pathlib import Path

# Load environment
from dotenv import load_dotenv

load_dotenv()

from openai import OpenAI
from app_core import import_translations_from_json, load_or_create_embeddings


def main():
    # Import all translations
    print("📥 Importing 583 translations from 3891_translations.json...")
    translations_file = Path("translations/3891_translations.json")
    result = import_translations_from_json(translations_file)
    print(f"✅ {result}")

    # Initialize OpenAI client for embeddings
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    client = OpenAI(api_key=api_key)

    # Generate embeddings
    print("\n🧠 Generating embeddings for 3891...\n")

    # Original Dutch embeddings
    print("📊 Original (Dutch) embeddings...")
    result_orig = load_or_create_embeddings(
        "3891", client, mode="original", use_cache=False
    )
    print(f"✅ {result_orig}")

    # Translated English embeddings
    print("\n📊 Translated (English) embeddings...")
    result_trans = load_or_create_embeddings(
        "3891", client, mode="translated", use_cache=False
    )
    print(f"✅ {result_trans}")

    print("\n✨ All 3891 translations and embeddings ready!")


if __name__ == "__main__":
    main()
