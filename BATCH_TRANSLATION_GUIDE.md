# Batch Translation with Prompt Caching

## Overview

This system uses Anthropic's Batch API with prompt caching to translate VOC documents at **90%+ cost savings** compared to regular API calls.

### Cost Savings

**Regular API (Haiku 4.5):**

- Input: $0.80 per million tokens
- Output: $4.00 per million tokens

**Batch API + Prompt Caching (Haiku 4.5):**

- Cached input: $0.02 per million tokens (98% discount!)
- Regular input: $0.40 per million tokens (50% discount)
- Output: $2.00 per million tokens (50% discount)

**Expected cost for 18 inventories (~10,500 chunks):**

- With batch API + caching: **~$2-3** 💰
- Without (regular API): **~$25-30**
- **Savings: ~90%**

### How It Works

1. **Prompt Caching**: The translation instructions (system prompt) are cached and reused across all requests in a batch, so you only pay full price once
2. **Batch API**: Requests are queued and processed during off-peak hours at 50% discount
3. **Processing Time**: Results typically available within a few hours (max 24 hours)

## Quick Start

### Submit All Remaining Inventories (Recommended)

```bash
# Submit batch jobs for all 18 remaining inventories
python batch_translate_all.py submit

# Check status (wait a few hours first)
python batch_translate_all.py check-all

# Download and process results when complete
python batch_translate_all.py process-all
```

That's it! The system will:

- Create 18 batch files (one per inventory)
- Submit all batches to Anthropic
- Save batch IDs for later retrieval
- Process results into translation JSON files when complete

### Individual Inventory (Manual Control)

For more control, process inventories one at a time:

```bash
# 1. Create batch file for inventory 1267
python batch_translate.py create --inv-nr 1267

# 2. Submit the batch
python batch_translate.py submit --batch-file batches/batch_1267.jsonl

# This outputs a batch ID like: batch_abc123...
# Save this ID!

# 3. Check status (wait a few hours)
python batch_translate.py status --batch-id batch_abc123...

# 4. Download results when status is "ended"
python batch_translate.py download --batch-id batch_abc123...

# 5. Process results into translations
python batch_translate.py process --results-file batch_results/batch_abc123..._results.jsonl --inv-nr 1267
```

### All-in-One Workflow

Run the complete workflow for one inventory:

```bash
# Submit and wait for completion (will block until done)
python batch_translate.py workflow --inv-nr 1267 --wait

# Or submit without waiting
python batch_translate.py workflow --inv-nr 1267
```

## File Structure

```
batches/
  batch_1267.jsonl              # Batch request file
  batch_1267_metadata.json      # Batch ID and metadata
  batch_submission_progress.json # All submitted batches

batch_results/
  batch_abc123..._results.jsonl # Raw results from API

translations/
  1267_translations.json        # Processed translations (same format as before)
```

## Expected Timeline

For 18 remaining inventories:

1. **Submission**: ~1-2 minutes (creates and submits all batches)
2. **Processing**: 2-12 hours (Anthropic processes during off-peak hours)
3. **Download & Process**: ~5 minutes (downloads and formats all results)

**Total wall time**: 2-12 hours (mostly waiting)
**Total cost**: ~$2-3 (instead of ~$25-30)

## Checking Progress

The batch submission script saves all batch IDs to `batches/batch_submission_progress.json`:

```bash
# Check status of all batches
python batch_translate_all.py check-all
```

This shows:

- ✅ Completed batches (ready to process)
- ⏳ In progress batches (still processing)
- ❌ Failed batches (need retry)

## After Processing

Once translations are processed, continue with the normal workflow:

```bash
# Import translations into database
python finalize_1267.py  # (or create similar scripts for other inventories)

# Generate embeddings
# (use existing embedding generation scripts)
```

## Tips

1. **Submit all at once**: Batch API handles queuing, so submit all 18 inventories at once
2. **Check in a few hours**: Most batches complete within 2-6 hours
3. **Process when complete**: You can process results as they complete (one at a time) or wait for all to finish
4. **Resume capability**: If interrupted, just re-run the process commands - they skip already-processed inventories

## Troubleshooting

**Batch still processing after 24 hours:**

```bash
python batch_translate.py status --batch-id <batch-id>
```

Check if status is "failed" - if so, you can resubmit that inventory.

**Missing translations after processing:**
Check the translations file and count:

```bash
python -c "import json; print(len(json.load(open('translations/1267_translations.json'))))"
```

**Cost estimate seems wrong:**
The first request in each batch pays full price for the system prompt (~500 tokens), then all subsequent requests in that batch pay the cached price. For a batch of 5 chunks, that's ~98% savings on the system prompt across the batch.

## Comparison: Batch API vs Real-Time

| Feature        | Batch API + Caching       | Real-Time API             |
| -------------- | ------------------------- | ------------------------- |
| Cost           | $2-3 for 18 inventories   | $25-30 for 18 inventories |
| Speed          | 2-12 hours                | 5-6 hours                 |
| Reliability    | High (queued)             | Requires monitoring       |
| Prompt Caching | Yes (98% savings)         | Yes (but less benefit)    |
| Best For       | Large batches, non-urgent | Single inventory, testing |

**Recommendation**: Use Batch API + caching for production translation of all remaining inventories. The 90%+ cost savings far outweigh the slightly longer processing time.
