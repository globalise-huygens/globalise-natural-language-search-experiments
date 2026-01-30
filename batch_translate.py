#!/usr/bin/env python3
"""
Translate VOC document chunks using Anthropic's Batch API with prompt caching.

This provides 90%+ cost savings by combining:
1. Prompt caching (90% discount on cached system prompts)
2. Batch API (50% discount on all tokens during off-peak processing)

Combined pricing for Haiku 4.5:
- Cached input: $0.02/MTok (vs $0.80/MTok regular)
- Regular input: $0.40/MTok (vs $0.80/MTok regular)
- Output: $2.00/MTok (vs $4.00/MTok regular)

Usage:
1. Create batch: python batch_translate.py create --inv-nr 1120
2. Submit batch: python batch_translate.py submit --batch-file batches/batch_1120.jsonl
3. Check status: python batch_translate.py status --batch-id <id>
4. Download results: python batch_translate.py download --batch-id <id>
5. Process results: python batch_translate.py process --results-file results/batch_1120_results.jsonl
"""

import os
import json
import sqlite3
import re
import time
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
from dotenv import load_dotenv
import anthropic

# --- Configuration ---
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
BATCHES_DIR = Path("batches")
BATCHES_DIR.mkdir(exist_ok=True)
BATCH_RESULTS_DIR = Path("batch_results")
BATCH_RESULTS_DIR.mkdir(exist_ok=True)
TRANSLATIONS_DIR = Path("translations")
TRANSLATIONS_DIR.mkdir(exist_ok=True)

# Batch API pricing for Haiku 4.5 (50% off regular prices)
BATCH_HAIKU_INPUT_PRICE = 0.40 / 1_000_000  # $0.40 per MTok (50% off $0.80)
BATCH_HAIKU_CACHED_INPUT_PRICE = 0.02 / 1_000_000  # $0.02 per MTok (50% off $0.04)
BATCH_HAIKU_OUTPUT_PRICE = 2.00 / 1_000_000  # $2.00 per MTok (50% off $4.00)

# Translation prompt - will be cached across all requests
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
- Do NOT merge consecutive chunks - each must have its marker and remain separate"""


def preprocess_text(text: str) -> str:
    """Preprocess text before translation."""
    # Collapse repeated punctuation (with optional spaces between)
    # Handles ASCII dash (-), en-dash (–), em-dash (—), and other punctuation
    text = re.sub(r"([\.\.\-\/,;:])([\ s]*\1)+", r"\1", text)  # ASCII punctuation
    text = re.sub(r"([–—])([\ s]*\1)+", r"\1", text)  # Unicode dashes (U+2013, U+2014)
    return text


def remove_brackets_content(text: str) -> str:
    """Remove bracketed additions for clean version."""

    def replace_bracket(match):
        content = match.group(1)
        content = re.sub(r"^[^:]+:\s*", "", content)
        return f" {content}"

    clean = re.sub(r"\[([^\]]+)\]", replace_bracket, text)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


def get_anthropic_client() -> anthropic.Anthropic:
    """Initialize Anthropic client."""
    load_dotenv()
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in environment")
    return anthropic.Anthropic(api_key=api_key)


def load_chunks_from_db(inv_nr: str) -> List[Dict]:
    """Load all chunks for a specific inventory number."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT rowid, * FROM documents WHERE inv_nr = ? ORDER BY rowid", (inv_nr,)
        )
        rows = cur.fetchall()
        return [dict(row) for row in rows]


