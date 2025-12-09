# 📊 Creating BM25 Indices

You need to pre-compute BM25 keyword search indices before using the hybrid search feature. Here's how:

## Quick Start (Recommended First)

**For a quick test (5 inventories, ~1 minute):**

```bash
cd /Users/lodewijkpetram/Documents/GitHub/globalise-natural-language-search-experiments
/Users/lodewijkpetram/miniforge3/bin/python create_bm25_indices.py --sample
```

This creates indices for just the first 5 inventories, enough to test the feature.

## Full Setup

**For all 20 sample inventories (~2 minutes):**

```bash
/Users/lodewijkpetram/miniforge3/bin/python create_bm25_indices.py --limit 20
```

**For the full corpus (7,000 inventories, ~2-3 hours):**

```bash
/Users/lodewijkpetram/miniforge3/bin/python create_bm25_indices.py
```

This creates ~35-70GB of index files in `bm25_indices/` directory.

## Options

```bash
# Quick test (5 inventories)
python create_bm25_indices.py --sample

# Create for first N inventories
python create_bm25_indices.py --limit 20

# Force recreate all (even if they exist)
python create_bm25_indices.py --force

# Show help
python create_bm25_indices.py --help
```

## How It Works

1. **Reads** all text chunks from SQLite database
2. **Tokenizes** the text (splits into words, lowercase)
3. **Creates** BM25 index using rank-bm25 library
4. **Saves** as pickle file: `bm25_indices/{inv_nr}.pkl`
5. **Reuses** on subsequent searches (cached)

## Storage

| Option       | Time    | Storage  | Purpose     |
| ------------ | ------- | -------- | ----------- |
| `--sample`   | 1 min   | ~50 MB   | Quick test  |
| `--limit 20` | 2 min   | ~200 MB  | Full sample |
| (no args)    | 2-3 hrs | 35-70 GB | Production  |

## When to Create Them

**Recommended workflow:**

1. **First**: Test with `--sample` to verify BM25 works
2. **Then**: Create for `--limit 20` to test on full sample data
3. **Finally**: Create all (if you want production-ready indices)

## What Happens Without Pre-Computed Indices

If you don't run this script:

- First search on an inventory: ~5-10 seconds (creates index on-the-fly)
- Subsequent searches same inventory: ~1 second (uses cached index)
- Works fine, just slower on first use

If you pre-compute indices:

- All searches: ~1 second (index already exists)
- Takes time upfront, but faster later

## Testing

After creating indices:

1. Start the Streamlit app:

   ```bash
   /Users/lodewijkpetram/miniforge3/bin/python -m streamlit run streamlit_app.py
   ```

2. In sidebar, enable BM25:

   - Check "Enable BM25 keyword search"
   - Adjust weight slider
   - Run a search

3. You should see no delay in BM25 scoring (index already exists)

## Troubleshooting

**"Database not found"**

- Make sure you've run the Streamlit app at least once
- The database should be at `text-metadata-sqlite/voc_documents.db`

**"No matching distribution found"**

- Make sure all dependencies are installed: `pip install -r requirements.txt`

**Script seems frozen**

- It's probably running. BM25 index creation is I/O-intensive
- For full corpus, expect 2-3 hours
- You'll see a progress bar with estimated time remaining

**Want to stop it?**

- Press `Ctrl+C` to stop
- Already-created indices will be kept
- Re-run to continue where you left off

## Next Steps

1. Run: `python create_bm25_indices.py --sample` (quick test)
2. Verify indices created: `ls bm25_indices/` (should show .pkl files)
3. Start Streamlit app and test the feature
4. If happy, run the full version when you have time

---

**Time to create sample**: ~1-5 minutes  
**Time to create all**: ~2-3 hours (one-time)  
**Status**: Ready to use!
