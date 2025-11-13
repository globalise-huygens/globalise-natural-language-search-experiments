import os
import re
import sqlite3
from pathlib import Path
from typing import Iterable, List, Tuple, Optional

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm


# --- Environment & constants ---
load_dotenv()

DATA_DIR = Path("text_input_metadata")
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
EMB_DIR = Path("embeddings")
RESULTS_DIR = Path("results")

EMB_MODEL = "text-embedding-3-large"
CHAT_MODEL = "gpt-4o-mini"


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set. Create a .env file or export the variable.")
    return OpenAI(api_key=api_key)


# --- Text preprocessing ---
def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    text = text.replace("„", '"').replace("’", "'")
    text = re.sub(r"[:;]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# --- Chunking ---
def chunk_within_docs(df_inv: pd.DataFrame, chunk_size: int, overlap: int) -> List[dict]:
    """
    Chunk text within document boundaries (tanap_id), not crossing documents.
    Returns list of chunk dictionaries with metadata.
    """
    all_chunks = []
    for tanap_id, df_doc in df_inv.groupby("tanap_id"):
        # Metadata for this doc (take first row)
        meta = df_doc.iloc[0]
        all_words = []
        page_boundaries = []
        word_count = 0
        for idx, row in df_doc.iterrows():
            words = str(row["text"]).split()
            all_words.extend(words)
            page_boundaries.append((word_count, row["filename"]))
            word_count += len(words)
        start = 0
        while start < len(all_words):
            end = min(start + chunk_size, len(all_words))
            chunk_words = all_words[start:end]
            pages_in_chunk = [p for idx_p, p in page_boundaries if start <= idx_p < end]
            if not pages_in_chunk:
                pages_in_chunk = [df_doc.iloc[-1]["filename"]]
            all_chunks.append({
                "inv_nr": meta["inv_nr"],
                "tanap_id": tanap_id,
                "chunk_id": start // max(1, chunk_size - overlap),
                "text": " ".join(chunk_words),
                "start_page": pages_in_chunk[0],
                "pages": pages_in_chunk,
                "datum": meta["datum"],
                "plaats": meta["plaats"],
                "vestiging": meta.get("vestiging", ""),
                "beschrijving": meta["beschrijving"],
                "doc_category": meta["doc_category"]
            })
            start += chunk_size - overlap
    return all_chunks


# --- DB utilities ---
def ensure_database_from_text_inputs(apply_normalization: bool = True, chunk_size: int = 300, overlap: int = 75) -> int:
    """
    Build or refresh the SQLite database from CSVs in text_input_metadata/.
    Returns number of chunks inserted.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Load CSVs with metadata
    all_files = sorted(DATA_DIR.glob("*.csv"))
    if not all_files:
        raise FileNotFoundError(f"No CSV files found in {DATA_DIR}.")

    dfs = []
    for f in all_files:
        # Extract inv_nr as everything before the first underscore
        inv_nr = f.stem.split("_")[0]
        df_temp = pd.read_csv(f, sep=",")
        # Only keep doc pages (TANAP_ID not empty)
        df_temp = df_temp[df_temp["TANAP_ID"].notna() & (df_temp["TANAP_ID"] != "")]
        # Standardize columns
        df_temp = df_temp.rename(columns={
            "text": "text",
            "filename": "filename",
            "TANAP_ID": "tanap_id",
            "TANAP_Boundaries": "tanap_boundaries",
            "DATUM": "datum",
            "PLAATS": "plaats",
            "VESTIGING": "vestiging",
            "BESCHRIJVING": "beschrijving",
            "GLOBALISE_document_category": "doc_category"
        })
        df_temp["inv_nr"] = inv_nr
        if apply_normalization:
            df_temp["text"] = df_temp["text"].apply(normalize_text)
        dfs.append(df_temp)
    
    df_all = pd.concat(dfs, ignore_index=True)

    # Create table with metadata columns
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS documents")
        cur.execute(
            """
            CREATE TABLE documents (
                inv_nr TEXT,
                tanap_id TEXT,
                start_page TEXT,
                pages TEXT,
                chunk_id INTEGER,
                datum TEXT,
                plaats TEXT,
                vestiging TEXT,
                beschrijving TEXT,
                doc_category TEXT,
                text TEXT
            )
            """
        )
        conn.commit()

        # Build chunks per inv_nr and insert
        total_chunks = 0
        for inv_nr in df_all["inv_nr"].unique():
            df_inv = df_all[df_all["inv_nr"] == inv_nr].copy()
            all_chunks = chunk_within_docs(df_inv, chunk_size=chunk_size, overlap=overlap)
            
            for chunk_data in all_chunks:
                pages_str = ";".join(chunk_data["pages"]) if chunk_data["pages"] else ""
                cur.execute(
                    """
                    INSERT INTO documents (inv_nr, tanap_id, start_page, pages, chunk_id, datum, plaats, vestiging, beschrijving, doc_category, text)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(chunk_data["inv_nr"]),
                        str(chunk_data["tanap_id"]),
                        str(chunk_data["start_page"]),
                        pages_str,
                        int(chunk_data["chunk_id"]),
                        str(chunk_data["datum"]),
                        str(chunk_data["plaats"]),
                        str(chunk_data.get("vestiging", "")),
                        str(chunk_data["beschrijving"]),
                        str(chunk_data["doc_category"]),
                        str(chunk_data["text"])
                    ),
                )
            total_chunks += len(all_chunks)
        conn.commit()

    return total_chunks


