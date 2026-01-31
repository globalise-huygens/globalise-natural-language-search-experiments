# Embeddings Backup (text-embedding-3-large)

This directory contains the original embeddings created with OpenAI's `text-embedding-3-large` model (3072 dimensions).

**Backup date:** 31 January 2026

**Reason for backup:**
The project switched from `text-embedding-3-large` to `text-embedding-3-small` (1536 dimensions) for cost optimization. The smaller model provides excellent performance for the translated modern English text while being 6.5× cheaper.

**Contents:**

- 20 original Dutch embeddings (`.index` files)
- 20 translated English embeddings (`_translated.index` files)

**Current setup (text-embedding-3-small):**

- Original Dutch embeddings: 1536 dimensions
- Translated English embeddings: 1536 dimensions (already created with small model)
- Cost savings: ~$0.11 per 1M tokens vs large model
- Performance: Excellent for modern translated text, good for archaic Dutch

**To restore large model embeddings:**

```bash
# If you want to switch back to the large model:
cp embeddings_backup_large/*.index embeddings/
```

**Note:** The translated embeddings were always created with the small model and did not need to be changed.
