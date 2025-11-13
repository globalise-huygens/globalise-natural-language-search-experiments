# globalise-natural-language-search-experiments
Repo to collect data and code for natural language search experiments

## 🚀 Quick Start

### Local Development

1. Create and activate a Python 3.10+ environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Provide an OpenAI API key, either via a `.env` file or environment variable:

```bash
OPENAI_API_KEY=your_key_here
```

4. Run the Streamlit app:

```bash
streamlit run streamlit_app.py
```

### Streamlit Cloud Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete instructions on deploying to Streamlit Cloud with precomputed embeddings for team use.

**Quick summary:**
1. Run `python precompute_embeddings.py` locally to generate all embeddings
2. Commit `embeddings/` and `text-metadata-sqlite/` to git
3. Deploy to Streamlit Cloud (no secrets needed - users provide their own API keys)

## 📖 Streamlit App

This repo includes a Streamlit app to explore natural-language search across VOC documents using OpenAI embeddings and FAISS.

### Features

- 🔍 **Semantic search** across historical Dutch VOC documents
- 🌍 **Multi-language queries** (auto-translated to modern Dutch)
- 🤖 **AI-powered justifications** explaining why each result is relevant
- 📊 **Interactive results** with similarity scores and downloadable CSVs
- 🔒 **Secure API key handling** (session-only, never persisted)
- 💾 **Precomputed embeddings** for fast shared team access

### How It Works

1. **Data preparation**: CSV files from `text-input/` are chunked with overlap across page boundaries
2. **Storage**: Chunks and metadata stored in SQLite (`text-metadata-sqlite/voc_documents.db`)
3. **Embeddings**: FAISS indexes created per inventory number using OpenAI `text-embedding-3-large`
4. **Search**: User queries are translated to Dutch, embedded, and matched against FAISS indexes
5. **Ranking**: Results ranked by cosine similarity; optional AI justifications generated

### Usage

### Usage

**Local mode:**
- Rebuild database from `text-input/` CSVs with custom chunking parameters
- Generate embeddings on-demand for new inventory numbers
- Full read/write access

**Streamlit Cloud mode:**
- Read-only: uses precomputed database and embeddings
- Each user provides their own OpenAI API key (session-only)
- Fast shared access for teams

### Data Directories

- `text-input/` — Source CSV files (filename, text columns) per inventory number
- `text-metadata-sqlite/` — SQLite database with chunks and metadata (~96MB)
- `embeddings/` — FAISS indexes per inventory number (~109MB)
- `results/` — User-generated search results (not committed to git)

## 🏗️ Project Structure

```
├── streamlit_app.py          # Main Streamlit UI
├── app_core.py               # Core logic (chunking, embeddings, search)
├── precompute_embeddings.py  # Helper to generate all embeddings
├── requirements.txt          # Python dependencies
├── DEPLOYMENT.md            # Streamlit Cloud deployment guide
└── .streamlit/config.toml   # Streamlit configuration
```

## 📚 Notebook

The original research notebook `natural-language-search.ipynb` contains exploratory analysis and the prototyping work that led to the Streamlit app.

## 🔐 Security Notes

- **API keys**: Never committed; stored only in browser session memory
- **Data**: Historic documents and embeddings are committed (public repo)
- **Results**: User CSV outputs excluded from git via `.gitignore`

## 📊 Models Used

- **Embeddings**: `text-embedding-3-large` (3072 dimensions)
- **Translation & Justifications**: `gpt-4o-mini`

## 🤝 Contributing

To add new inventory numbers:

1. Add CSV file to `text-input/{inv_nr}.csv` with columns: `filename`, `text`
2. Locally run `python precompute_embeddings.py`
3. Commit updated `embeddings/` and `text-metadata-sqlite/`
4. Push to trigger automatic Streamlit Cloud redeployment

## 📝 License

[Add your license here]

## 👥 Team

[Add your team/project information here]

---

For deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)