def list_available_inv_nrs() -> List[str]:
    """List inventory numbers from DB if present, else from text_input_metadata CSV names."""
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute("SELECT DISTINCT inv_nr FROM documents ORDER BY inv_nr").fetchall()
            invs = [r[0] for r in rows]
            if invs:
                return invs
    # Fallback to files
    return sorted([p.stem.split("_")[0] for p in DATA_DIR.glob("*.csv")])


def get_filter_options() -> dict:
    """
    Get available filter options from the database.
    Returns dict with 'doc_categories', 'vestigingen', 'plaatsen', and 'year_range'.
    """
    if not DB_PATH.exists():
        return {
            "doc_categories": [],
            "vestigingen": [],
            "plaatsen": [],
            "year_range": (1600, 1800),
        }
    
    with sqlite3.connect(DB_PATH) as conn:
        # Get column names from the database
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(documents)")
        columns = [row[1] for row in cursor.fetchall()]
        
        # Get unique document categories (if column exists)
        if "doc_category" in columns:
            doc_cats = pd.read_sql_query(
                "SELECT DISTINCT doc_category FROM documents WHERE doc_category IS NOT NULL AND doc_category != ''",
                conn
            )["doc_category"].tolist()
        else:
            doc_cats = []
        
        # Get unique vestigingen (if column exists)
        if "vestiging" in columns:
            vest = pd.read_sql_query(
                "SELECT DISTINCT vestiging FROM documents WHERE vestiging IS NOT NULL AND vestiging != ''",
                conn
            )["vestiging"].tolist()
        else:
            vest = []
        
        # Get unique plaatsen (if column exists, handling pipe-separated values)
        if "plaats" in columns:
            plaatsen_raw = pd.read_sql_query(
                "SELECT DISTINCT plaats FROM documents WHERE plaats IS NOT NULL AND plaats != ''",
                conn
            )["plaats"].tolist()
            
            # Flatten pipe-separated plaats values
            plaatsen = set()
            for p in plaatsen_raw:
                if isinstance(p, str):
                    plaatsen.update([x.strip() for x in p.split("|") if x.strip()])
            plaatsen = sorted(list(plaatsen))
        else:
            plaatsen = []
        
        # Get year range (if datum column exists)
        if "datum" in columns:
            datum_df = pd.read_sql_query(
                "SELECT datum FROM documents WHERE datum IS NOT NULL AND datum != ''",
                conn
            )
            years = datum_df["datum"].str.extract(r"(\d{4})")[0].dropna().astype(int)
            year_min = int(years.min()) if len(years) > 0 else 1600
            year_max = int(years.max()) if len(years) > 0 else 1800
        else:
            year_min, year_max = 1600, 1800
        
        return {
            "doc_categories": sorted(doc_cats),
            "vestigingen": sorted(vest),
            "plaatsen": plaatsen,
            "year_range": (year_min, year_max),
        }


# --- Embeddings & search ---
def _embeddings_file(inv_nr: str) -> Path:
    EMB_DIR.mkdir(exist_ok=True)
    return EMB_DIR / f"{inv_nr}.index"


