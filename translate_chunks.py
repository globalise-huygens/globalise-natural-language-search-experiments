#!/usr/bin/env python3
"""
Translate VOC document chunks from archaic Dutch to modern English using Claude Haiku 4.5.

This script:
1. Reads chunks from the SQLite database
2. Translates them in batches using Claude Haiku 4.5
3. Stores two versions: detailed (with brackets) and clean (for embeddings)
4. Saves translations to a JSON file for inspection and later import to DB
5. Tracks progress and costs

Run with --sample flag first to test on one inventory number before full translation.
"""

import os
import json
import sqlite3
import re
import math
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
from dotenv import load_dotenv
import anthropic

# --- Configuration ---
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
TRANSLATIONS_DIR = Path("translations")
TRANSLATIONS_DIR.mkdir(exist_ok=True)

# Claude Haiku 4.5 pricing (as of Jan 2026)
# https://www.anthropic.com/pricing
HAIKU_INPUT_PRICE = 0.80 / 1_000_000  # $0.80 per MTok
HAIKU_OUTPUT_PRICE = 4.00 / 1_000_000  # $4.00 per MTok

# Translation prompt optimized for VOC documents
TRANSLATION_PROMPT = """You are an expert translator specializing in Dutch East India Company (VOC) documents, written in early modern Dutch (17th-18th century) in an Asian, early colonial context.

**CORE PRINCIPLES:**
1. Translate ALL text completely - do not summarize, condense, or omit ANY content
2. Produce NATURAL, READABLE ENGLISH while remaining completely accurate to the original meaning
3. Do NOT ask for permission or add meta-commentary - just translate everything
4. Translate each chunk fully without stopping

Translate the entire text provided into modern English, paying careful attention to:

1. Historical context and specific terminology related to the VOC and its operations in early modern Asia
2. Archaic Dutch language patterns, sentence structure, and vocabulary
3. Period-appropriate titles, ranks, and administrative terms

**Translation Guidelines:**
- Translate every word's meaning completely and accurately
- Use natural, flowing English sentences rather than awkward word-by-word constructions
- Maintain logical paragraph and sentence breaks for readability
- Preserve proper names, ship names, and place names as they appear in the text; add normalized names (or modern equivalents), if known, between brackets [normalized version:]
- If known, add modern English equivalents for outdated measurements, currencies, and terms between brackets [modern equivalent:]
- When uncertain about specific words or phrases, indicate this with [uncertain: original text]
- For completely illegible or damaged text, use [illegible] or [damaged text]
- For abbreviations, expand them with the full term in brackets if helpful [expanded: full term]
- For words with no direct modern equivalent, provide the original Dutch term with an explanatory note in brackets
- Translate even mid-sentence fragments completely

**BOUNDARY MARKER PRESERVATION (CRITICAL):**
- NEVER merge or combine multiple chunks into a single response
- ALWAYS include the exact separator `--- CHUNK X ---` IMMEDIATELY BEFORE each translated chunk
- Each chunk MUST have its own unique marker with the correct chunk number
- Example format: `--- CHUNK 1 ---\n[translation of chunk 1]\n--- CHUNK 2 ---\n[translation of chunk 2]`
- VERIFY that the number of chunks in your response matches the number of input chunks
- If you notice yourself combining text that belongs to separate chunks, STOP and re-translate with proper separation

**IMPORTANT:**
- This is NOT a word-for-word mechanical translation - use natural English that sounds like a fluent translation
- Group related information logically and use paragraph breaks where appropriate
- Maintain accuracy to original meaning while ensuring the English is clear and readable
- DO NOT SKIP OR IGNORE THE BOUNDARY MARKERS - they are essential for parsing

**ABSOLUTELY FORBIDDEN:**
- Do NOT summarize ("Details the financial situation...")
- Do NOT ask for continuation ("Would you like me to continue?")
- Do NOT add translator notes ("[Note: This is...]")
- Do NOT create artificial literal constructions that sound unnatural
- Do NOT merge consecutive chunks - each must have its marker and remain separate

Please translate the following text:"""


def remove_brackets_content(text: str) -> str:
    """
    Remove bracketed additions from translation to create clean version for embeddings.
    Preserves the content inside brackets but removes the brackets themselves.
    Example: "Amsterdam [normalized version: Batavia]" -> "Amsterdam Batavia"
    """

    # Extract content from brackets and append without brackets
    def replace_bracket(match):
        content = match.group(1)
        # Remove the label prefix if present (e.g., "normalized version:", "modern equivalent:")
        content = re.sub(r"^[^:]+:\s*", "", content)
        return f" {content}"

    # Replace all bracketed content
    clean = re.sub(r"\[([^\]]+)\]", replace_bracket, text)
    # Clean up multiple spaces
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def estimate_tokens(text: str) -> int:
    """Rough estimate: ~4 characters per token for Dutch/English."""
    return len(text) // 4


