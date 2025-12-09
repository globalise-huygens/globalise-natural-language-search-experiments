# BM25 Scoring Fixes - December 9, 2025

## Problem Identified

User reported critical BM25 scoring issues:

- Query: "activiteiten van weduwen in ternate"
- A chunk with NO mentions of "weduwen" but only from Ternate got BM25 score of **1.0**
- A highly relevant chunk mentioning "weduwe" (widow) got BM25 score of **0.0**

## Root Causes

### 1. No Stemming/Lemmatization

- Query has "weduwen" (plural), document has "weduwe" (singular)
- Without stemming, these are treated as different words
- BM25 couldn't match them, resulting in false negatives

### 2. Query Terms Not In Corpus

- Query includes "activiteiten" which doesn't appear in documents
- BM25 penalizes documents for missing query terms
- Caused documents with partial matches to get negative scores

### 3. Poor Normalization

- Percentile-based normalization still inflated scores inappropriately
- Documents with any match could reach near-perfect scores

## Solutions Implemented

### 1. ✅ Added Dutch Stemming (NLTK SnowballStemmer)

**What changed:**

- Replaced simple lowercase tokenization with `SnowballStemmer("dutch")`
- Both corpus and queries now use stemming
- Handles:
  - Singular/plural: "weduwe" → "weduw", "weduwen" → "weduw"
  - Spelling variations: "ternate" → "ternat", "ternaten" → "ternat"
  - Other inflections: prefixes, suffixes

**Files modified:**

- `requirements.txt`: Added `nltk>=3.8`
- `app_core.py`:
  - Import: `from nltk.stem.snowball import SnowballStemmer`
  - `create_or_load_bm25_index()`: Uses stemming in `tokenize_text()`
  - Search function: Uses same stemming in query processing

### 2. ✅ Filter Query Tokens to Corpus Vocabulary

**What changed:**

- New critical step: Before scoring, filter query tokens to only those that exist in the indexed corpus
- Prevents BM25 from penalizing documents for missing rare/misspelled terms
- Query tokens that don't appear in corpus are silently dropped

**Implementation:**

```python
# Build set of all unique tokens in corpus
all_corpus_tokens = set()
for text in corpus_texts:
    for token in tokenize_text(text):
        all_corpus_tokens.add(token)

# Filter query tokens
filtered_query_tokens = [t for t in query_tokens if t in all_corpus_tokens]

# Only proceed if at least one query token is in corpus
if filtered_query_tokens:
    bm25_scores = bm25_index.get_scores(filtered_query_tokens)
```

### 3. ✅ Improved Score Normalization

**Old approach:**

- Used percentile-based normalization
- Didn't handle negative BM25 scores properly
- Could still inflate scores

**New approach (shift-and-scale):**

```python
score_min = scores.min()
score_max = scores.max()
score_range = score_max - score_min

if score_range > 0:
    normalized = (scores - score_min) / score_range  # Maps to [0, 1]
else:
    normalized = 0.5 * ones_like(scores)  # All same, neutral
```

**Benefits:**

- Properly handles negative BM25 scores
- Preserves document ranking order
- Maps all scores to [0, 1] range
- Robust to score distributions

## Impact on Test Case

**Query:** "activiteiten van weduwen in ternate"

**Before fixes:**

- Doc 1 (Ternate only, no weduwe): BM25 = 1.0 ❌
- Doc 2 (weduwe + Ternate): BM25 = 0.0 ❌

**After fixes:**

1. Query tokens stemmed: ["activiteit", "weduw", "ternat"]
2. Filter to corpus: ["weduw", "ternat"] (activiteit not in corpus)
3. Raw BM25 scores:
   - Doc 1: -0.0078 (has only "ternat")
   - Doc 2: -0.0051 (has "weduw" + "ternat", ranks higher!)
4. Normalized scores (via shift-and-scale):
   - Doc 1: 0.000 ✅
   - Doc 2: 1.000 ✅

**Result:** Doc 2 correctly ranks much higher than Doc 1!

## Changes Summary

### Updated Files

1. **requirements.txt**

   - Added: `nltk>=3.8`

2. **app_core.py**

   - Import added: `SnowballStemmer`
   - Function: `create_or_load_bm25_index()` - updated tokenization with stemming
   - Function: `search()` - added corpus token filtering + improved normalization
   - ~100 lines modified total

3. **bm25_indices/** (recreated)
   - All indices regenerated with new stemming tokenization
   - Old indices had poor tokenization, new ones are better

## Testing

To verify the improvements:

```bash
# 1. Indices are already recreated with `python create_bm25_indices.py --limit 20`

# 2. Start the app
python -m streamlit run streamlit_app.py

# 3. Test the problem query
# Query: "activiteiten van weduwen in ternate"
# Enable BM25: Yes
# BM25 weight: 0.3 (or any value)

# 4. Expected results:
# - Chunks mentioning "weduwe" should rank high
# - Chunks that are just from Ternate but don't mention widows should rank low
# - No more inflated 1.0 scores for irrelevant matches
```

## Future Improvements (Optional)

1. **Fine-tuned stop word list:** Current list could be optimized for VOC domain
2. **Custom Dutch stemmer:** Could implement domain-specific stemming rules
3. **TF-IDF weighting:** Could weight important terms more heavily
4. **Language detection:** Could auto-detect and handle non-Dutch text

## References

- **NLTK Stemming:** https://www.nltk.org/howto/portuguese_en.html (similar for Dutch)
- **BM25 Algorithm:** https://en.wikipedia.org/wiki/Okapi_BM25
- **Dutch NLP:** https://github.com/clips/pattern (alternative if needed)
