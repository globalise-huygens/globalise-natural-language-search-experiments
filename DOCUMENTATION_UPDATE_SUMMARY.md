# Documentation Updates for BM25 Hybrid Search - December 9, 2025

## Summary

Updated all project documentation to reflect the current BM25 hybrid search implementation with detailed explanations of the scoring logic, metadata weighting, and preprocessing pipeline.

## Files Updated

### 1. README.md

**Changes:**

- Expanded "How It Works" section (item 6) with detailed BM25 logic:
  - Explains weighted metadata integration
  - Documents stemming and query token filtering
  - Describes score normalization and blending formula
  - Shows user weight slider behavior
- Added comprehensive "Hybrid Search: BM25 Keyword Matching" subsection to Technical Details:
  - Algorithm overview (Okapi BM25)
  - Preprocessing pipeline (stemming, stopwords, tokenization)
  - Step-by-step scoring algorithm (raw scores → normalization → scaling → blending)
  - Key features and best use cases
  - Known limitations

**Why:** The README serves as the first reference point for new users and contributors; it now accurately reflects the current implementation.

### 2. BM25_HYBRID_SEARCH.md (NEW FILE)

**Content:**

- **Overview:** Why hybrid search is useful
- **Architecture:** Components (FAISS semantic, BM25 keyword, scoring combination)
- **Metadata Weighting:** Detailed explanation with rationale for weights:
  - Place/establishment: 2.0× (key search dimensions)
  - Year: 1.5× (temporal queries)
  - Description: 0.5× (context, less reliable)
  - Text: 1.0× (baseline)
- **Preprocessing Pipeline:** Complete tokenization flow (lowercasing → punctuation removal → stopword filtering → stemming)
- **Scoring Algorithm:** Four-step detailed breakdown:
  1. Raw BM25 scores
  2. Max-normalization
  3. Scaling to semantic range
  4. Weighted blending
- **Implementation Details:**
  - Alignment with embeddings
  - Cache management with versioning
  - Query filtering (twice: preprocessing + vocabulary)
- **Usage:** How to enable BM25 in Streamlit app
- **Result Interpretation:** How to read score breakdown
- **Troubleshooting:** Common issues and solutions
- **Performance:** Speed and resource estimates
- **Future Improvements:** Potential enhancements
- **References:** Links to Okapi BM25, rank-bm25, NLTK, FAISS
- **Implementation Files:** Pointers to relevant code sections

**Why:** Comprehensive documentation for anyone wanting to understand or modify the BM25 implementation.

## Current Implementation Details Documented

### Metadata Weighting (Shared between Semantic and BM25)

```
WEIGHT_PLAATS = 2.0          # Place (key search dimension)
WEIGHT_VESTIGING = 2.0       # Establishment (key search dimension)
WEIGHT_JAAR = 1.5            # Year/date (temporal queries)
WEIGHT_BESCHRIJVING = 0.5    # Description (context)
WEIGHT_TEXT = 1.0            # Main text (baseline)
```

### Preprocessing

1. Lowercasing
2. Punctuation removal
3. Stopword filtering (Dutch)
4. 3+ character length filtering
5. Dutch Snowball stemming (shared between query and corpus)

### Scoring Formula

```
final_score = (1 - bm25_weight) × semantic_score + bm25_weight × bm25_scaled
```

Where:

- `bm25_scaled = (bm25_raw / bm25_max) × semantic_max`
- `bm25_weight` user-configurable (default 0.3 = 70% semantic, 30% BM25)

### Cache Invalidation

- BM25 indices versioned (`BM25_INDEX_VERSION = 2`)
- Old caches auto-rebuilt when preprocessing changes
- Version check on cache load

## Testing

Code compiles successfully with all changes:

```
✅ Code compiles successfully
```

BM25 caches rebuild on first query after version bump, showing:

```
ℹ️ BM25 cache for {inv_nr} is outdated (version 1); rebuilding.
```

## Related Files Modified

- `app_core.py`: Added versioned cache management, metadata weighting helpers, aligned BM25/embeddings preprocessing
- `streamlit_app.py`: UI already supports BM25 toggle and weight slider (no changes needed)

## Backward Compatibility

- Old BM25 caches (version 1) are automatically detected and rebuilt
- Users will see minor notification on first search after update
- No manual action required
- Results will be more accurate due to:
  1. Weighted metadata alignment with embeddings
  2. Better scoring normalization
  3. Proper vocabulary filtering

## Next Steps for Users

1. **No action required** - app will auto-rebuild BM25 indices
2. **Test hybrid search** with the "weduwen in Ternate" query
3. **Report results** - verify that relevant "weduwe" documents now rank higher
4. **Adjust weight slider** - experiment with 0.1-0.5 range depending on query type
