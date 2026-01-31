# Embeddings Backup (text-embedding-3-small)

This directory contains embeddings created with OpenAI's `text-embedding-3-small` model (1536 dimensions).

**Backup Date:** January 31, 2026

## Why This Backup Exists

These embeddings were created during an attempted cost optimization where the project briefly switched from `text-embedding-3-large` (3072 dimensions) to `text-embedding-3-small` (1536 dimensions). However, we reverted to the large model because:

- The translated embeddings were already using the large model (3072 dims)
- Restoring the large model embeddings avoided the $5-10 cost of regenerating translated embeddings
- The large model provides better semantic quality for historical texts

## Contents

- 20 original (Dutch) `.index` files using text-embedding-3-small (1536 dimensions)
- 20 translated (English) `_translated.index` files using text-embedding-3-large (3072 dimensions)

## Restoring These Embeddings

If you want to switch back to the small model for cost savings:

1. **Copy original embeddings:**

   ```bash
   cp embeddings_backup_small/*.index embeddings/
   # Don't copy *_translated.index files
   ```

2. **Regenerate translated embeddings with small model:**

   ```bash
   python regenerate_translated_embeddings.py
   ```

   Cost: ~$5-10 for ~15,000 chunks

3. **Update app configuration:**

   ```python
   # In app_core.py
   EMB_MODEL = "text-embedding-3-small"
   ```

4. **Update documentation** in streamlit_app.py and README.md

**Note:** Only restore if you need to optimize query costs (6.5× cheaper per query). The one-time regeneration cost is ~$10.