def get_anthropic_client() -> anthropic.Anthropic:
    """Initialize Anthropic client with API key from environment."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "ANTHROPIC_API_KEY not set. Create a .env file or export the variable."
        )
    return anthropic.Anthropic(api_key=api_key)


def preprocess_text(text: str) -> str:
    """
    Preprocess text before translation:
    - Replace recurring punctuation marks (with or without spaces) with a single one.
    - E.g., '. . .' or '..' becomes '.', '- -' becomes '-', etc.
    - Handles both ASCII dashes and Unicode dashes (en-dash, em-dash)
    """
    # Pattern: any punctuation character followed by spaces and the same character (1+ more times)
    # Matches: . . or .. or . . . or - - or -- etc.
    text = re.sub(r"([\.\.\-\/,;:])([\ s]*\1)+", r"\1", text)  # ASCII punctuation
    text = re.sub(
        r"([–—])([\ s]*\1)+", r"\1", text
    )  # Unicode dashes (U+2013 en-dash, U+2014 em-dash)
    return text


def load_chunks_from_db(inv_nr: str = None) -> List[Dict]:
    """
    Load chunks from database. If inv_nr specified, load only that inventory.
    Returns list of dicts with chunk data.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Database not found at {DB_PATH}. Run precompute_embeddings.py first."
        )

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        if inv_nr:
            query = "SELECT rowid, * FROM documents WHERE inv_nr = ? ORDER BY rowid"
            cur.execute(query, (inv_nr,))
        else:
            query = "SELECT rowid, * FROM documents ORDER BY inv_nr, rowid"
            cur.execute(query)

        rows = cur.fetchall()
        return [dict(row) for row in rows]


def translate_batch(
    client: anthropic.Anthropic, chunks: List[Dict], batch_size: int = 10
) -> Tuple[List[Dict], Dict]:
    """
    Translate a batch of chunks.
    Returns: (translated_chunks, stats_dict)
    """
    if not chunks:
        return [], {}

    # Build batch prompt with clear instructions to preserve headers
    batch_prompt = f"""{TRANSLATION_PROMPT}

**CRITICAL FORMATTING INSTRUCTION**: 
You must translate each chunk and preserve the exact "--- CHUNK X ---" header before each translation.
Output format:
--- CHUNK 1 ---
[translation of chunk 1]

--- CHUNK 2 ---
[translation of chunk 2]

etc.

Here are the chunks to translate:

"""

    for i, chunk in enumerate(chunks):
        preprocessed_text = preprocess_text(chunk["text"])
        batch_prompt += f"--- CHUNK {i + 1} ---\n{preprocessed_text}\n\n"

    # Translate
    try:
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",  # Haiku 4.5
            max_tokens=16000,
            temperature=0,
            messages=[{"role": "user", "content": batch_prompt}],
        )

        translation_output = message.content[0].text

        # Debug: Save raw output for first batch
        if chunks[0]["rowid"] <= 10:
            debug_file = TRANSLATIONS_DIR / "debug_output.txt"
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write("=== RAW TRANSLATION OUTPUT ===\n")
                f.write(translation_output)
                f.write("\n\n=== END OUTPUT ===\n")

        # Parse output back into individual chunks
        # Split by "--- CHUNK X ---" pattern (more flexible regex)
        chunk_pattern = (
            r"---\s*CHUNK\s+(\d+)\s*---\s*(.*?)(?=---\s*CHUNK\s+\d+\s*---|$)"
        )
        matches = re.findall(
            chunk_pattern, translation_output, re.DOTALL | re.IGNORECASE
        )

        translations = {}
        for chunk_num, translation in matches:
            translations[int(chunk_num)] = translation.strip()

        # If parsing failed, try alternative: assume sequential order without headers
        if len(translations) == 0 and len(chunks) == 1:
            # Single chunk - just use the whole output
            translations[1] = translation_output.strip()

        # Build results with both versions
        results = []
        for i, chunk in enumerate(chunks):
            chunk_num = i + 1
            if chunk_num in translations:
                detailed = translations[chunk_num]
                clean = remove_brackets_content(detailed)

                results.append(
                    {
                        "rowid": chunk["rowid"],
                        "inv_nr": chunk["inv_nr"],
                        "tanap_id": chunk["tanap_id"],
                        "chunk_id": chunk["chunk_id"],
                        "text_original": chunk["text"],
                        "text_translated_detailed": detailed,
                        "text_translated_clean": clean,
                        "translation_model": "claude-haiku-4-5-20251001",
                        "translation_date": datetime.now().isoformat(),
                    }
                )
            else:
                # Translation failed for this chunk
                print(
                    f"⚠️  Warning: No translation found for chunk {chunk_num} (rowid {chunk['rowid']})"
                )
                print(f"    Found translations for chunks: {list(translations.keys())}")

        # Calculate stats
        stats = {
            "input_tokens": message.usage.input_tokens,
            "output_tokens": message.usage.output_tokens,
            "input_cost": message.usage.input_tokens * HAIKU_INPUT_PRICE,
            "output_cost": message.usage.output_tokens * HAIKU_OUTPUT_PRICE,
        }

        return results, stats

    except Exception as e:
        print(f"❌ Translation error: {e}")
        import traceback

        traceback.print_exc()
        return [], {}


