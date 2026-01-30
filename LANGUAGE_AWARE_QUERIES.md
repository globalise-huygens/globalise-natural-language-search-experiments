# Compare Both Mode: Language-Aware Query Implementation

## Summary

Implemented intelligent language detection and per-embedding query translation for "Compare Both" mode. This ensures each embedding (Dutch original and English translation) is queried in its native language, maximizing relevance and allowing fair comparison of embedding quality.

## How It Works

### Query Language Detection

When in "Compare Both" mode, the system automatically detects the query language:

- **Dutch query** → Searches Dutch embeddings with original query, English embeddings with English translation
- **English query** → Searches Dutch embeddings with Dutch translation, English embeddings with original query
- **Other language** → Translates to both Dutch and English

### Implementation Details

**New File: `language_utils.py`**

- `detect_query_language(query_text)`: Detects if query is Dutch, English, or other language
- `get_queries_for_compare_mode(query_text, client)`: Prepares language-specific queries for both embeddings
- `_translate_query(text, target_language, client)`: Translates query using GPT-4o-mini

**Modified: `streamlit_app.py`**

- Imports language detection utilities
- Conditional UI: Translation checkbox only appears in Original/Translated modes
- In Compare Both mode, displays detected language and translations (if any)
- Calls separate `search_query()` for each embedding with language-appropriate queries
- Merges results with source labels

**Modified: `app_core.py`**

- Added langdetect import (with graceful fallback if unavailable)

**Modified: `requirements.txt`**

- Added `langdetect>=1.0.9` dependency

## User Experience

### Original & Translated Modes

- Translation checkbox available to translate queries to Dutch if needed
- Works as before

### Compare Both Mode

1. User enters query in any language
2. System detects language
3. Display shows: "Query language detected: 🇳🇱 Dutch" (or English/Other)
4. If translated, shows both versions
5. Each embedding searched with optimal query language
6. Side-by-side results show which docs appear in which mode

**Example:**

```
User enters: "What were the main exports?"
↓
System detects: English
↓
Dutch embeddings searched with: "Wat waren de belangrijkste uitvoer?"
English embeddings searched with: "What were the main exports?"
↓
Results show:
  Left (Dutch): Top 5 from original corpus
  Right (English): Top 5 from translated corpus
```

## Benefits

✅ **Fair comparison** - Each embedding queried in native language
✅ **Optimal relevance** - Embeddings respond to semantically correct input
✅ **Transparent** - User sees detected language and any translations applied
✅ **Multilingual** - Works with queries in Dutch, English, or other languages
✅ **Cost-efficient** - Only translates when needed for Compare Both mode

## Testing

Run language detection tests:

```bash
python3 test_language_detection.py
```

Test full Compare Both workflow by:

1. Running: `streamlit run streamlit_app.py`
2. Select "Compare Both" mode
3. Try queries in different languages:
   - Dutch: "VOC handelsactiviteiten"
   - English: "trading activities of the VOC"
   - Mixed/Other: "la VOC et le commerce" (French)
4. Observe detected language and translation
5. Compare results from each embedding mode

## Future Enhancements

- Fine-tune language detection for very short queries
- Add option to manually override detected language
- Cache translations to avoid re-translating same query
- Add language preference settings in sidebar
