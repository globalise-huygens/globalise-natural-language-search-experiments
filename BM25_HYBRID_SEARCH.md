# BM25 Hybrid Search Implementation

## Overview

The VOC Natural Language Search application optionally combines semantic embeddings (FAISS) with BM25 keyword matching to provide a hybrid search approach. This document explains the BM25 implementation, scoring logic, and how to use it effectively.

## Why Hybrid Search?

**Semantic search** (embeddings + FAISS) excels at:

- Understanding conceptual queries and paraphrases
- Finding documents with similar meaning even if wording differs
- Handling open-ended exploratory queries

**BM25 keyword search** excels at:

- Exact name matching (person names, place names)
- Technical or specialized terms
- Queries with specific proper nouns that should rank highest

**Hybrid approach** combines both strengths, allowing users to balance semantic understanding with exact keyword precision.

## Architecture

### Components

1. **Semantic Search (FAISS)**

   - OpenAI `text-embedding-3-large` embeddings (3072 dimensions)
   - L2 distance similarity matching
   - Includes weighted metadata (plaats, vestiging, jaar, beschrijving)

2. **BM25 Keyword Search**

   - Okapi BM25 (rank-bm25 library)
   - Same weighted metadata as embeddings for consistency
   - Dutch stemming (NLTK SnowballStemmer)
   - Stopword filtering

3. **Scoring Combination**
   - Both scores normalized to [0, 1] range
   - User-controlled blending weight
   - Final score: `(1 - weight) × semantic + weight × bm25_scaled`

## Metadata Weighting

Both semantic and BM25 search index the same weighted metadata to ensure alignment:

```python
WEIGHT_PLAATS = 2.0          # Place/establishment (doubled)
WEIGHT_VESTIGING = 2.0       # Establishment name (doubled)
WEIGHT_JAAR = 1.5            # Year/date
WEIGHT_BESCHRIJVING = 0.5    # Document description (lighter)
WEIGHT_TEXT = 1.0            # Main document text (baseline)
```

**Rationale:**

- Place and establishment are often key search dimensions (e.g., "widows in Ternate")
- Year helps with temporal queries but shouldn't dominate
- Description provides context but is less reliable than main text
- Main text is the primary source of truth

The combined text is built as:

```
[plaats repeated 2x] [vestiging repeated 2x] [jaar repeated 1.5x] [beschrijving repeated 0.5x] [text]
```

## Preprocessing Pipeline

### Tokenization (Shared by both semantic and BM25)

1. **Lowercasing:** Convert text to lowercase
2. **Punctuation removal:** Strip all punctuation characters
3. **Stopword filtering:** Remove common Dutch words (de, het, een, van, op, in, etc.)
4. **Length filtering:** Keep only tokens with 3+ characters
5. **Dutch stemming:** Apply NLTK SnowballStemmer for Dutch
   - Handles singular/plural: "weduwe" / "weduwen" → "weduw"
   - Handles inflections and variants
   - Normalizes archaic spellings

### Corpus Vocabulary Building

When BM25 search is enabled, the system:

1. Loads all documents for the inventory number
2. Tokenizes each document (combined_text with metadata)
3. Builds vocabulary set of all unique stemmed tokens
4. Filters query tokens to only those in vocabulary

**Why vocabulary filtering?**

- Prevents BM25 from penalizing documents for missing rare/misspelled query terms
- Rare misspellings in historical documents won't cause false negatives
- Queries with typos or non-existent terms won't break scoring

## Scoring Algorithm

### Step 1: BM25 Raw Scores

```python
bm25_scores = bm25_index.get_scores(filtered_query_tokens)
```

Raw BM25 scores using the Okapi BM25 formula:

- Positive scores: Documents containing query terms
- Zero/negative scores: Documents missing query terms or with poor term frequency matches

### Step 2: Max-Normalization

```python
bm25_max = bm25_scores.max()
if bm25_max > 0:
    bm25_normalized = bm25_scores / bm25_max
else:
    bm25_normalized = zeros  # No matches found
```

Normalizes to [0, 1] range, preserving zero for non-matching documents.

### Step 3: Scaling to Semantic Range

```python
semantic_max = semantic_scores.max()
bm25_scaled = bm25_normalized × semantic_max
```

Scales BM25 scores to the same dynamic range as semantic scores so they're comparable.

### Step 4: Weighted Blending

```python
final_score = (1 - bm25_weight) × semantic_score + bm25_weight × bm25_scaled
```

