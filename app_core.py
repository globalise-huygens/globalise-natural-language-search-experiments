import os
import re
import sqlite3
import json
from pathlib import Path
from typing import Iterable, List, Tuple, Optional
import pickle

import faiss
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
from tqdm import tqdm
from rank_bm25 import BM25Okapi
from nltk.stem.snowball import SnowballStemmer

try:
    from langdetect import detect, LangDetectException
except ImportError:
    detect = None
    LangDetectException = None


# --- Environment & constants ---
load_dotenv()

DATA_DIR = Path("text_input_metadata")
DB_PATH = Path("text-metadata-sqlite/voc_documents.db")
EMB_DIR = Path("embeddings")
BM25_DIR = Path("bm25_indices")
RESULTS_DIR = Path("results")

EMB_MODEL = "text-embedding-3-large"
CHAT_MODEL = "gpt-4o-mini"


def get_openai_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not set. Create a .env file or export the variable."
        )
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
def chunk_within_docs(
    df_inv: pd.DataFrame, chunk_size: int, overlap: int
) -> List[dict]:
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
        page_spans = []
        for i, (start_idx, filename) in enumerate(page_boundaries):
            end_idx = (
                page_boundaries[i + 1][0]
                if i + 1 < len(page_boundaries)
                else word_count
            )
            page_spans.append((start_idx, end_idx, filename))
        start = 0
        while start < len(all_words):
            end = min(start + chunk_size, len(all_words))
            chunk_words = all_words[start:end]
            pages_in_chunk = [
                filename
                for span_start, span_end, filename in page_spans
                if span_start < end and span_end > start
            ]
            if not pages_in_chunk:
                pages_in_chunk = [df_doc.iloc[-1]["filename"]]
            else:
                # Preserve order while removing duplicates
                seen = set()
                pages_in_chunk = [
                    p for p in pages_in_chunk if not (p in seen or seen.add(p))
                ]
            all_chunks.append(
                {
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
                    "doc_category": meta["doc_category"],
                }
            )
            start += chunk_size - overlap
    return all_chunks


# --- DB utilities ---
def ensure_database_from_text_inputs(
    apply_normalization: bool = True, chunk_size: int = 300, overlap: int = 75
) -> int:
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
        df_temp = df_temp.rename(
            columns={
                "text": "text",
                "filename": "filename",
                "TANAP_ID": "tanap_id",
                "TANAP_Boundaries": "tanap_boundaries",
                "DATUM": "datum",
                "PLAATS": "plaats",
                "VESTIGING": "vestiging",
                "BESCHRIJVING": "beschrijving",
                "GLOBALISE_document_category": "doc_category",
            }
        )
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
            all_chunks = chunk_within_docs(
                df_inv, chunk_size=chunk_size, overlap=overlap
            )

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
                        str(chunk_data["text"]),
                    ),
                )
            total_chunks += len(all_chunks)
        conn.commit()

    return total_chunks


def migrate_db_add_translation_columns() -> None:
    """
    Add translation columns to the documents table if they don't exist.
    Idempotent - safe to call multiple times.
    """
    if not DB_PATH.exists():
        print("Database does not exist yet")
        return

    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        # Check if columns already exist
        cur.execute("PRAGMA table_info(documents)")
        columns = {row[1] for row in cur.fetchall()}

        # Add columns if missing
        if "text_translated_detailed" not in columns:
            cur.execute(
                "ALTER TABLE documents ADD COLUMN text_translated_detailed TEXT DEFAULT NULL"
            )
            print("✓ Added text_translated_detailed column")

        if "text_translated_clean" not in columns:
            cur.execute(
                "ALTER TABLE documents ADD COLUMN text_translated_clean TEXT DEFAULT NULL"
            )
            print("✓ Added text_translated_clean column")

        if "translation_model" not in columns:
            cur.execute(
                "ALTER TABLE documents ADD COLUMN translation_model TEXT DEFAULT NULL"
            )
            print("✓ Added translation_model column")

        if "translation_date" not in columns:
            cur.execute(
                "ALTER TABLE documents ADD COLUMN translation_date TEXT DEFAULT NULL"
            )
            print("✓ Added translation_date column")

        conn.commit()