def load_or_create_embeddings(inv_nr: str, client: OpenAI) -> Tuple[faiss.IndexFlatL2, List[str]]:
    """
    Load FAISS index for an inv_nr or create it from the SQLite documents.
    Uses weighted metadata (plaats, vestiging, jaar, beschrijving) in embeddings.
    Returns (faiss_index, chunks_texts)
    
    On Streamlit Cloud, only loads pre-existing embeddings (no creation).
    """
    # ====== ⚖️ WEIGHTS — adjust these to tune importance ======
    WEIGHT_PLAATS = 2.0
    WEIGHT_VESTIGING = 2.0
    WEIGHT_JAAR = 1.5
    WEIGHT_BESCHRIJVING = 0.5
    WEIGHT_TEXT = 1.0
    # ==========================================================

    def repeat_weighted(text, weight):
        n = max(1, int(round(weight)))
        return (" " + text) * n

    def expand_places(raw_str):
        if not raw_str or not isinstance(raw_str, str):
            return ""
        parts = [p.strip() for p in raw_str.split("|") if p.strip()]
        return " ".join([f"Plaats: {p}." for p in parts]) if parts else ""

    def safe_col(df, col):
        """Always return a Series (string type), even if column missing."""
        if col in df.columns:
            return df[col].fillna("").astype(str)
        else:
            return pd.Series([""] * len(df), index=df.index, dtype=str)

    if not DB_PATH.exists():
        raise FileNotFoundError("SQLite database not found. Build it from text inputs first.")

    with sqlite3.connect(DB_PATH) as conn:
        df_chunks = pd.read_sql_query(
            "SELECT * FROM documents WHERE inv_nr=? ORDER BY chunk_id",
            conn,
            params=(inv_nr,),
        )

    if df_chunks.empty:
        raise ValueError(f"No data found for inv_nr {inv_nr} in the database.")

    # --- Safe column loading ---
    df_chunks["text"] = safe_col(df_chunks, "text")
    df_chunks["plaats"] = safe_col(df_chunks, "plaats")
    df_chunks["vestiging"] = safe_col(df_chunks, "vestiging")
    df_chunks["beschrijving"] = safe_col(df_chunks, "beschrijving")
    df_chunks["datum"] = safe_col(df_chunks, "datum")

    # Extract only the year (yyyy)
    df_chunks["jaar"] = df_chunks["datum"].str.extract(r"(\d{4})")[0].fillna("")

    # --- Combine weighted metadata into a single text field ---
    df_chunks["combined_text"] = (
        repeat_weighted(df_chunks["plaats"].apply(expand_places), WEIGHT_PLAATS) +
        repeat_weighted("Vestiging: " + df_chunks["vestiging"] + ".", WEIGHT_VESTIGING) +
        repeat_weighted("Jaar: " + df_chunks["jaar"] + ".", WEIGHT_JAAR) +
        repeat_weighted("Beschrijving: " + df_chunks["beschrijving"] + ".", WEIGHT_BESCHRIJVING) +
        repeat_weighted(df_chunks["text"], WEIGHT_TEXT)
    )

    # Remove empty or whitespace-only entries
    df_chunks = df_chunks[df_chunks["combined_text"].str.strip() != ""]
    chunks_inv = df_chunks["combined_text"].tolist()

    if not chunks_inv:
        raise ValueError(f"All chunks for {inv_nr} are empty after cleaning.")

    emb_file = _embeddings_file(inv_nr)
    if emb_file.exists():
        faiss_idx = faiss.read_index(str(emb_file))
        return faiss_idx, chunks_inv

    # Check if running on Streamlit Cloud
    is_cloud = os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD")
    if is_cloud:
        raise RuntimeError(
            f"Embeddings for {inv_nr} not found. On Streamlit Cloud, all embeddings must be precomputed. "
            "Please generate embeddings locally and commit them to the repository."
        )

    # Create embeddings (only in local development)
    embeddings: List[List[float]] = []
    batch_size = 50
    print(f"🧠 Computing embeddings for {inv_nr} ({len(chunks_inv)} chunks, with weighted metadata)...")
    for i in tqdm(range(0, len(chunks_inv), batch_size)):
        batch = chunks_inv[i : i + batch_size]
        try:
            resp = client.embeddings.create(model=EMB_MODEL, input=batch)
            batch_embeddings = [r.embedding for r in resp.data if hasattr(r, "embedding")]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"Embedding batch {i} failed: {e}")
            continue

    if not embeddings:
        raise RuntimeError(f"No embeddings created for {inv_nr}.")

    emb_arr = np.array(embeddings, dtype="float32")
    dim = emb_arr.shape[1]
    faiss_idx = faiss.IndexFlatL2(dim)
    faiss_idx.add(emb_arr)
    faiss.write_index(faiss_idx, str(emb_file))
    print(f"💾 Saved FAISS index for {inv_nr} -> {emb_file}")
    return faiss_idx, chunks_inv


def is_dutch(text: str) -> bool:
    """Detect if the text is Dutch using a simple heuristic."""
    dutch_words = ["de", "het", "een", "en", "van", "op", "in", "is", "niet", "dat", "met"]
    text_lower = text.lower()
    return any(word in text_lower.split() for word in dutch_words)