- `bm25_weight = 0.0`: Pure semantic search
- `bm25_weight = 0.5`: Equal weight to both
- `bm25_weight = 1.0`: Pure keyword search
- Default: `bm25_weight = 0.3` (70% semantic, 30% keyword)

## Key Implementation Details

### Alignment with Embeddings

Both BM25 and embeddings use:

- Same source database (SQLite chunks)
- Same combined_text with weighted metadata
- Same stemming and preprocessing
- Same vocabulary and tokenization rules

This ensures that a document ranked high by one method will be considered fairly by the other.

### Cache Management

BM25 indices are cached to disk in `bm25_indices/{inv_nr}.pkl` with versioning:

- Version is stored in cache file
- If preprocessing changes (tokenization, weights, etc.), version is bumped
- Old caches are automatically invalidated and rebuilt
- Current version: `BM25_INDEX_VERSION = 2`

### Query Filtering

The system filters query tokens twice:

1. **Query preprocessing:** Same stemming/stopword removal as corpus
2. **Corpus vocabulary filter:** Remove tokens not in indexed documents
   - Handles user typos and rare terms gracefully
   - Prevents false penalization for unique query terms

## Usage

### Enabling BM25 in Streamlit App

1. **Sidebar → Hybrid search (experimental)**
2. **Enable BM25 keyword search** (checkbox)
3. **Adjust BM25 weight** (slider, 0.0–1.0)
   - Lower values favor semantic/conceptual matches
   - Higher values favor exact keyword matches
   - Default 0.3 is a good starting point

### Result Interpretation

When BM25 is enabled, results show:

```
Similarity: 0.782 (semantic: 0.539, BM25: 0.825)
```

- **Similarity:** Final blended score (what results are ranked by)
- **semantic:** Raw semantic similarity from embeddings
- **BM25:** Raw BM25 score (normalized to [0, 1])

This breakdown helps understand why a document ranked where it did.

## Troubleshooting

### Problem: All BM25 scores are 0

**Causes:**

- No query tokens in corpus vocabulary (very rare query words)
- Very short query with only stopwords
- Query is in a different language than corpus

**Solution:**

- Check if query makes sense for keyword search (try semantic search instead)
- If query is in English, translate it to Dutch first
- Use lower bm25_weight to favor semantic search

### Problem: BM25 score is 1.0 for all results

**Likely scenarios:**

- All documents contain all query terms (rare with long queries)
- Query is very specific to inventory

**Solution:**

- This is actually correct behavior - verify results manually
- Try more specific query terms
- Lower bm25_weight if semantic ranking feels better

### Problem: Results quality degrades with BM25 enabled

**Causes:**

- bm25_weight too high (overriding semantic ranking)
- Query is conceptual/paraphrased (bad for keyword matching)

**Solution:**

- Lower bm25_weight (try 0.1 or 0.2)
- Use more specific search terms for keyword matching
- Switch to pure semantic search (bm25_weight = 0) for conceptual queries

## Performance

- **BM25 index creation:** ~100-500ms per inventory number (depending on corpus size)
- **BM25 query:** ~10-50ms per inventory number
- **Disk space:** ~5-10MB per inventory number
- **Memory:** ~10-20MB per inventory number (indices cached in memory during session)

BM25 queries are very fast compared to embeddings generation, so hybrid search adds minimal latency.

## Future Improvements

Potential enhancements:

1. **Field-specific weighting:** Different weights for plaats vs. text matches
2. **Query expansion:** Automatic synonym/variant expansion for archaic terms
3. **Fuzzy matching:** Handle more spelling variations
4. **Per-inventory tuning:** Different weights for different document collections
5. **Learning to rank:** Machine learning combination of semantic + BM25 based on user feedback

## References

- **Okapi BM25:** https://en.wikipedia.org/wiki/Okapi_BM25
- **rank-bm25 library:** https://github.com/dorianbrown/rank_bm25
- **Dutch stemming:** NLTK SnowballStemmer, https://nltk.org/
- **FAISS:** https://github.com/facebookresearch/faiss

## Implementation Files

- **Main logic:** `app_core.py`

  - `create_or_load_bm25_index()`: BM25 index creation
  - `search_query()`: Hybrid scoring and combination
  - `_prepare_combined_text()`: Metadata weighting and alignment

- **UI:** `streamlit_app.py`

  - BM25 toggle and weight slider
  - Score breakdown in results

- **Configuration:** `app_core.py` module-level constants
  - `WEIGHT_*`: Metadata weights
  - `BM25_INDEX_VERSION`: Cache invalidation
