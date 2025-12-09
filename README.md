# globalise-natural-language-search-experiments

Repository for natural language search experiments in historical VOC documents using semantic embeddings and AI-powered relevance matching.

## Quick Start

### Local Development

1. Create and activate a Python 3.10+ environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Provide an OpenAI API key via a `.env` file or environment variable:

```bash
echo "OPENAI_API_KEY=your_key_here" > .env
```

4. Run the Streamlit app:

```bash
streamlit run streamlit_app.py
```

On first run, the app will automatically download and extract the precomputed database and embeddings (approximately 200MB). This data is cached locally for subsequent runs.

### Streamlit Cloud Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for complete instructions on deploying to Streamlit Cloud with precomputed embeddings for team use.

Quick summary:

1. Run `python precompute_embeddings.py` locally to generate all embeddings
2. Commit `embeddings/` and `text-metadata-sqlite/` to git
3. Deploy to Streamlit Cloud (no secrets needed - users provide their own API keys)
4. The app automatically downloads required data files on first startup

## Streamlit App

This repository includes a Streamlit web application for exploring natural-language search across historical VOC documents using OpenAI embeddings and FAISS vector similarity search.

### Features

- **Semantic search** across historical Dutch VOC documents from 20 inventory numbers
- **Hybrid BM25 keyword search** (optional) for improved retrieval of proper names and technical terms
- Multi-language query support with automatic translation to modern Dutch
- Flexible result ranking: top K per inventory number or top K overall across all inventories
- Similarity threshold filtering to control result quality
- Interactive metadata-based filtering (year, place, establishment, document category)
- Downloadable search results as CSV
- Secure API key handling (session-only, never persisted to disk)
- Precomputed embeddings for fast shared team access

### Data Directories

- `text_input_metadata/` - Source CSV files with document text and metadata per inventory number
- `text-metadata-sqlite/` - SQLite database with chunks and metadata (approximately 96MB)
- `embeddings/` - FAISS indexes per inventory number (approximately 109MB, `.index` files)
- `bm25_indices/` - BM25 keyword search indices per inventory number (approximately 5-10MB each, created automatically)
- `results/` - User-generated search results (not committed to git)

