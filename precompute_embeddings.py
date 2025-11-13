#!/usr/bin/env python3
"""
Precompute all FAISS embeddings for deployment to Streamlit Cloud.

This script:
1. Ensures the database exists
2. Lists all inventory numbers
3. Generates embeddings for each one (if not already present)
4. Saves them to the embeddings/ directory

Run this locally before deploying to Streamlit Cloud.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from app_core import (
    get_openai_client,
    list_available_inv_nrs,
    load_or_create_embeddings,
    ensure_database_from_text_inputs,
    DB_PATH,
)

def main():
    load_dotenv()
    
    # Check API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY not found in environment or .env file")
        print("   Please set it before running this script.")
        return
    
    client = get_openai_client()
    print("✅ OpenAI client initialized\n")
    
    # Ensure database exists
    if not DB_PATH.exists():
        print("📦 Database not found. Building from text-input/...")
        total_chunks = ensure_database_from_text_inputs(
            apply_normalization=True,
            chunk_size=500,
            overlap=100
        )
        print(f"✅ Database built with {total_chunks} chunks\n")
    else:
        print(f"✅ Database found at {DB_PATH}\n")
    
    # Get all inventory numbers
    inv_nrs = list_available_inv_nrs()
    print(f"📋 Found {len(inv_nrs)} inventory numbers: {', '.join(inv_nrs[:10])}{'...' if len(inv_nrs) > 10 else ''}\n")
    
    # Process each inventory number
    for i, inv_nr in enumerate(inv_nrs, 1):
        print(f"[{i}/{len(inv_nrs)}] Processing {inv_nr}...")
        try:
            faiss_idx, chunks = load_or_create_embeddings(inv_nr, client)
            print(f"    ✅ {len(chunks)} chunks, {faiss_idx.ntotal} embeddings")
        except Exception as e:
            print(f"    ❌ Error: {e}")
    
    print(f"\n🎉 All embeddings precomputed!")
    print(f"   Database: {DB_PATH}")
    print(f"   Embeddings: {Path('embeddings').absolute()}")
    print("\n📝 Next steps:")
    print("   1. Commit embeddings/ and text-metadata-sqlite/ to git")
    print("   2. Push to GitHub")
    print("   3. Deploy to Streamlit Cloud")

if __name__ == "__main__":
    main()