def create_batch_file(inv_nr: str, batch_size: int = 5) -> Path:
    """
    Create a JSONL batch file for an inventory with prompt caching.

    Each request uses cache_control on the system prompt so it's cached
    across all requests in the batch.
    """
    print(f"\n📦 Creating batch file for inventory {inv_nr}...")

    # Load chunks
    chunks = load_chunks_from_db(inv_nr)
    if not chunks:
        raise ValueError(f"No chunks found for inventory {inv_nr}")

    print(f"   Found {len(chunks)} chunks")

    # Group into batches
    num_batches = (len(chunks) + batch_size - 1) // batch_size
    print(f"   Creating {num_batches} batch requests (batch_size={batch_size})")

    # Create JSONL file
    batch_file = BATCHES_DIR / f"batch_{inv_nr}.jsonl"
    requests = []

    for batch_idx in range(num_batches):
        start_idx = batch_idx * batch_size
        end_idx = min(start_idx + batch_size, len(chunks))
        batch_chunks = chunks[start_idx:end_idx]

        # Build user prompt with chunks
        user_prompt = f"""**CRITICAL FORMATTING INSTRUCTION**: 
You must translate each chunk and preserve the exact "--- CHUNK X ---" header before each translation.
Output format:
--- CHUNK 1 ---
[translation of chunk 1]

--- CHUNK 2 ---
[translation of chunk 2]

etc.

Here are the chunks to translate:

"""

        for i, chunk in enumerate(batch_chunks):
            preprocessed = preprocess_text(chunk["text"])
            user_prompt += f"--- CHUNK {i + 1} ---\n{preprocessed}\n\n"

        # Create request with prompt caching on system message
        request = {
            "custom_id": f"inv{inv_nr}_batch{batch_idx}_chunks{start_idx}-{end_idx - 1}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 16000,
                "temperature": 0,
                "system": [
                    {
                        "type": "text",
                        "text": TRANSLATION_PROMPT,
                        "cache_control": {
                            "type": "ephemeral"
                        },  # Cache the system prompt!
                    }
                ],
                "messages": [{"role": "user", "content": user_prompt}],
            },
        }

        requests.append(request)

    # Write JSONL file
    with open(batch_file, "w") as f:
        for req in requests:
            f.write(json.dumps(req) + "\n")

    print(f"✅ Created batch file: {batch_file}")
    print(f"   {len(requests)} requests ready to submit")

    # Estimate costs
    # First request pays full price for system prompt, rest pay cached price
    system_tokens = len(TRANSLATION_PROMPT) // 4  # rough estimate
    print(f"\n💰 Estimated cost savings:")
    print(f"   System prompt: ~{system_tokens:,} tokens")
    print(f"   - First request: ${system_tokens * BATCH_HAIKU_INPUT_PRICE:.4f}")
    print(
        f"   - Remaining {len(requests) - 1} requests: ${(len(requests) - 1) * system_tokens * BATCH_HAIKU_CACHED_INPUT_PRICE:.4f}"
    )
    print(
        f"   - Total system prompt cost: ${system_tokens * BATCH_HAIKU_INPUT_PRICE + (len(requests) - 1) * system_tokens * BATCH_HAIKU_CACHED_INPUT_PRICE:.4f}"
    )
    print(
        f"   - Without caching would be: ${len(requests) * system_tokens * BATCH_HAIKU_INPUT_PRICE:.4f}"
    )

    return batch_file


def submit_batch(batch_file: Path) -> str:
    """Submit a batch file to Anthropic's Batch API."""
    print(f"\n🚀 Submitting batch file: {batch_file}")

    client = get_anthropic_client()

    # Load requests from JSONL file
    print("   Loading requests...")
    requests = []
    with open(batch_file, "r") as f:
        for line in f:
            if line.strip():
                requests.append(json.loads(line))

    print(f"   Submitting {len(requests)} requests...")
    uploaded_file = client.beta.messages.batches.create(requests=requests)

    batch_id = uploaded_file.id
    print(f"✅ Batch submitted successfully!")
    print(f"   Batch ID: {batch_id}")
    print(f"   Status: {uploaded_file.processing_status}")
    print(f"\n📝 Save this batch ID to check status later")
    print(f"   Check status: python batch_translate.py status --batch-id {batch_id}")

    # Save batch metadata
    metadata_file = BATCHES_DIR / f"{batch_file.stem}_metadata.json"
    metadata = {
        "batch_id": batch_id,
        "batch_file": str(batch_file),
        "submitted_at": datetime.now().isoformat(),
        "status": uploaded_file.processing_status,
    }
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"   Metadata saved to: {metadata_file}")

    return batch_id


def check_status(batch_id: str) -> Dict:
    """Check the status of a batch job."""
    print(f"\n🔍 Checking status for batch: {batch_id}")

    client = get_anthropic_client()
    batch = client.beta.messages.batches.retrieve(batch_id)

    print(f"\n📊 Batch Status:")
    print(f"   Status: {batch.processing_status}")
    print(f"   Created: {batch.created_at}")
    print(f"   Requests: {batch.request_counts}")

    if batch.processing_status == "ended":
        print(f"\n✅ Batch processing complete!")
        print(
            f"   Download results: python batch_translate.py download --batch-id {batch_id}"
        )
    elif batch.processing_status == "in_progress":
        print(f"\n⏳ Batch still processing...")
        print(f"   Check again in a few minutes")
    elif batch.processing_status == "failed":
        print(f"\n❌ Batch processing failed")

    return batch