def import_translations_from_json(json_file: Path) -> int:
    """
    Import translations from JSON file into the database.
    Updates existing rows with translation columns based on inv_nr + tanap_id + chunk_id matching.
    Falls back to rowid if inv_nr/tanap_id/chunk_id are missing.
    Returns number of translations imported.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    if not json_file.exists():
        raise FileNotFoundError(f"Translation JSON file not found at {json_file}")

    # First ensure columns exist
    migrate_db_add_translation_columns()

    # Load translations from JSON
    with open(json_file, "r", encoding="utf-8") as f:
        translations = json.load(f)

    print(f"📥 Importing {len(translations)} translations from {json_file.name}...")

    # Update database with translations
    imported = 0
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()

        for trans in translations:
            inv_nr = trans.get("inv_nr")
            tanap_id = trans.get("tanap_id")
            chunk_id = trans.get("chunk_id")
            rowid = trans.get("rowid")

            if inv_nr is not None and tanap_id is not None and chunk_id is not None:
                cur.execute(
                    """
                    UPDATE documents
                    SET text_translated_detailed = ?,
                        text_translated_clean = ?,
                        translation_model = ?,
                        translation_date = ?
                    WHERE inv_nr = ? AND tanap_id = ? AND chunk_id = ?
                    """,
                    (
                        trans.get("text_translated_detailed"),
                        trans.get("text_translated_clean"),
                        trans.get("translation_model"),
                        trans.get("translation_date"),
                        str(inv_nr),
                        str(tanap_id),
                        int(chunk_id),
                    ),
                )
            elif rowid is not None:
                cur.execute(
                    """
                    UPDATE documents
                    SET text_translated_detailed = ?,
                        text_translated_clean = ?,
                        translation_model = ?,
                        translation_date = ?
                    WHERE rowid = ?
                    """,
                    (
                        trans.get("text_translated_detailed"),
                        trans.get("text_translated_clean"),
                        trans.get("translation_model"),
                        trans.get("translation_date"),
                        rowid,
                    ),
                )
            else:
                continue

            imported += 1

        conn.commit()

    print(f"✅ Imported {imported} translations")
    return imported


def list_available_inv_nrs() -> List[str]:
    """List inventory numbers from DB if present, else from text_input_metadata CSV names."""
    if DB_PATH.exists():
        with sqlite3.connect(DB_PATH) as conn:
            rows = conn.execute(
                "SELECT DISTINCT inv_nr FROM documents ORDER BY inv_nr"
            ).fetchall()
            invs = [r[0] for r in rows]
            if invs:
                return invs
    # Fallback to files
    return sorted([p.stem.split("_")[0] for p in DATA_DIR.glob("*.csv")])


def get_translations_by_chunks(
    inv_nr: str, chunk_ids: List[int], tanap_id: Optional[str] = None
) -> dict:
    """
    Fetch translations for specific chunks.

    Args:
        inv_nr: Inventory number
        chunk_ids: List of chunk IDs to fetch translations for

    Returns:
        Dict mapping (inv_nr, chunk_id) tuples to translation data:
        {
            (inv_nr, chunk_id): {
                'text_translated_detailed': str,
                'text_translated_clean': str
            },
            ...
        }
    """
    if not DB_PATH.exists():
        return {}

    translations = {}
    if not chunk_ids:
        return translations

    try:
        with sqlite3.connect(DB_PATH) as conn:
            # Create placeholder string for parameterized query
            placeholders = ",".join("?" * len(chunk_ids))
            tanap_clause = " AND tanap_id = ?" if tanap_id is not None else ""
            query = f"""
                SELECT chunk_id, text, text_translated_detailed, text_translated_clean
                FROM documents
                WHERE inv_nr = ?{tanap_clause} AND chunk_id IN ({placeholders})
            """
            params = [inv_nr] + ([tanap_id] if tanap_id is not None else []) + chunk_ids
            rows = conn.execute(query, params).fetchall()

            for chunk_id, text_original, text_detailed, text_clean in rows:
                translations[(inv_nr, chunk_id)] = {
                    "text_original": text_original,
                    "text_translated_detailed": text_detailed,
                    "text_translated_clean": text_clean,
                }
    except Exception as e:
        print(f"⚠️  Error fetching translations: {e}")

    return translations


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
                conn,
            )["doc_category"].tolist()
        else:
            doc_cats = []

        # Get unique vestigingen (if column exists)
        if "vestiging" in columns:
            vest = pd.read_sql_query(
                "SELECT DISTINCT vestiging FROM documents WHERE vestiging IS NOT NULL AND vestiging != ''",
                conn,
            )["vestiging"].tolist()
        else:
            vest = []

        # Get unique plaatsen (if column exists, handling pipe-separated values)
        if "plaats" in columns:
            plaatsen_raw = pd.read_sql_query(
                "SELECT DISTINCT plaats FROM documents WHERE plaats IS NOT NULL AND plaats != ''",
                conn,
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
                conn,
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
def _embeddings_file(inv_nr: str, mode: str = "original") -> Path:
    """
    Get path to FAISS embedding index file.

    Args:
        inv_nr: Inventory number
        mode: 'original' for Dutch text, 'translated' for English text

    Returns:
        Path object for the FAISS index file
    """
    EMB_DIR.mkdir(exist_ok=True)
    if mode == "original":
        return EMB_DIR / f"{inv_nr}.index"
    elif mode == "translated":
        return EMB_DIR / f"{inv_nr}_translated.index"
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'original' or 'translated'.")


def _bm25_file(inv_nr: str) -> Path:
    """Get path to BM25 index file."""
    BM25_DIR.mkdir(exist_ok=True)
    return BM25_DIR / f"{inv_nr}.pkl"


# ====== ⚖️ WEIGHTS — used for both embeddings and BM25 ======
WEIGHT_PLAATS = 2.0
WEIGHT_VESTIGING = 2.0
WEIGHT_JAAR = 1.5
WEIGHT_BESCHRIJVING = 0.5
WEIGHT_TEXT = 1.0
# Bump this when changing BM25 preprocessing so caches refresh
BM25_INDEX_VERSION = 2
# ============================================================


def _repeat_weighted(text, weight):
    n = max(1, int(round(weight)))
    return (" " + text) * n


def _expand_places(raw_str):
    if not raw_str or not isinstance(raw_str, str):
        return ""
    parts = [p.strip() for p in raw_str.split("|") if p.strip()]
    return " ".join([f"Plaats: {p}." for p in parts]) if parts else ""


def _safe_col(df, col):
    """Always return a Series (string type), even if column missing."""
    if col in df.columns:
        return df[col].fillna("").astype(str)
    return pd.Series([""] * len(df), index=df.index, dtype=str)


def _prepare_combined_text_for_embeddings(df_chunks: pd.DataFrame) -> List[str]:
    """
    Build lightweight combined text for embeddings.
    Unlike BM25, we don't heavily repeat metadata - we just include it once.
    This keeps token count under embedding model's limit.
    """
    df_chunks = df_chunks.copy()
    df_chunks["text"] = _safe_col(df_chunks, "text")
    df_chunks["plaats"] = _safe_col(df_chunks, "plaats")
    df_chunks["vestiging"] = _safe_col(df_chunks, "vestiging")
    df_chunks["beschrijving"] = _safe_col(df_chunks, "beschrijving")
    df_chunks["datum"] = _safe_col(df_chunks, "datum")
    df_chunks["jaar"] = df_chunks["datum"].str.extract(r"(\d{4})")[0].fillna("")

    combined_texts = []
    for idx, row in df_chunks.iterrows():
        # Build metadata once (not repeated)
        plaats_str = _expand_places(row["plaats"])
        metadata_parts = [
            plaats_str if plaats_str else "",
            f"Vestiging: {row['vestiging']}" if row["vestiging"] else "",
            f"Jaar: {row['jaar']}" if row["jaar"] else "",
            f"Beschrijving: {row['beschrijving']}" if row["beschrijving"] else "",
        ]
        metadata = " ".join([p for p in metadata_parts if p]).strip()

        # Get main text and truncate if needed to avoid exceeding token limits
        main_text = row["text"].strip()
        # Truncate to ~6000 chars to ensure we stay under 8192 token limit
        if len(main_text) > 6000:
            main_text = main_text[:6000] + "..."

        # Combine metadata with main text
        if metadata and main_text:
            combined = f"{metadata}. {main_text}"
        elif metadata:
            combined = metadata
        elif main_text:
            combined = main_text
        else:
            combined = ""

        combined_texts.append(combined)

    return combined_texts


def _prepare_combined_text(df_chunks: pd.DataFrame) -> pd.DataFrame:
    """Build combined_text with weighted metadata for embeddings/BM25."""
    df_chunks = df_chunks.copy()
    df_chunks["text"] = _safe_col(df_chunks, "text")
    df_chunks["plaats"] = _safe_col(df_chunks, "plaats")
    df_chunks["vestiging"] = _safe_col(df_chunks, "vestiging")
    df_chunks["beschrijving"] = _safe_col(df_chunks, "beschrijving")
    df_chunks["datum"] = _safe_col(df_chunks, "datum")

    df_chunks["jaar"] = df_chunks["datum"].str.extract(r"(\d{4})")[0].fillna("")

    df_chunks["combined_text"] = (
        _repeat_weighted(df_chunks["plaats"].apply(_expand_places), WEIGHT_PLAATS)
        + _repeat_weighted(
            "Vestiging: " + df_chunks["vestiging"] + ".", WEIGHT_VESTIGING
        )
        + _repeat_weighted("Jaar: " + df_chunks["jaar"] + ".", WEIGHT_JAAR)
        + _repeat_weighted(
            "Beschrijving: " + df_chunks["beschrijving"] + ".", WEIGHT_BESCHRIJVING
        )
        + _repeat_weighted(df_chunks["text"], WEIGHT_TEXT)
    )

    df_chunks = df_chunks[df_chunks["combined_text"].str.strip() != ""]
    return df_chunks


def create_or_load_bm25_index(inv_nr: str) -> Tuple[BM25Okapi, List[str]]:
    """
    Create and cache a BM25 index for an inventory number.
    Returns (BM25Okapi instance, list of texts)
    """
    bm25_file = _bm25_file(inv_nr)

    # Check if cached index exists
    if bm25_file.exists():
        try:
            with open(bm25_file, "rb") as f:
                data = pickle.load(f)
            version = data.get("version", 1) if isinstance(data, dict) else 1
            if (
                isinstance(data, dict)
                and version == BM25_INDEX_VERSION
                and "bm25" in data
                and "texts" in data
            ):
                return data["bm25"], data["texts"]
            else:
                print(
                    f"ℹ️ BM25 cache for {inv_nr} is outdated (version {version}); rebuilding."
                )
        except Exception as e:
            print(f"⚠️ Error loading BM25 cache for {inv_nr}: {e}")

    # Load chunks from database
    if not DB_PATH.exists():
        raise FileNotFoundError(
            "SQLite database not found. Build it from text inputs first."
        )

    with sqlite3.connect(DB_PATH) as conn:
        df_chunks = pd.read_sql_query(
            "SELECT text, plaats, vestiging, beschrijving, datum FROM documents WHERE inv_nr=? ORDER BY chunk_id",
            conn,
            params=(inv_nr,),
        )

    if df_chunks.empty:
        raise ValueError(f"No data found for inv_nr {inv_nr} in database.")

    # Build combined text with weighted metadata (matches embedding input)
    df_chunks = _prepare_combined_text(df_chunks)
    if df_chunks.empty:
        raise ValueError(f"All chunks for {inv_nr} are empty after cleaning.")

    texts = df_chunks["combined_text"].tolist()

    # Initialize stemmer and stop words for Dutch
    import string

    stemmer = SnowballStemmer("dutch")

    stop_words = {
        "de",
        "het",
        "een",
        "en",
        "van",
        "op",
        "in",
        "is",
        "dat",
        "met",
        "voor",
        "aan",
        "om",
        "te",
        "er",
        "niet",
        "als",
        "uit",
        "daar",
        "wat",
        "wie",
        "welke",
        "deze",
        "die",
        "wij",
        "ik",
        "je",
        "hij",
        "zij",
        "zich",
        "hun",
        "mij",
        "me",
        "jou",
        "u",
        "ma",
        "pa",
        "ja",
        "nee",
        "ook",
        "nog",
        "heel",
        "very",
        "this",
        "that",
        "be",
        "have",
    }

    def tokenize_text(text):
        """Tokenize text: remove punctuation, filter stop words, stem words."""
        # Remove punctuation and convert to lowercase
        text = text.translate(str.maketrans("", "", string.punctuation)).lower()
        # Split into words
        tokens = text.split()
        # Filter and stem
        stemmed = []
        for word in tokens:
            # Skip short words and stop words
            if len(word) > 2 and word not in stop_words:
                # Apply stemming to normalize plural/singular and other forms
                stem = stemmer.stem(word)
                stemmed.append(stem)
        return stemmed

    tokenized_corpus = [tokenize_text(text) for text in texts]

    # Create BM25 index
    bm25 = BM25Okapi(tokenized_corpus)

    # Cache to disk
    bm25_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(bm25_file, "wb") as f:
            pickle.dump(
                {"version": BM25_INDEX_VERSION, "bm25": bm25, "texts": texts}, f
            )
    except Exception as e:
        print(f"⚠️ Could not cache BM25 index: {e}")

    return bm25, texts

    EMB_DIR.mkdir(exist_ok=True)
    return EMB_DIR / f"{inv_nr}.index"


def load_or_create_embeddings(
    inv_nr: str, client: OpenAI, mode: str = "original", use_cache: bool = True
) -> Tuple[faiss.IndexFlatL2, List[str]]:
    """
    Load FAISS index for an inv_nr or create it from the SQLite documents.
    Uses lightweight metadata in embeddings (included once, not repeated).

    Args:
        inv_nr: Inventory number
        client: OpenAI client
        mode: 'original' for Dutch text, 'translated' for English text
        use_cache: Whether to use cached embeddings if they exist

    Returns:
        (faiss_index, chunks_texts) tuple
        - faiss_index: FAISS index for searching
        - chunks_texts: List of text strings corresponding to embedding vectors

    On Streamlit Cloud, only loads pre-existing embeddings (no creation).
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            "SQLite database not found. Build it from text inputs first."
        )

    with sqlite3.connect(DB_PATH) as conn:
        df_chunks = pd.read_sql_query(
            "SELECT * FROM documents WHERE inv_nr=? ORDER BY chunk_id",
            conn,
            params=(inv_nr,),
        )

    if df_chunks.empty:
        raise ValueError(f"No data found for inv_nr {inv_nr} in the database.")

    # Determine which text column to use based on mode
    if mode == "original":
        # Use original Dutch text with lightweight metadata
        chunks_inv = _prepare_combined_text_for_embeddings(df_chunks)
    elif mode == "translated":
        # Check if translations exist
        if (
            "text_translated_clean" not in df_chunks.columns
            or df_chunks["text_translated_clean"].isna().all()
        ):
            raise ValueError(
                f"No translated text found for {inv_nr}. "
                "Please run translate_chunks.py and import_translations.py first."
            )
        # Build combined text with translated text and lightweight metadata
        df_chunks = df_chunks.copy()
        df_chunks["text"] = df_chunks["text_translated_clean"].fillna("").astype(str)
        chunks_inv = _prepare_combined_text_for_embeddings(df_chunks)
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'original' or 'translated'.")

    if not chunks_inv:
        raise ValueError(f"All chunks for {inv_nr} are empty after cleaning.")

    # Filter out empty chunks
    chunks_inv = [c for c in chunks_inv if c.strip()]
    if not chunks_inv:
        raise ValueError(f"All chunks for {inv_nr} are empty after filtering.")

    emb_file = _embeddings_file(inv_nr, mode=mode)
    if use_cache and emb_file.exists():
        faiss_idx = faiss.read_index(str(emb_file))
        return faiss_idx, chunks_inv

    # Check if running on Streamlit Cloud
    is_cloud = os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD")
    if is_cloud:
        raise RuntimeError(
            f"Embeddings for {inv_nr} ({mode} mode) not found. On Streamlit Cloud, all embeddings must be precomputed. "
            "Please generate embeddings locally and commit them to the repository."
        )

    # Create embeddings (only in local development)
    embeddings: List[List[float]] = []
    batch_size = 20  # Small batch size to stay under token limit
    print(f"🧠 Computing {mode} embeddings for {inv_nr} ({len(chunks_inv)} chunks)...")
    for i in tqdm(range(0, len(chunks_inv), batch_size)):
        batch = chunks_inv[i : i + batch_size]
        try:
            resp = client.embeddings.create(model=EMB_MODEL, input=batch)
            batch_embeddings = [
                r.embedding for r in resp.data if hasattr(r, "embedding")
            ]
            embeddings.extend(batch_embeddings)
        except Exception as e:
            print(f"❌ Embedding batch {i} failed: {e}")
            continue

    if not embeddings:
        raise RuntimeError(f"No embeddings created for {inv_nr} ({mode} mode).")

    emb_arr = np.array(embeddings, dtype="float32")
    dim = emb_arr.shape[1]
    faiss_idx = faiss.IndexFlatL2(dim)
    faiss_idx.add(emb_arr)
    faiss.write_index(faiss_idx, str(emb_file))
    print(f"💾 Saved {mode} FAISS index for {inv_nr} -> {emb_file}")
    return faiss_idx, chunks_inv


