# Setup Guide - BM25 Hybrid Search

## ✅ Dependencies Installed

All required packages have been installed in your Python 3.12 environment:

- ✅ streamlit 1.12.0
- ✅ openai
- ✅ faiss-cpu 1.13.0
- ✅ pandas
- ✅ numpy
- ✅ python-dotenv
- ✅ tqdm
- ✅ requests
- ✅ rank-bm25 0.2.2

## 📋 Requirements Updated

The `requirements.txt` has been updated to use more flexible version constraints that work with available packages.

**Old requirements** (too strict, caused conflicts):

```
streamlit>=1.38  (not available for your setup)
```

**New requirements** (compatible):

```
streamlit>=1.0   (1.12.0 available)
rank-bm25>=0.2.0 (0.2.2 available)
```

## 🚀 Ready to Run

Everything is installed and tested. To start the Streamlit app:

```bash
# Make sure you're in the right directory
cd /Users/lodewijkpetram/Documents/GitHub/globalise-natural-language-search-experiments

# Run the app
/Users/lodewijkpetram/miniforge3/bin/python -m streamlit run streamlit_app.py
```

Or if you want to use the simpler command, ensure `/Users/lodewijkpetram/miniforge3/bin` is in your PATH:

```bash
streamlit run streamlit_app.py
```

## 🧪 Testing the Implementation

Once the Streamlit app is running:

1. **Enter your OpenAI API key** in the sidebar
2. **Scroll down in the sidebar** to find the new **"🔤 Hybrid search (experimental)"** section
3. **Check the box**: "Enable BM25 keyword search"
4. **Adjust the slider**: "BM25 weight" (0.0-1.0)
5. **Run a search** to see BM25 in action

## 📊 What to Look For

**With BM25 disabled** (weight = 0.0):

- Results show `similarity` score only
- Pure semantic search

**With BM25 enabled** (weight = 0.3):

- Results show `similarity` (combined), `semantic_score`, and `bm25_score`
- Result headers show: "Similarity: 0.523 (semantic: 0.498, BM25: 0.610)"
- Exact name/place matches score higher

## 💡 Troubleshooting

**If Streamlit doesn't start:**

```bash
# Verify all imports work
/Users/lodewijkpetram/miniforge3/bin/python -c "import streamlit, openai, faiss, pandas; from rank_bm25 import BM25Okapi; print('✅ All good')"
```

**If BM25 controls don't appear:**

- Refresh the browser page
- Clear browser cache
- Check that the checkbox is visible in the sidebar

**If you get import errors:**

```bash
# Reinstall with the correct Python
/Users/lodewijkpetram/miniforge3/bin/python -m pip install -r requirements.txt
```

## 📝 Next Steps

1. Test the app locally
2. Try different BM25 weights on various queries
3. Check if BM25 improves results for your specific research questions
4. Read `NEXT_STEPS.md` for detailed testing guide

## ℹ️ Files for Reference

- `BM25_QUICKSTART.md` - Quick reference guide
- `BM25_IMPLEMENTATION.md` - Technical details
- `COMPLETION_SUMMARY.md` - Overview of implementation
- `NEXT_STEPS.md` - Detailed testing instructions

---

**Status**: ✅ Ready to use
**Python Version**: 3.12.10
**All Tests**: Passed