def download_results(batch_id: str) -> Optional[Path]:
    """Download results from a completed batch."""
    print(f"\n⬇️  Downloading results for batch: {batch_id}")

    client = get_anthropic_client()
    batch = client.beta.messages.batches.retrieve(batch_id)

    if batch.processing_status != "ended":
        print(f"❌ Batch not yet complete (status: {batch.processing_status})")
        return None

    # Get results
    print("   Fetching results...")
    results = client.beta.messages.batches.results(batch_id)

    # Save to file
    results_file = BATCH_RESULTS_DIR / f"batch_{batch_id}_results.jsonl"
    with open(results_file, "w") as f:
        for result in results:
            f.write(json.dumps(result.to_dict()) + "\n")

    print(f"✅ Results downloaded: {results_file}")
    print(
        f"   Process results: python batch_translate.py process --results-file {results_file}"
    )

    return results_file


def process_results(results_file: Path, inv_nr: str) -> None:
    """Process batch results and create translations JSON file."""
    print(f"\n⚙️  Processing results from: {results_file}")

    # Load all chunks from DB
    chunks = load_chunks_from_db(inv_nr)
    chunks_by_rowid = {chunk["rowid"]: chunk for chunk in chunks}

    # Load results
    results = []
    with open(results_file) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))

    print(f"   Found {len(results)} batch results")

    # Process each result
    translations = []
    total_input_tokens = 0
    total_cached_tokens = 0
    total_output_tokens = 0

    for result in results:
        custom_id = result["custom_id"]

        # Parse custom_id to get chunk range
        # Format: inv{inv_nr}_batch{idx}_chunks{start}-{end}
        match = re.match(r"inv(\d+)_batch(\d+)_chunks(\d+)-(\d+)", custom_id)
        if not match:
            print(f"⚠️  Could not parse custom_id: {custom_id}")
            continue

        result_inv_nr, batch_idx, start_idx, end_idx = match.groups()
        start_idx, end_idx = int(start_idx), int(end_idx)

        # Get response
        response = result["result"]
        if response["type"] != "succeeded":
            print(f"⚠️  Request failed: {custom_id}")
            continue

        message = response["message"]

        # Track usage
        usage = message["usage"]
        total_input_tokens += usage["input_tokens"]
        total_cached_tokens += usage.get("cache_read_input_tokens", 0)
        total_output_tokens += usage["output_tokens"]

        # Extract translations
        response_text = message["content"][0]["text"]

        # Parse chunks from response
        chunk_pattern = (
            r"---\s*CHUNK\s+(\d+)\s*---\s*(.*?)(?=---\s*CHUNK\s+\d+\s*---|$)"
        )
        parsed_chunks = re.findall(chunk_pattern, response_text, re.DOTALL)

        if len(parsed_chunks) != (end_idx - start_idx + 1):
            print(
                f"⚠️  Expected {end_idx - start_idx + 1} chunks, got {len(parsed_chunks)} for {custom_id}"
            )

        # Match parsed chunks to original chunks
        batch_chunks = chunks[start_idx : end_idx + 1]
        for i, (chunk_num, translation) in enumerate(parsed_chunks):
            if i >= len(batch_chunks):
                break

            original_chunk = batch_chunks[i]
            rowid = original_chunk["rowid"]

            translation_detailed = translation.strip()
            translation_clean = remove_brackets_content(translation_detailed)

            translations.append(
                {
                    "rowid": rowid,
                    "inv_nr": inv_nr,
                    "tanap_id": original_chunk["tanap_id"],
                    "chunk_id": original_chunk["chunk_id"],
                    "text_original": original_chunk["text"],
                    "text_translated_detailed": translation_detailed,
                    "text_translated_clean": translation_clean,
                    "translation_model": "claude-haiku-4-5-20251001-batch",
                    "translation_date": datetime.now().isoformat(),
                }
            )

    # Save translations
    translations.sort(key=lambda x: x["rowid"])
    output_file = TRANSLATIONS_DIR / f"{inv_nr}_translations.json"

    with open(output_file, "w") as f:
        json.dump(translations, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Processed {len(translations)} translations")
    print(f"   Saved to: {output_file}")

    # Calculate costs
    write_tokens = total_input_tokens - total_cached_tokens
    cost = (
        write_tokens * BATCH_HAIKU_INPUT_PRICE
        + total_cached_tokens * BATCH_HAIKU_CACHED_INPUT_PRICE
        + total_output_tokens * BATCH_HAIKU_OUTPUT_PRICE
    )

    print(f"\n💰 Token usage and costs:")
    print(
        f"   Input tokens (new): {write_tokens:,} @ ${BATCH_HAIKU_INPUT_PRICE * 1_000_000:.2f}/MTok = ${write_tokens * BATCH_HAIKU_INPUT_PRICE:.4f}"
    )
    print(
        f"   Input tokens (cached): {total_cached_tokens:,} @ ${BATCH_HAIKU_CACHED_INPUT_PRICE * 1_000_000:.2f}/MTok = ${total_cached_tokens * BATCH_HAIKU_CACHED_INPUT_PRICE:.4f}"
    )
    print(
        f"   Output tokens: {total_output_tokens:,} @ ${BATCH_HAIKU_OUTPUT_PRICE * 1_000_000:.2f}/MTok = ${total_output_tokens * BATCH_HAIKU_OUTPUT_PRICE:.4f}"
    )
    print(f"   Total cost: ${cost:.4f}")

    # Calculate savings
    no_cache_cost = (
        total_input_tokens * BATCH_HAIKU_INPUT_PRICE
        + total_output_tokens * BATCH_HAIKU_OUTPUT_PRICE
    )
    regular_cost = (
        total_input_tokens * 0.80 / 1_000_000 + total_output_tokens * 4.00 / 1_000_000
    )

    print(f"\n📊 Cost comparison:")
    print(f"   With batch API + caching: ${cost:.4f}")
    print(
        f"   With batch API only: ${no_cache_cost:.4f} (saved ${no_cache_cost - cost:.4f})"
    )
    print(
        f"   Regular API: ${regular_cost:.4f} (saved ${regular_cost - cost:.4f}, {((regular_cost - cost) / regular_cost * 100):.1f}%)"
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch translate VOC documents with prompt caching"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Create batch file
    create_parser = subparsers.add_parser("create", help="Create batch file")
    create_parser.add_argument("--inv-nr", required=True, help="Inventory number")
    create_parser.add_argument(
        "--batch-size", type=int, default=5, help="Chunks per batch (default: 5)"
    )

    # Submit batch
    submit_parser = subparsers.add_parser("submit", help="Submit batch file")
    submit_parser.add_argument(
        "--batch-file", required=True, help="Path to batch JSONL file"
    )

    # Check status
    status_parser = subparsers.add_parser("status", help="Check batch status")
    status_parser.add_argument("--batch-id", required=True, help="Batch ID")

    # Download results
    download_parser = subparsers.add_parser("download", help="Download batch results")
    download_parser.add_argument("--batch-id", required=True, help="Batch ID")

    # Process results
    process_parser = subparsers.add_parser("process", help="Process batch results")
    process_parser.add_argument(
        "--results-file", required=True, help="Path to results JSONL file"
    )
    process_parser.add_argument("--inv-nr", required=True, help="Inventory number")

    # All-in-one workflow
    workflow_parser = subparsers.add_parser(
        "workflow", help="Run complete workflow for an inventory"
    )
    workflow_parser.add_argument("--inv-nr", required=True, help="Inventory number")
    workflow_parser.add_argument(
        "--batch-size", type=int, default=5, help="Chunks per batch"
    )
    workflow_parser.add_argument(
        "--wait", action="store_true", help="Wait for batch to complete"
    )

    args = parser.parse_args()

    if args.command == "create":
        create_batch_file(args.inv_nr, args.batch_size)

    elif args.command == "submit":
        batch_file = Path(args.batch_file)
        submit_batch(batch_file)

    elif args.command == "status":
        check_status(args.batch_id)

    elif args.command == "download":
        download_results(args.batch_id)

    elif args.command == "process":
        results_file = Path(args.results_file)
        process_results(results_file, args.inv_nr)

    elif args.command == "workflow":
        # Run complete workflow
        print(f"\n🔄 Running complete workflow for inventory {args.inv_nr}")

        # 1. Create batch file
        batch_file = create_batch_file(args.inv_nr, args.batch_size)

        # 2. Submit batch
        batch_id = submit_batch(batch_file)

        if args.wait:
            # 3. Wait for completion
            print(f"\n⏳ Waiting for batch to complete...")
            while True:
                batch = check_status(batch_id)
                if batch.processing_status == "ended":
                    break
                elif batch.processing_status == "failed":
                    print("❌ Batch failed")
                    return
                time.sleep(60)  # Check every minute

            # 4. Download results
            results_file = download_results(batch_id)

            # 5. Process results
            if results_file:
                process_results(results_file, args.inv_nr)
        else:
            print(f"\n✅ Batch submitted. Check status with:")
            print(f"   python batch_translate.py status --batch-id {batch_id}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