On Streamlit Cloud and first local runs, the database and embeddings are automatically downloaded from cloud storage (https://surfdrive.surf.nl/s/8edwicW2DYd8QAB) and cached locally.

### How It Works

1. Data preparation: CSV files from `text_input_metadata/` are processed into 300-word chunks with 75-word overlap. Chunks can cross scan boundaries but respect document boundaries (TANAP IDs).
2. Metadata enrichment: Each chunk is enriched with metadata (year, place, establishment, document category) to enhance search and enable filtering.
3. Storage: Chunks and metadata are stored in SQLite database (`text-metadata-sqlite/voc_documents.db`).
4. Embeddings: FAISS indexes are created per inventory number using OpenAI's `text-embedding-3-large` model (3072 dimensions). Metadata is weighted and incorporated into embeddings.
5. Search: User queries are optionally translated to Dutch, embedded, and matched against FAISS indexes using cosine similarity.
6. Hybrid search (optional): If enabled, results are enhanced with BM25 (Okapi BM25) keyword matching to improve retrieval of proper names and technical terms:
   - BM25 uses the same weighted metadata (plaats, vestiging, jaar, beschrijving) as embeddings for consistency
   - Query tokens are stemmed (Dutch Snowball stemmer) and filtered to corpus vocabulary to avoid penalty for rare/misspelled terms
   - BM25 scores are max-normalized and scaled to match semantic score range
   - Final score: `(1 - weight) × semantic_score + weight × bm25_scaled`
   - Users control the semantic/keyword balance with an adjustable weight (0.0=pure semantic, 1.0=pure BM25, default 0.3)
   - BM25 scores appear as separate column in results for transparency
7. Filtering: Results can be filtered by similarity threshold, year range, place, establishment, and document category.
8. Ranking: Results are ranked by similarity score (or hybrid combined score if BM25 enabled), with options for per-inventory or overall ranking.

### Usage Modes

Local mode:

- Rebuild database from source CSV files with custom chunking parameters
- Generate embeddings on-demand for new inventory numbers
- Full read/write access to all settings

Cloud mode (Streamlit Cloud):

- Database rebuild options are disabled (greyed out)
- Uses precomputed database and embeddings downloaded automatically on startup
- Each user provides their own OpenAI API key (stored only in browser session)
- Fast shared access for teams without local setup

### Cost Estimates

Each search query requires:

- Query embedding: 1 call to `text-embedding-3-large` (~$0.00013 per query)
- Optional translation: 1 call to `gpt-4o-mini` if query is not in Dutch (~$0.0001)
- Total typical cost: ~$0.0002 per search query

Note: The precomputed embeddings for document chunks are generated once and reused, so they don't incur costs for each query.

## Project Structure

```
streamlit_app.py              Main Streamlit UI
app_core.py                   Core logic (chunking, embeddings, search)
download_data.py              Helper to download and extract precomputed data
precompute_embeddings.py      Helper to generate all embeddings locally
requirements.txt              Python dependencies
DEPLOYMENT.md                 Streamlit Cloud deployment guide
natural-language-search.ipynb Original research notebook
.streamlit/config.toml        Streamlit configuration
```

## Research Notebook

The `natural-language-search.ipynb` notebook contains the original exploratory analysis and prototyping work that led to the Streamlit app. It demonstrates the methodology for text chunking, embedding generation, and semantic search.

## Technical Details

### Models Used

- Embeddings: `text-embedding-3-large` (3072 dimensions, $0.00013 per 1K tokens)
- Translation: `gpt-4o-mini` (when query is not in Dutch, $0.00015 per 1K input tokens)

### Chunking Strategy

- Chunk size: 300 words
- Overlap: 75 words
- Chunks respect document boundaries (TANAP IDs) but can cross scan boundaries
- Metadata (year, place, establishment, description) is weighted and incorporated into embeddings

### Search Parameters

- Similarity threshold: Configurable minimum similarity score (default: 0.45)
- Top K mode: Per inventory number (default: 25) or overall across all inventories (default: 50)
- Result filtering: Year range, place, establishment, document category

### Hybrid Search: BM25 Keyword Matching

**Algorithm:** Okapi BM25 (rank-bm25 library implementation)

**Preprocessing:**

- Query tokens and corpus are stemmed using NLTK's Dutch Snowball stemmer
- Stopwords removed (common Dutch words: de, het, een, van, op, etc.)
- Tokens shorter than 3 characters filtered out
- Punctuation removed; text lowercased

**Scoring Logic:**

1. Build corpus vocabulary from all documents
2. Filter query tokens to only those in vocabulary (avoids penalizing for rare/misspelled terms)
3. Calculate BM25 scores using the filtered query tokens
4. Normalize BM25 scores: `bm25_normalized = bm25_raw / bm25_max` (keeps zeros for non-matches)
5. Scale normalized BM25 to semantic score range: `bm25_scaled = bm25_normalized × semantic_max`
6. Blend with semantic scores: `final_score = (1 - weight) × semantic + weight × bm25_scaled`

**Key Features:**

- **Metadata Integration:** BM25 indexes the same weighted metadata (plaats, vestiging, jaar, beschrijving) as embeddings, ensuring keyword matches consider document context
- **Consistency:** Both semantic and BM25 use identical tokenization/stemming for reliable combination
- **Transparency:** BM25 scores shown separately in results for understanding the ranking
- **Configurability:** Weight slider (0.0–1.0) lets users tune semantic vs. keyword balance

**Best Use Cases:**

- Searching for specific person names, place names, or proper nouns (semantic search often misses exact matches)
- Technical terms or historical jargon (benefit from exact matching)
- Queries mixing conceptual terms with specific proper names

**Limitations:**

- Relies on exact token matching; doesn't understand synonyms or related concepts
- Less effective for paraphrased queries or conceptual search (use semantic search for these)

## Security and Privacy

- API keys: Never committed to git; stored only in browser session memory (Streamlit session state)
- Data: Historic documents, metadata, and precomputed embeddings are public (committed to repository)
- User results: CSV outputs are excluded from git via `.gitignore`
- Cloud storage: Precomputed data is hosted on SURFdrive and downloaded automatically on app startup

## Contributing

To add new inventory numbers:

1. Add CSV file to `text_input_metadata/{inv_nr}_metadata.csv` with required columns (see existing files for format)
2. Run locally: `python precompute_embeddings.py` to generate embeddings
3. Commit updated `embeddings/` and `text-metadata-sqlite/` directories
4. Update cloud storage ZIP file with new data
5. Push to trigger automatic Streamlit Cloud redeployment

## Methodology

For detailed information about the methodology, data sources, and research context, see:

- The research notebook: `natural-language-search.ipynb`
- The deployment guide: `DEPLOYMENT.md`
- Renate Smit's metadata work: https://github.com/globalise-huygens/Inventorization-and-Metadata

## License

[TBA]

## Acknowledgments

This project builds on metadata enrichment work by Renate Smit, uses transcriptions from the GLOBALISE project (specifically XMI files with resolved line breaks, prepared by Bram Buitendijk).

---

For detailed deployment instructions, see [DEPLOYMENT.md](DEPLOYMENT.md)
