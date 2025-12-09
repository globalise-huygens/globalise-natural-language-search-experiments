# Testing BM25 Improvements

## Quick Start

The BM25 indices have been recreated with improved stemming-based tokenization. Here's how to test:

### Step 1: Start the Streamlit App

```bash
python -m streamlit run streamlit_app.py
```

### Step 2: Test the Problem Query

**Query:** `activiteiten van weduwen in ternate`

**Expected Results with Improved BM25:**

1. **Chunks about widows in Ternate** - HIGH scores (these should be ranked first)

   - Should match on "weduw" (stemmed from weduwe/weduwen)
   - Should match on "ternat" (stemmed from Ternate/Ternaten)
   - Combined relevance is high

2. **Chunks from Ternate only** - LOW scores (should be ranked lower)
   - Matches only "ternat"
   - No mention of widows
   - Should get minimal BM25 score

### Step 3: Verify the Fix

**In the Streamlit UI:**

1. Enable "BM25 keyword search" checkbox
2. Set BM25 weight to 0.3-0.5 (gives it meaningful weight)
3. Enter the query
4. Check the results:
   - Relevant chunks should rank high
   - Irrelevant chunks (just location) should rank low
   - **No more 1.0 scores for irrelevant matches** ✅

### What Changed

| Aspect              | Before                   | After                                             |
| ------------------- | ------------------------ | ------------------------------------------------- |
| **Tokenization**    | Simple lowercase split   | Dutch stemming (weduw/weduwe both → weduw)        |
| **Query filtering** | All query terms used     | Only terms in corpus used (prevents penalization) |
| **Normalization**   | Percentile-based         | Shift-and-scale (handles negative scores)         |
| **Example score**   | Ternate-only doc: 1.0 ❌ | Ternate-only doc: 0.0 ✅                          |

### Testing Other Queries

Try these queries to see the improvements:

1. **Plural vs Singular:**

   - Query: "vrouwen" vs "vrouw" (women/woman)
   - Both should find documents with either form

2. **Location matching:**

   - Query: "batavia" vs "Jakarta"
   - Should find VOC documents about Batavia

3. **Domain-specific terms:**
   - Query: "gouverneur" vs "gouverneurs"
   - Should match regardless of number

## Troubleshooting

**If scores are still not right:**

1. Check indices were recreated:

   ```bash
   ls -la bm25_indices/ | head
   # Should show recent dates (Dec 2025)
   ```

2. Verify stemming is working:

   ```bash
   python -c "from nltk.stem.snowball import SnowballStemmer; s = SnowballStemmer('dutch'); print(s.stem('weduwen'))"
   # Should print: "weduw"
   ```

3. Check that BM25 weight is > 0:
   - In Streamlit: "BM25 weight" slider should not be at 0.0
   - If 0.0, BM25 is disabled (only semantic search runs)

## Performance Notes

- **First run** of each inventory: Corpus tokens are scanned to build the filtering list

  - Takes ~100ms per inventory (one-time cost)
  - Subsequent searches use cached results

- **Score computation**: Still very fast (~1ms per document)
  - Stemming adds negligible overhead
  - Filtering adds O(n) scan but only of unique tokens

## Next Steps

Once you verify the improvements work:

1. **Generate full corpus indices** (optional, when ready):

   ```bash
   rm -rf bm25_indices/
   python create_bm25_indices.py  # No --limit flag = all inventories
   # This takes 2-3 hours for full corpus
   ```

2. **Document results** if using in research/publication

   - Include BM25_FIXES.md as reference
   - Note the stemming and filtering approach used

3. **Customize if needed**:
   - Edit stop_words set in app_core.py if you want different filtering
   - Add domain-specific terms or exclude certain words
