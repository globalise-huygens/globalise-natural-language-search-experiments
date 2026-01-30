#!/usr/bin/env python3
"""
Submit batch translation jobs for all remaining inventories.

This script automates submitting batch jobs for multiple inventories at once.
Results can be downloaded and processed later (typically within 24 hours).
"""

import json
import time
from pathlib import Path
from batch_translate import (
    create_batch_file,
    submit_batch,
    check_status,
    download_results,
    process_results,
)

# All 20 inventories (excluding 1120 and 3891 which are already done)
ALL_INVENTORIES = [
    1120,
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

# Already completed
COMPLETED = [1120, 3891]

# Remaining to translate
REMAINING = [inv for inv in ALL_INVENTORIES if inv not in COMPLETED]


def submit_all_batches(batch_size: int = 5, delay_between_submissions: int = 2):
    """
    Create and submit batch jobs for all remaining inventories.

    Args:
        batch_size: Number of chunks per batch request
        delay_between_submissions: Seconds to wait between submissions to avoid rate limits
    """
    print(f"\n🚀 Submitting batch jobs for {len(REMAINING)} inventories")
    print(f"   Remaining inventories: {REMAINING}")
    print(f"   Batch size: {batch_size} chunks per request")
    print(f"   Delay between submissions: {delay_between_submissions}s\n")

    submitted_batches = []

    for i, inv_nr in enumerate(REMAINING, 1):
        print(f"\n{'=' * 60}")
        print(f"📦 [{i}/{len(REMAINING)}] Processing inventory {inv_nr}")
        print(f"{'=' * 60}")

        try:
            # Create batch file
            batch_file = create_batch_file(str(inv_nr), batch_size)

            # Submit batch
            batch_id = submit_batch(batch_file)

            submitted_batches.append(
                {
                    "inv_nr": inv_nr,
                    "batch_id": batch_id,
                    "batch_file": str(batch_file),
                    "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

            # Save progress
            progress_file = Path("batches/batch_submission_progress.json")
            with open(progress_file, "w") as f:
                json.dump(submitted_batches, f, indent=2)

            print(f"   Progress saved to: {progress_file}")

            # Wait before next submission
            if i < len(REMAINING):
                print(
                    f"\n⏸️  Waiting {delay_between_submissions}s before next submission..."
                )
                time.sleep(delay_between_submissions)

        except Exception as e:
            print(f"❌ Error processing inventory {inv_nr}: {e}")
            continue

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✅ SUBMISSION COMPLETE")
    print(f"{'=' * 60}")
    print(f"   Submitted: {len(submitted_batches)}/{len(REMAINING)} batches")
    print(f"\n📋 Batch IDs:")
    for batch in submitted_batches:
        print(f"   {batch['inv_nr']}: {batch['batch_id']}")

    print(f"\n📝 All batch IDs saved to: batches/batch_submission_progress.json")
    print(f"\n⏳ Batches typically complete within 24 hours (often much faster)")
    print(f"\n🔍 Check status of all batches:")
    print(f"   python batch_translate_all.py check-all")
    print(f"\n⬇️  Download and process all results when complete:")
    print(f"   python batch_translate_all.py process-all")


def check_all_batches():
    """Check status of all submitted batches."""
    progress_file = Path("batches/batch_submission_progress.json")

    if not progress_file.exists():
        print("❌ No batches found. Submit batches first with:")
        print("   python batch_translate_all.py submit")
        return

    with open(progress_file) as f:
        batches = json.load(f)

    print(f"\n🔍 Checking status of {len(batches)} batches\n")

    status_summary = {"ended": [], "in_progress": [], "failed": [], "unknown": []}

    for batch_info in batches:
        inv_nr = batch_info["inv_nr"]
        batch_id = batch_info["batch_id"]

        try:
            print(f"\n📦 Inventory {inv_nr} (batch {batch_id})")
            batch = check_status(batch_id)
            status = batch.processing_status
            status_summary[status].append(inv_nr)
        except Exception as e:
            print(f"❌ Error checking status: {e}")
            status_summary["unknown"].append(inv_nr)

    # Summary
    print(f"\n{'=' * 60}")
    print(f"📊 STATUS SUMMARY")
    print(f"{'=' * 60}")
    print(
        f"   ✅ Completed: {len(status_summary['ended'])} - {status_summary['ended']}"
    )
    print(
        f"   ⏳ In Progress: {len(status_summary['in_progress'])} - {status_summary['in_progress']}"
    )
    print(f"   ❌ Failed: {len(status_summary['failed'])} - {status_summary['failed']}")
    if status_summary["unknown"]:
        print(
            f"   ❓ Unknown: {len(status_summary['unknown'])} - {status_summary['unknown']}"
        )

    if status_summary["ended"]:
        print(f"\n⬇️  Ready to download and process:")
        print(f"   python batch_translate_all.py process-all")


def process_all_results():
    """Download and process results for all completed batches."""
    progress_file = Path("batches/batch_submission_progress.json")

    if not progress_file.exists():
        print("❌ No batches found.")
        return

    with open(progress_file) as f:
        batches = json.load(f)

    print(f"\n⬇️  Processing results for {len(batches)} batches\n")

    processed = []
    failed = []

    for batch_info in batches:
        inv_nr = batch_info["inv_nr"]
        batch_id = batch_info["batch_id"]

        try:
            print(f"\n{'=' * 60}")
            print(f"📦 Inventory {inv_nr} (batch {batch_id})")
            print(f"{'=' * 60}")

            # Check if already processed
            translations_file = Path(f"translations/{inv_nr}_translations.json")
            if translations_file.exists():
                print(f"⚠️  Translations file already exists, skipping")
                processed.append(inv_nr)
                continue

            # Download results
            results_file = download_results(batch_id)

            if results_file:
                # Process results
                process_results(results_file, str(inv_nr))
                processed.append(inv_nr)
            else:
                print(f"⚠️  Batch not ready yet, skipping")
                failed.append(inv_nr)

        except Exception as e:
            print(f"❌ Error processing inventory {inv_nr}: {e}")
            failed.append(inv_nr)
            continue

    # Summary
    print(f"\n{'=' * 60}")
    print(f"✅ PROCESSING COMPLETE")
    print(f"{'=' * 60}")
    print(f"   Processed: {len(processed)} - {processed}")
    if failed:
        print(f"   Failed/Not Ready: {len(failed)} - {failed}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Batch translate all remaining inventories"
    )
    parser.add_argument(
        "command", choices=["submit", "check-all", "process-all"], help="Command to run"
    )
    parser.add_argument(
        "--batch-size", type=int, default=5, help="Chunks per batch (default: 5)"
    )
    parser.add_argument(
        "--delay", type=int, default=2, help="Seconds between submissions (default: 2)"
    )

    args = parser.parse_args()

    if args.command == "submit":
        submit_all_batches(args.batch_size, args.delay)
    elif args.command == "check-all":
        check_all_batches()
    elif args.command == "process-all":
        process_all_results()


if __name__ == "__main__":
    main()