def is_dutch(text: str) -> bool:
    """Detect if the text is Dutch using a simple heuristic."""
    dutch_words = [
        "de",
        "het",
        "een",
        "en",
        "van",
        "op",
        "in",
        "is",
        "niet",
        "dat",
        "met",
    ]
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
    return (
        "".join([c for c in q if c.isalnum() or c in "-_ "]).strip().replace(" ", "_")
    )


def search_query(
    query_text: str,
    inv_nrs: Iterable[str],
    top_k: int | None = None,
    translate_if_not_dutch: bool = True,
    use_bm25: bool = False,
    bm25_weight: float = 0.3,
    mode: str = "original",
) -> pd.DataFrame:
    """
    Search across one or more inventory numbers and return a unified DataFrame.
    Supports hybrid semantic + BM25 keyword search.
    Filters are applied in the UI after getting results.

    Args:
        query_text: The search query
        inv_nrs: List of inventory numbers to search
        top_k: Maximum results per inventory number
        translate_if_not_dutch: Auto-translate non-Dutch queries to Dutch
        use_bm25: If True, use hybrid semantic + BM25 search
        bm25_weight: Weight for BM25 in hybrid scoring (0.0-1.0), semantic gets (1 - bm25_weight)
        mode: Search mode - 'original' (Dutch embeddings), 'translated' (English embeddings), or 'both' (search both and merge)
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

    if use_bm25:
        print(f"🔄 Using hybrid search (semantic + BM25, weight={bm25_weight})")

    # Validate mode
    if mode not in ("original", "translated", "both"):
        raise ValueError(
            f"Invalid mode: {mode}. Must be 'original', 'translated', or 'both'."
        )

    if mode == "both":
        print(f"🔄 Comparison mode: searching both original and translated embeddings")

    all_results: List[pd.DataFrame] = []
    modes_to_search = ["original", "translated"] if mode == "both" else [mode]

    for search_mode in modes_to_search:
        for inv in inv_nrs:
            mode_label = f" ({search_mode})" if mode == "both" else ""
            print(f"\n🔎 Searching in {inv}{mode_label} ...")
            try:
                faiss_idx, chunks_inv = load_or_create_embeddings(
                    inv, client, mode=search_mode
                )
            except (ValueError, FileNotFoundError) as e:
                print(f"⚠️  Skipped: {e}")
                continue
            if not chunks_inv:
                continue

        # --- Semantic search (FAISS) ---
        q_emb = np.array(
            client.embeddings.create(model=EMB_MODEL, input=translated_query)
            .data[0]
            .embedding,
            dtype="float32",
        ).reshape(1, -1)

        k = (
            len(chunks_inv)
            if top_k is None
            else min(top_k, len(chunks_inv), faiss_idx.ntotal)
        )
        D, I = faiss_idx.search(q_emb, k)
        semantic_scores = 1.0 / (1.0 + D.flatten())
        I = I.flatten()

        # --- BM25 search (if enabled) ---
        final_scores = semantic_scores.copy()
        bm25_scores_arr = None

        if use_bm25:
            try:
                bm25_idx, bm25_texts = create_or_load_bm25_index(inv)
                # Tokenize query with same preprocessing and stemming
                import string

                stemmer = SnowballStemmer("dutch")

                stop_words = {
                    "de",
                    "het",
                    "een",
                    "en",
                    "van",
                    "op",
                    "in",
                    "is",
                    "dat",
                    "met",
                    "voor",
                    "aan",
                    "om",
                    "te",
                    "er",
                    "niet",
                    "als",
                    "uit",
                    "daar",
                    "wat",
                    "wie",
                    "welke",
                    "deze",
                    "die",
                    "wij",
                    "ik",
                    "je",
                    "hij",
                    "zij",
                    "zich",
                    "hun",
                    "mij",
                    "me",
                    "jou",
                    "u",
                    "ma",
                    "pa",
                    "ja",
                    "nee",
                    "ook",
                    "nog",
                    "heel",
                    "very",
                    "this",
                    "that",
                    "be",
                    "have",
                }

                # Apply same tokenization as in index creation
                query_text = translated_query.translate(
                    str.maketrans("", "", string.punctuation)
                ).lower()
                query_tokens = []
                for word in query_text.split():
                    if len(word) > 2 and word not in stop_words:
                        query_tokens.append(stemmer.stem(word))

                if query_tokens:  # Only proceed if there are meaningful tokens
                    # Filter query tokens to only those present in the corpus vocabulary
                    all_corpus_tokens = set()
                    with sqlite3.connect(DB_PATH) as conn:
                        df_corpus = pd.read_sql_query(
                            "SELECT text FROM documents WHERE inv_nr=?",
                            conn,
                            params=(inv,),
                        )

                    for text in df_corpus["text"].fillna("").astype(str):
                        text = text.translate(
                            str.maketrans("", "", string.punctuation)
                        ).lower()
                        for word in text.split():
                            if len(word) > 2 and word not in stop_words:
                                all_corpus_tokens.add(stemmer.stem(word))

                    filtered_query_tokens = [
                        t for t in query_tokens if t in all_corpus_tokens
                    ]

                    # If nothing matches the corpus vocabulary, keep BM25 neutral but present
                    if not filtered_query_tokens:
                        bm25_scores_topk = np.zeros_like(I, dtype=float)
                    else:
                        # Get BM25 scores for all documents
                        bm25_doc_scores = bm25_idx.get_scores(filtered_query_tokens)

                        # Get BM25 scores for the top-k semantic results
                        bm25_scores_topk = bm25_doc_scores[I]

                    # Normalize BM25 scores relative to their max (keep zeros if unmatched)
                    if len(bm25_scores_topk) > 0:
                        bm25_max = bm25_scores_topk.max()
                        if bm25_max > 0:
                            bm25_scores_arr = bm25_scores_topk / bm25_max
                        else:
                            bm25_scores_arr = np.zeros_like(bm25_scores_topk)

                        # Scale BM25 contribution to semantic score scale for clearer interpretations
                        sem_max = semantic_scores.max()
                        bm25_scaled = bm25_scores_arr * sem_max

                        # Weighted blend without forcing scores to 1.0
                        final_scores = ((1 - bm25_weight) * semantic_scores) + (
                            bm25_weight * bm25_scaled
                        )
            except Exception as e:
                print(f"⚠️ BM25 search failed for {inv}: {e}")
                # Fall back to semantic-only scores

        with sqlite3.connect(DB_PATH) as conn:
            # Select appropriate text column based on search mode
            text_column = (
                "text_translated_clean" if search_mode == "translated" else "text"
            )
            df_meta = pd.read_sql_query(
                f"SELECT inv_nr, tanap_id, start_page, pages, chunk_id, datum, plaats, vestiging, beschrijving, doc_category, {text_column} as text FROM documents WHERE inv_nr=? ORDER BY chunk_id",
                conn,
                params=(inv,),
            )

        valid_mask = I < len(df_meta)
        I = I[valid_mask]
        semantic_scores = semantic_scores[valid_mask]
        final_scores = final_scores[valid_mask]
        if bm25_scores_arr is not None:
            bm25_scores_arr = bm25_scores_arr[valid_mask]

        if len(I) == 0:
            continue

        # Sort by final scores and apply top_k
        sort_idx = np.argsort(-final_scores)
        if top_k is not None:
            sort_idx = sort_idx[:top_k]
        I = I[sort_idx]
        semantic_scores = semantic_scores[sort_idx]
        final_scores = final_scores[sort_idx]
        if bm25_scores_arr is not None:
            bm25_scores_arr = bm25_scores_arr[sort_idx]

        df_res = df_meta.iloc[I].copy()
        df_res["similarity"] = final_scores
        df_res["semantic_score"] = semantic_scores
        if bm25_scores_arr is not None:
            df_res["bm25_score"] = bm25_scores_arr

        # Add search mode source when doing comparison
        if mode == "both":
            df_res["search_source"] = search_mode

        # Extract year for filtering (done here so it's available in results)
        df_res["jaar"] = df_res["datum"].str.extract(r"(\d{4})")[0].fillna("")
        df_res["jaar_int"] = pd.to_numeric(df_res["jaar"], errors="coerce")

        # Add transcription URL
        df_res["transcription_url"] = df_res["start_page"].apply(
            build_transcription_url
        )

        # Save per-inv CSV
        out_file = RESULTS_DIR / f"{safe_filename_from_query(query_text)}-{inv}.csv"
        df_res.to_csv(out_file, index=False)
        print(f"💾 Results saved to: {out_file}")

        all_results.append(df_res)

    if all_results:
        df_all = pd.concat(all_results, ignore_index=True)
        # Build column list, including optional score columns
        columns = [
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
            "semantic_score",
        ]
        if "bm25_score" in df_all.columns:
            columns.append("bm25_score")
        if "search_source" in df_all.columns:
            columns.append("search_source")
        columns.extend(["transcription_url", "text"])
        return df_all[columns]

    # Return empty DataFrame with appropriate columns
    columns = [
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
        "semantic_score",
        "transcription_url",
        "text",
    ]
    if use_bm25:
        columns.insert(columns.index("transcription_url"), "bm25_score")
    return pd.DataFrame(columns=columns)