def translate_to_dutch(client: OpenAI, text: str) -> str:
    """Translate input (in any language) to modern Dutch."""
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "Je bent een ervaren vertaler gespecialiseerd in geschiedenis en (vroeg-)koloniale terminologie."
                ),
            },
            {
                "role": "user",
                "content": f"Vertaal dit naar modern Nederlands, behoud betekenis en historische termen: {text}",
            },
        ],
        temperature=0.3,
    )
    return resp.choices[0].message.content.strip()


def build_transcription_url(start_page: str) -> str:
    """
    Build a transcription viewer URL from the start_page value.
    Example: NL-HaNA_1.04.02_8023_0061 -> https://transcriptions.globalise.huygens.knaw.nl/detail/urn:globalise:NL-HaNA_1.04.02_8023_0061?query[fullText]=x
    """
    if not start_page or not isinstance(start_page, str):
        return ""
    # Clean the page ID
    page_id = start_page.strip()
    if not page_id:
        return ""
    return f"https://transcriptions.globalise.huygens.knaw.nl/detail/urn:globalise:{page_id}?query[fullText]=x"


def safe_filename_from_query(q: str) -> str:
    return "".join([c for c in q if c.isalnum() or c in "-_ "]).strip().replace(" ", "_")


def search_query(
    query_text: str,
    inv_nrs: Iterable[str],
    top_k: int | None = None,
    translate_if_not_dutch: bool = True,
) -> pd.DataFrame:
    """
    Search across one or more inventory numbers and return a unified DataFrame.
    Filters are applied in the UI after getting results.
    
    Args:
        query_text: The search query
        inv_nrs: List of inventory numbers to search
        top_k: Maximum results per inventory number
        translate_if_not_dutch: Auto-translate non-Dutch queries to Dutch
    """
    RESULTS_DIR.mkdir(exist_ok=True)
    client = get_openai_client()

    # Optional translation
    if translate_if_not_dutch and not is_dutch(query_text):
        translated_query = translate_to_dutch(client, query_text)
        print(f"🌍 Original query: {query_text}")
        print(f"🇳🇱 Translated query: {translated_query}")
    else:
        translated_query = query_text
        print(f"🔎 Query: {query_text}")

    all_results: List[pd.DataFrame] = []
    for inv in inv_nrs:
        print(f"\n🔎 Searching in {inv} ...")
        faiss_idx, chunks_inv = load_or_create_embeddings(inv, client)
        if not chunks_inv:
            continue

        q_emb = np.array(
            client.embeddings.create(model=EMB_MODEL, input=translated_query).data[0].embedding,
            dtype="float32",
        ).reshape(1, -1)

        k = len(chunks_inv) if top_k is None else min(top_k, len(chunks_inv), faiss_idx.ntotal)
        D, I = faiss_idx.search(q_emb, k)
        scores = 1.0 / (1.0 + D.flatten())
        I = I.flatten()

        with sqlite3.connect(DB_PATH) as conn:
            df_meta = pd.read_sql_query(
                "SELECT inv_nr, tanap_id, start_page, pages, chunk_id, datum, plaats, vestiging, beschrijving, doc_category, text FROM documents WHERE inv_nr=? ORDER BY chunk_id",
                conn,
                params=(inv,),
            )

        valid_mask = I < len(df_meta)
        I = I[valid_mask]
        scores = scores[valid_mask]
        if len(I) == 0:
            continue

        df_res = df_meta.iloc[I].copy()
        df_res["similarity"] = scores
        
        # Extract year for filtering (done here so it's available in results)
        df_res["jaar"] = df_res["datum"].str.extract(r"(\d{4})")[0].fillna("")
        df_res["jaar_int"] = pd.to_numeric(df_res["jaar"], errors="coerce")

        # Add transcription URL
        df_res["transcription_url"] = df_res["start_page"].apply(build_transcription_url)

        # Save per-inv CSV
        out_file = RESULTS_DIR / f"{safe_filename_from_query(query_text)}-{inv}.csv"
        df_res.to_csv(out_file, index=False)
        print(f"💾 Results saved to: {out_file}")

        all_results.append(df_res)

    if all_results:
        df_all = pd.concat(all_results, ignore_index=True)
        return df_all[[
            "inv_nr",
            "tanap_id",
            "start_page",
            "pages",
            "chunk_id",
            "datum",
            "jaar",
            "jaar_int",
            "plaats",
            "vestiging",
            "beschrijving",
            "doc_category",
            "similarity",
            "transcription_url",
            "text",
        ]]
    return pd.DataFrame(columns=[
        "inv_nr",
        "tanap_id",
        "start_page",
        "pages",
        "chunk_id",
        "datum",
        "jaar",
        "jaar_int",
        "plaats",
        "vestiging",
        "beschrijving",
        "doc_category",
        "similarity",
        "transcription_url",
        "text",
    ])