def save_translations_json(translations: List[Dict], inv_nr: str):
    """Save translations to JSON file for review and later import."""
    output_file = TRANSLATIONS_DIR / f"{inv_nr}_translations.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(translations, f, indent=2, ensure_ascii=False)
    print(f"   💾 Saved to {output_file}")


def load_existing_translations(inv_nr: str) -> Dict[int, Dict]:
    """Load existing translations from JSON file if present. Returns dict keyed by rowid."""
    json_file = TRANSLATIONS_DIR / f"{inv_nr}_translations.json"
    if json_file.exists():
        with open(json_file, "r", encoding="utf-8") as f:
            translations = json.load(f)
            return {t["rowid"]: t for t in translations}
    return {}


def list_available_inv_nrs() -> List[str]:
    """Get list of all inventory numbers in the database."""
    if not DB_PATH.exists():
        return []

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT inv_nr FROM documents ORDER BY inv_nr")
        return [row[0] for row in cur.fetchall()]


def translate_inventory(
    client: anthropic.Anthropic,
    inv_nr: str,
    batch_size: int = 10,
    resume: bool = True,
    delay: float = 0,
) -> Dict:
    """
    Translate all chunks for one inventory number.
    Returns summary statistics.

    Args:
        delay: Seconds to wait between batches (for rate limiting, default 0)
    """
    import time

    print(f"\n{'=' * 60}")
    print(f"📚 Processing inventory: {inv_nr}")
    print(f"{'=' * 60}")

    # Load chunks
    chunks = load_chunks_from_db(inv_nr)
    print(f"   Found {len(chunks)} chunks")

    # Check for existing translations
    existing = {}
    if resume:
        existing = load_existing_translations(inv_nr)
        if existing:
            print(f"   ✓ Found {len(existing)} existing translations (will skip)")

    # Filter out already translated
    chunks_to_translate = [c for c in chunks if c["rowid"] not in existing]

    if not chunks_to_translate:
        print(f"   ✓ All chunks already translated!")
        return {"skipped": len(chunks), "translated": 0, "cost": 0}

    print(
        f"   🔄 Translating {len(chunks_to_translate)} chunks in batches of {batch_size}"
    )
    if delay > 0:
        print(f"   ⏱️  Rate limiting: {delay}s delay between batches")

    # Translate in batches
    all_translations = list(existing.values())
    total_cost = 0
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(0, len(chunks_to_translate), batch_size):
        batch = chunks_to_translate[i : i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(chunks_to_translate) + batch_size - 1) // batch_size

        print(f"   Batch {batch_num}/{total_batches} ({len(batch)} chunks)...", end=" ")

        translated, stats = translate_batch(client, batch, batch_size)

        if translated:
            all_translations.extend(translated)
            batch_cost = stats["input_cost"] + stats["output_cost"]
            total_cost += batch_cost
            total_input_tokens += stats["input_tokens"]
            total_output_tokens += stats["output_tokens"]

            print(f"✓ ${batch_cost:.4f}")

            # Save after each batch (for resume capability)
            save_translations_json(all_translations, inv_nr)

            # Rate limiting delay between batches (skip on last batch)
            if delay > 0 and batch_num < total_batches:
                time.sleep(delay)
        else:
            print("✗ Failed")

    # Final summary
    summary = {
        "inv_nr": inv_nr,
        "total_chunks": len(chunks),
        "skipped": len(existing),
        "translated": len(chunks_to_translate),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_cost": total_cost,
    }

    print(f"\n   {'─' * 50}")
    print(f"   ✅ Complete: {summary['translated']} chunks translated")
    print(f"   💰 Cost: ${summary['total_cost']:.4f}")
    print(
        f"   📊 Tokens: {summary['input_tokens']:,} in / {summary['output_tokens']:,} out"
    )

    return summary


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Translate VOC document chunks using Claude Haiku 4.5"
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="Translate only the first inventory number as a sample",
    )
    parser.add_argument(
        "--inv-nr", type=str, help='Translate specific inventory number (e.g., "1120")'
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="Number of chunks per API call (default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0,
        help="Seconds to delay between batches for rate limiting (default: 0)",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Start fresh (ignore existing translations)",
    )

    args = parser.parse_args()

    # Initialize client
    try:
        client = get_anthropic_client()
        print("✅ Anthropic client initialized (Claude Haiku 4.5)")
    except ValueError as e:
        print(f"❌ {e}")
        return

    # Check database
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        print("   Run this first: python precompute_embeddings.py")
        return

    # Determine which inventories to process
    inv_nrs = list_available_inv_nrs()
    if not inv_nrs:
        print("❌ No inventory numbers found in database")
        return

    print(f"\n📋 Found {len(inv_nrs)} inventory numbers in database")

    if args.inv_nr:
        if args.inv_nr not in inv_nrs:
            print(f"❌ Inventory {args.inv_nr} not found")
            return
        inv_nrs = [args.inv_nr]
        print(f"🎯 Processing single inventory: {args.inv_nr}")
    elif args.sample:
        inv_nrs = [inv_nrs[0]]
        print(f"🧪 Sample mode: processing first inventory ({inv_nrs[0]})")
    else:
        print(f"🔄 Processing all {len(inv_nrs)} inventories")

    # Estimate total cost (input + output tokens)
    total_chunks = 0
    total_batches = 0
    input_text_tokens = 0
    estimated_input_tokens = 0
    for inv in inv_nrs:
        chunks = load_chunks_from_db(inv)
        existing = load_existing_translations(inv) if not args.no_resume else {}
        chunks_to_translate = [c for c in chunks if c["rowid"] not in existing]
        total_chunks += len(chunks_to_translate)
        total_batches += math.ceil(len(chunks_to_translate) / args.batch_size)
        chunk_text_tokens = sum(
            estimate_tokens(preprocess_text(c["text"])) for c in chunks_to_translate
        )
        input_text_tokens += chunk_text_tokens
        estimated_input_tokens += chunk_text_tokens

    # Add prompt overhead per batch + chunk header markers
    batch_prompt_overhead = estimate_tokens(TRANSLATION_PROMPT) + estimate_tokens(
        """

**CRITICAL FORMATTING INSTRUCTION**: 
You must translate each chunk and preserve the exact "--- CHUNK X ---" header before each translation.
Output format:
--- CHUNK 1 ---
[translation of chunk 1]

--- CHUNK 2 ---
[translation of chunk 2]

etc.

Here are the chunks to translate:

"""
    )
    chunk_header_tokens = estimate_tokens("--- CHUNK 1 ---\n")
    estimated_input_tokens += total_batches * batch_prompt_overhead
    estimated_input_tokens += total_chunks * chunk_header_tokens

    estimated_output_tokens = int(
        input_text_tokens * 1.2
    )  # Translations slightly longer
    estimated_input_cost = estimated_input_tokens * HAIKU_INPUT_PRICE
    estimated_output_cost = estimated_output_tokens * HAIKU_OUTPUT_PRICE
    estimated_cost = estimated_input_cost + estimated_output_cost

    print(
        f"\n💰 Estimated cost: ${estimated_cost:.2f} for {total_chunks} chunks"
        f" (input: ${estimated_input_cost:.2f}, output: ${estimated_output_cost:.2f})"
    )

    if not args.sample and not args.inv_nr:
        response = input("\nProceed with full translation? (yes/no): ")
        if response.lower() not in ["yes", "y"]:
            print("Cancelled.")
            return

    # Process each inventory
    all_summaries = []
    for inv_nr in inv_nrs:
        summary = translate_inventory(
            client,
            inv_nr,
            batch_size=args.batch_size,
            resume=not args.no_resume,
            delay=args.delay,
        )
        all_summaries.append(summary)

    # Final summary
    print(f"\n{'=' * 60}")
    print("🎉 TRANSLATION COMPLETE")
    print(f"{'=' * 60}")

    total_translated = sum(s["translated"] for s in all_summaries)
    total_cost = sum(s["total_cost"] for s in all_summaries)
    total_skipped = sum(s["skipped"] for s in all_summaries)

    print(f"✅ Translated: {total_translated} chunks")
    if total_skipped:
        print(f"⏭️  Skipped: {total_skipped} chunks (already done)")
    print(f"💰 Total cost: ${total_cost:.2f}")
    print(f"\n📁 Translations saved to: {TRANSLATIONS_DIR.absolute()}/")

    print(f"\n📝 Next steps:")
    print(f"   1. Review translations in {TRANSLATIONS_DIR}/ directory")
    print(f"   2. Check quality of both detailed and clean versions")
    print(f"   3. Run without --sample flag to translate all inventories")
    print(f"   4. Update database schema to store translations")
    print(f"   5. Generate embeddings from translated text")


if __name__ == "__main__":
    main()
