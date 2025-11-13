# Streamlit Cloud Deployment Guide

This guide explains how to deploy the VOC Natural Language Search app to Streamlit Cloud so your team can use it with shared, precomputed embeddings.

## 🎯 Deployment Overview

**Key features:**
- ✅ Shared precomputed embeddings and database (committed to repo)
- ✅ Secure API key handling (session-only, never persisted)
- ✅ Read-only mode on Streamlit Cloud (no embedding creation)
- ✅ Each user provides their own OpenAI API key

## 📋 Prerequisites

1. **GitHub account** with this repository pushed
2. **Streamlit Cloud account** (free tier works fine)
3. **OpenAI API key** (for local precomputation and for each user)

## 🚀 Step-by-Step Deployment

### Step 1: Precompute All Embeddings Locally

Before deploying, you must generate all FAISS embeddings locally (this only needs to be done once):

```bash
# Ensure your .env file has your OpenAI API key
echo "OPENAI_API_KEY=your_key_here" > .env

# Run the precomputation script
python precompute_embeddings.py
```

This will:
- Build the SQLite database from `text-input/` CSVs (if not already built)
- Generate FAISS embeddings for all inventory numbers
- Save everything to `embeddings/` and `text-metadata-sqlite/`

Expected output directories:
- `text-metadata-sqlite/voc_documents.db` (~96MB)
- `embeddings/*.db` (~109MB total for 8+ inventory numbers)

### Step 2: Commit Data to Git

The precomputed data needs to be in your repository:

```bash
# Add the precomputed files (these are already tracked)
git add text-metadata-sqlite/
git add embeddings/
git add .streamlit/
git add .gitignore

# Commit
git commit -m "Add precomputed embeddings and database for Streamlit Cloud deployment"

# Push to GitHub
git push origin main
```

**Important:** The `.gitignore` file is configured to:
- ✅ **Include** `text-metadata-sqlite/` and `embeddings/` (precomputed shared data)
- ❌ **Exclude** `results/*.csv` (user-generated search results)
- ❌ **Exclude** `.env` (sensitive API keys)

### Step 3: Deploy to Streamlit Cloud

1. Go to [share.streamlit.io](https://share.streamlit.io)
2. Click **"New app"**
3. Select your repository and branch
4. Set main file path: `streamlit_app.py`
5. Click **"Deploy"**

**No secrets needed!** Users provide their own API keys in the app interface.

### Step 4: Share with Your Team

Once deployed, share the app URL with your colleagues. They will:

1. Open the app
2. Enter their own OpenAI API key in the sidebar (text input field)
3. Select inventory numbers to search
4. Run queries

**Security note:** API keys are:
- ✅ Stored only in browser session memory (`st.session_state`)
- ✅ Never sent to Streamlit servers
- ✅ Never written to disk or logs
- ✅ Cleared when the browser session ends

## 🔒 Security & Privacy

### API Key Handling

The app uses Streamlit's session state to handle API keys securely:

```python
# From streamlit_app.py
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""

api_key_input = st.text_input(
    "OpenAI API key",
    value=st.session_state.api_key,
    type="password",
    help="Your API key is only stored in memory during this session and never saved to disk or servers."
)
```

This means:
- Keys exist only in the user's browser session
- They are destroyed when the tab/browser closes
- Streamlit Cloud servers never see or log the keys
- Each user must re-enter their key on each visit

### Data Privacy

- **Input data** (`text-input/`): Historic VOC documents, already committed to repo
- **Embeddings**: Precomputed, shared across all users
- **Search results**: Generated per-session, can be downloaded by users
- **Results directory**: User CSV outputs are NOT committed (excluded in `.gitignore`)

## 📦 Repository Structure for Deployment

```
├── streamlit_app.py          # Main app (committed)
├── app_core.py               # Core logic (committed)
├── precompute_embeddings.py  # Helper script for local use
├── requirements.txt          # Python dependencies (committed)
├── .streamlit/
│   └── config.toml           # Streamlit config (committed)
├── text-input/               # Source CSVs (committed, ~27MB)
├── text-metadata-sqlite/     # Precomputed DB (committed, ~96MB)
├── embeddings/               # Precomputed FAISS indexes (committed, ~109MB)
├── results/                  # User outputs (NOT committed)
│   └── .gitkeep             # Keeps directory structure
├── .env                      # API key for local dev (NOT committed)
└── .gitignore               # Exclusions configured
```

**Total repo size:** ~232MB (well within Streamlit Cloud's 1GB limit)

## 🔄 Updating Embeddings

If you add new inventory numbers or change chunking parameters:

1. **Locally**, run the precomputation script again:
   ```bash
   python precompute_embeddings.py
   ```

2. Commit and push the updated `embeddings/` and `text-metadata-sqlite/`:
   ```bash
   git add embeddings/ text-metadata-sqlite/
   git commit -m "Update embeddings with new inventory data"
   git push
   ```

3. Streamlit Cloud will automatically redeploy with the new data

## 🛠️ Troubleshooting

### "Embeddings for XXX not found" error

**Cause:** An inventory number exists in the database but has no corresponding FAISS index.

**Solution:**
```bash
# Locally, regenerate all embeddings
python precompute_embeddings.py

# Commit and push
git add embeddings/
git commit -m "Add missing embeddings"
git push
```

### App is slow or times out

**Cause:** First query for an inventory number loads its FAISS index into memory.

**Solution:** This is expected. Subsequent queries on the same inventory will be faster. For very large datasets, consider:
- Using Streamlit's caching (`@st.cache_resource`)
- Upgrading to a paid Streamlit Cloud tier with more memory

### Users can't enter API key

**Cause:** The session state initialization might not be working.

**Solution:** Check that the app starts with:
```python
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""
```

## 📊 Resource Limits (Streamlit Cloud Free Tier)

- **Storage:** 1GB (current usage: ~232MB ✅)
- **RAM:** 1GB (FAISS indexes loaded on-demand)
- **CPU:** Shared
- **Concurrent users:** Unlimited (each gets their own session)

## 🎓 User Instructions

Share these instructions with your colleagues:

---

**How to use the VOC Natural Language Search app:**

1. Open the app URL (provided by your administrator)
2. In the sidebar, enter your OpenAI API key
   - Get a key at: https://platform.openai.com/api-keys
   - Your key is never saved; you'll need to re-enter it each session
3. Select which inventory numbers to search
4. Enter your search query (any language; it will be auto-translated to Dutch)
5. Adjust Top-K and "verantwoording" settings if desired
6. Click **"Zoeken"** to search
7. View results, download as CSV if needed

**Cost estimates:**
- Each search uses the `text-embedding-3-large` model for the query (~$0.00013)
- Verantwoordingen use `gpt-4o-mini` (very low cost)
- Typical search: ~$0.001-0.01 depending on verantwoording count

---

## 🤝 Support

For issues or questions:
1. Check this deployment guide
2. Review the main [README.md](README.md)
3. Contact your repository administrator

## 📝 Changelog

- **v1.0** (Nov 2025): Initial deployment with precomputed embeddings and secure API key handling
