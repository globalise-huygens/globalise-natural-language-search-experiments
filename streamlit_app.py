import os
from pathlib import Path
import traceback

import streamlit as st
import pandas as pd

from app_core import (
    list_available_inv_nrs,
    ensure_database_from_text_inputs,
    search_query,
    get_translations_by_chunks,
    get_openai_client,
)
from language_utils import get_queries_for_compare_mode, get_query_for_mode

# --- Ensure required data is present (download + unzip if needed) ---
# We always run this check on startup. It's fast when files already exist and
# avoids relying on fragile cloud env vars.


def _data_ready() -> bool:
    db_ok = Path("text-metadata-sqlite/voc_documents.db").exists()
    emb_dir = Path("embeddings")
    emb_ok = emb_dir.exists() and (
        any(emb_dir.glob("*.index")) or any(emb_dir.glob("*.db"))
    )
    return db_ok and emb_ok


@st.cache_resource(show_spinner=False)
def _prepare_data_once() -> str:
    """Idempotent, cached data preparation. Returns a short status string."""
    if _data_ready():
        return "already-present"
    try:
        # Lazy import so local runs without the helper still work
        from download_data import ensure_data_files
    except Exception as e:
        # Surface a clear error if helper is missing in deployments
        raise RuntimeError(
            f"Data helper missing: {e}. Ensure 'download_data.ensure_data_files' exists."
        )
    ensure_data_files()
    return "downloaded"


with st.spinner("🔄 Preparing data files (one-time)"):
    try:
        status = _prepare_data_once()
        if status == "downloaded":
            st.success("Data files downloaded and extracted.")
    except Exception as e:
        st.error(f"Failed to prepare data files: {e}")
        st.stop()

st.set_page_config(
    page_title="VOC Natural Language Search",
    page_icon="🔎",
    layout="wide",
)

# Initialize session state for API key (ephemeral, not persisted)
if "api_key" not in st.session_state:
    st.session_state.api_key = ""

st.title("VOC Natural Language Search Explorer")

if "about_expanded" not in st.session_state:
    st.session_state["about_expanded"] = True

# Show intro text in an expander - keep state across reruns
with st.expander("ℹ️ About this tool", expanded=st.session_state["about_expanded"]):
    st.markdown(
        """
        Bilingual semantic search in historical VOC documents with **original Dutch** and **translated English** embeddings.
        
        **Search Modes:**
        - **Original (Dutch):** Semantic search using Dutch embeddings. Best for Dutch-language queries.
        - **Translated (English):** Semantic search using English embeddings (Claude Haiku translations). Best for English-language queries.
        - **Compare Both:** Side-by-side view of both embedding modes to see which documents rank highest in each language.
        
        **Data & Storage:**
        - Precomputed embeddings for inventory 1120 (1,583 chunks in both Dutch and English)
        - Automatically downloaded on first run (~200MB)
        - Cached locally: `text-metadata-sqlite/voc_documents.db`, `embeddings/` (FAISS indices)
        
        **API Key & Costs:**
        - OpenAI API key required (browser session only, never saved to disk)
        - Per-query cost: ~$0.0002 (one embedding generation)
        - Query translation (when needed): ~$0.0001
        - Precomputed document embeddings reused—no recurring cost
        
        **Querying in Different Languages:**
        - **Dutch queries:** Use "Original (Dutch)" or "Compare Both" mode
        - **English queries:** Use "Translated (English)" or "Compare Both" mode
        - Check "Query in language other than Dutch" to auto-translate queries to Dutch for searching the original corpus
        
        **Search Features:**
        - **Semantic Search:** OpenAI embeddings (text-embedding-3-small, 1536 dimensions) find conceptually similar documents
        - **Optional Hybrid Search (BM25):** Combine semantic with exact keyword matching (best for names/places)
        - **Advanced Filtering:** Year range, document category, establishment, place
        - **Length-aware Scoring:** Optional boost for longer, more content-rich chunks
        - **Bilingual Display:** Every result shows original Dutch + translated English text
        - 300-word chunks with 75-word overlap, respecting document boundaries
        - Flexible ranking: top K per inventory or top K overall
        
        **Methodology:**
        - Metadata enrichment based on [Renate Smit's work](https://github.com/globalise-huygens/Inventorization-and-Metadata)
        - Translations by Claude Haiku 4.5 (claude-haiku-4-5-20251001)
        - For technical details, see [GitHub repository](https://github.com/globalise-huygens/globalise-natural-language-search-experiments/tree/streamlit)
        """
    )

# Sidebar with configuration - needs to be FIRST to set selected_mode
with st.sidebar:
    st.header("⚙️ Configuration")

    # ===== 1. API KEY =====
    st.subheader("🔑 API Key")
    api_key_input = st.text_input(
        "OpenAI API key",
        value=st.session_state.api_key,
        type="password",
        help="Your API key is only stored in memory during this session and never saved to disk or servers.",
    )

    # Update session state when user changes the key
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        # Set environment variable for app_core to use
        if api_key_input:
            os.environ["OPENAI_API_KEY"] = api_key_input

    # ===== 2. SEARCH EMBEDDINGS MODE =====
    st.markdown("---")
    st.subheader("🌐 Search embeddings")

    search_mode = st.radio(
        "Select embedding source",
        options=["Original (Dutch)", "Translated (English)", "Compare Both"],
        index=0,
        help="Choose which embeddings to use. 'Compare Both' shows side-by-side results from both modes.",
    )

    # Convert UI label to mode string
    mode_map = {
        "Original (Dutch)": "original",
        "Translated (English)": "translated",
        "Compare Both": "both",
    }
    selected_mode = mode_map[search_mode]

    # ===== 3. SEARCH OPTIONS =====
    st.markdown("---")
    st.subheader("🔍 Search options")

    inv_options = list_available_inv_nrs()
    selected_inv_nrs = st.multiselect(
        "Inventory numbers",
        inv_options,
        default=inv_options[:20] if len(inv_options) > 0 else [],
    )

    # Top-K mode selection
    top_k_mode = st.radio(
        "Result ranking mode",
        options=["Overall (across all inventories)", "Per inventory number"],
        help="Choose whether to get top K results overall ranked by similarity, or top K results from each inventory separately.",
    )

    if top_k_mode == "Per inventory number":
        top_k = st.number_input(
            "Top K results per inventory number", min_value=1, max_value=2000, value=25
        )
        top_k_overall = None
    else:
        top_k = st.number_input(
            "Top K results per inventory number (before overall ranking)",
            min_value=1,
            max_value=2000,
            value=100,
            help="Fetch this many from each inventory, then rank and limit overall",
        )
        top_k_overall = st.number_input(
            "Top K results overall", min_value=1, max_value=2000, value=50
        )

    # ===== 4. RESULT QUALITY OPTIONS =====
    st.markdown("---")
    st.subheader("📏 Result quality options")

    # Similarity threshold
    min_similarity = st.number_input(
        "Minimum similarity threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.40,
        step=0.01,
        help="Only show results with similarity score above this threshold (0-1 scale)",
    )

    min_chunk_length = st.number_input(
        "Minimum chunk length (words)",
        min_value=0,
        max_value=300,
        value=100,
        step=25,
        help="Filter out chunks shorter than this. Helps remove short fragments that may score artificially high.",
    )

    apply_length_adjustment = st.checkbox(
        "Apply length-aware scoring",
        value=True,
        help="Boost longer chunks to balance semantic similarity with content richness. Reduces bias toward short, overly-focused chunks.",
    )

    if apply_length_adjustment:
        st.caption(
            "ℹ️ Length adjustment applies a gentle boost to longer chunks (up to target length of 300 words) to counteract the tendency of short chunks to score artificially high in semantic similarity."
        )

    # ===== 5. HYBRID SEARCH OPTIONS =====
    st.markdown("---")
    st.subheader("🔤 Hybrid search (experimental)")

    use_bm25 = st.checkbox(
        "Enable BM25 keyword search",
        value=False,
        help="Combine semantic search with exact keyword matching. Useful for finding specific names, places, or technical terms that might be missed by semantic search alone.",
    )

    if use_bm25:
        bm25_weight = st.slider(
            "BM25 weight",
            min_value=0.0,
            max_value=1.0,
            value=0.3,
            step=0.05,
            help="Balance between semantic (0.0) and keyword (1.0) matching. 0.3 means 70% semantic + 30% keyword.",
        )
        st.caption(
            "ℹ️ BM25 excels at finding exact matches for names, places, and technical terms. Semantic search is better for conceptual queries. This hybrid approach lets you experiment with both."
        )
    else:
        bm25_weight = 0.0

    # ===== 6. DATABASE OPTIONS =====
    st.markdown("---")
    st.subheader("🔧 Database options (local only)")

    # Only allow DB rebuild in local development (not on Streamlit Cloud)
    is_cloud = os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD")

    if is_cloud:
        # In cloud: show info message only, no controls
        st.info(
            "📌 Database and embeddings are pre-computed. Database rebuild options are only available when running locally."
        )
        build_db = False
        apply_norm = True
        chunk_size = 300
        overlap = 75
    else:
        # Local development: show interactive controls
        build_db = st.checkbox(
            "Rebuild database",
            value=False,
            help="Reads all CSVs and reconstructs chunks.",
        )
        apply_norm = st.checkbox(
            "Normalize spelling", value=False, help="Apply text normalization."
        )
        chunk_size = st.number_input(
            "Chunk size (words)",
            min_value=100,
            max_value=2000,
            value=300,
            step=50,
            help="Number of words per chunk.",
        )
        overlap = st.number_input(
            "Overlap (words)",
            min_value=0,
            max_value=500,
            value=75,
            step=10,
            help="Word overlap between chunks.",
        )

    st.markdown("---")
    st.caption("Database: text-metadata-sqlite/voc_documents.db")
    st.caption("Embeddings: embeddings/")
    st.caption("BM25 indices: bm25_indices/")

# Search interface - after sidebar so selected_mode is defined
st.markdown("## Search")

if "last_selected_mode" not in st.session_state:
    st.session_state["last_selected_mode"] = selected_mode

if st.session_state.get("last_selected_mode") != selected_mode:
    st.session_state["last_selected_mode"] = selected_mode
    st.session_state["search_results"] = pd.DataFrame()
    st.session_state["query_text"] = ""
    st.session_state["about_expanded"] = False

if selected_mode == "both":
    st.info(
        "ℹ️ In **Compare Both** mode, queries are automatically translated to each language (Dutch for original embeddings, English for translated embeddings) based on language detection."
    )

with st.form(key="search_form"):
    query_text = st.text_input(
        "Enter your search query (any language)",
        placeholder="E.g. abuse of power by the VOC, consequences of volcanic eruptions, living conditions of enslaved persons, ...",
    )
    run_search = st.form_submit_button("Search", type="primary")

# Use the session state API key
api_key = st.session_state.api_key

if build_db:
    if not api_key:
        st.error(
            "API key required for building database (for potential embedding generation later)."
        )
    else:
        with st.spinner("Building database from CSVs..."):
            try:
                total = ensure_database_from_text_inputs(
                    apply_normalization=apply_norm,
                    chunk_size=chunk_size,
                    overlap=overlap,
                )
                st.success(f"Database built with {total} chunks.")
            except Exception as e:
                st.error(f"Error building database: {e}")
                st.code(traceback.format_exc())

# Process search
if run_search:
    if not api_key:
        st.error("Please enter a valid OpenAI API key first.")
    elif not selected_inv_nrs:
        st.warning("Please select at least one inventory number.")
    else:
        with st.spinner("Loading/generating embeddings and performing search..."):
            try:
                st.session_state["about_expanded"] = False

                def _postprocess_results(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
                    if df.empty:
                        return df, 0

                    df = df.copy()
                    df["word_count"] = df["text"].str.split().str.len()

                    original_count = len(df)
                    df = df[df["word_count"] >= min_chunk_length]
                    filtered_count = original_count - len(df)

                    if apply_length_adjustment:
                        df["length_factor"] = 0.7 + 0.3 * df["word_count"].apply(
                            lambda x: min(x / 300, 1.0)
                        )
                        df["adjusted_similarity"] = (
                            df["similarity"] * df["length_factor"]
                        )

                        df = df.sort_values("adjusted_similarity", ascending=False)
                        df = df[df["adjusted_similarity"] >= min_similarity]

                        if (
                            top_k_mode == "Overall (across all inventories)"
                            and top_k_overall
                        ):
                            df = df.nlargest(int(top_k_overall), "adjusted_similarity")

                        df["similarity_raw"] = df["similarity"]
                        df["similarity"] = df["adjusted_similarity"]
                    else:
                        df = df[df["similarity"] >= min_similarity]

                        if (
                            top_k_mode == "Overall (across all inventories)"
                            and top_k_overall
                        ):
                            df = df.nlargest(int(top_k_overall), "similarity")

                    return df, filtered_count

                # For "Compare Both" mode, use smart language-aware query handling
                if selected_mode == "both":
                    client = get_openai_client()
                    query_info = get_queries_for_compare_mode(query_text, client)
                    detected_lang = query_info["detected_lang"]
                    dutch_query = query_info["dutch_query"]
                    english_query = query_info["english_query"]

                    lang_label = {
                        "nl": "🇳🇱 Dutch",
                        "en": "🇬🇧 English",
                        "other": "🌍 Other",
                    }
                    st.info(
                        f"Query language detected: {lang_label.get(detected_lang, 'Unknown')}. "
                        "Auto-translation applied where needed."
                    )
                    if detected_lang != "nl":
                        st.caption(f"Dutch query used: {dutch_query}")
                    if detected_lang != "en":
                        st.caption(f"English query used: {english_query}")

                    # Search with language-specific queries
                    df_results_original = search_query(
                        query_text=dutch_query,
                        inv_nrs=selected_inv_nrs,
                        top_k=int(top_k),
                        translate_if_not_dutch=False,  # Already handled
                        use_bm25=use_bm25,
                        bm25_weight=bm25_weight,
                        mode="original",
                    )
                    df_results_original["search_source"] = "original"

                    df_results_translated = search_query(
                        query_text=english_query,
                        inv_nrs=selected_inv_nrs,
                        top_k=int(top_k),
                        translate_if_not_dutch=False,  # Already handled
                        use_bm25=use_bm25,
                        bm25_weight=bm25_weight,
                        mode="translated",
                    )
                    df_results_translated["search_source"] = "translated"

                    df_results_original, filtered_original = _postprocess_results(
                        df_results_original
                    )
                    df_results_translated, filtered_translated = _postprocess_results(
                        df_results_translated
                    )

                    filtered_count = filtered_original + filtered_translated

                    # Merge results
                    df_results = pd.concat(
                        [df_results_original, df_results_translated], ignore_index=True
                    )
                else:
                    # Standard search for Original or Translated mode (language-aware)
                    client = get_openai_client()
                    query_info = get_query_for_mode(query_text, selected_mode, client)
                    mode_query = query_info["query"]
                    detected_lang = query_info["detected_lang"]

                    lang_label = {
                        "nl": "🇳🇱 Dutch",
                        "en": "🇬🇧 English",
                        "other": "🌍 Other",
                    }
                    if mode_query != query_text:
                        st.info(
                            f"Query language detected: {lang_label.get(detected_lang, 'Unknown')}. "
                            f"Translated query used: {mode_query}"
                        )
                    else:
                        st.info(
                            f"Query language detected: {lang_label.get(detected_lang, 'Unknown')}. "
                            "No translation applied."
                        )

                    df_results = search_query(
                        query_text=mode_query,
                        inv_nrs=selected_inv_nrs,
                        top_k=int(top_k),
                        translate_if_not_dutch=False,
                        use_bm25=use_bm25,
                        bm25_weight=bm25_weight,
                        mode=selected_mode,
                    )
                    df_results, filtered_count = _postprocess_results(df_results)

                if filtered_count > 0:
                    st.info(
                        f"ℹ️ Filtered out {filtered_count} chunks shorter than {min_chunk_length} words."
                    )

                # Store results in session state
                st.session_state["search_results"] = df_results
                st.session_state["query_text"] = query_text
                st.session_state["min_similarity"] = min_similarity
                st.session_state["top_k_mode"] = top_k_mode
                st.session_state["apply_length_adjustment"] = apply_length_adjustment

                # Show message if no results meet the threshold
                if df_results.empty:
                    st.warning(
                        f"No results found with similarity ≥ {min_similarity:.2f}. "
                        f"Try lowering the minimum similarity threshold in the sidebar (currently set to {min_similarity:.2f})."
                    )
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.code(traceback.format_exc())
                st.session_state["search_results"] = pd.DataFrame()

# Display results if available
if (
    "search_results" in st.session_state
    and not st.session_state["search_results"].empty
):
    df_results = st.session_state["search_results"]

    # Get search parameters from session
    applied_threshold = st.session_state.get("min_similarity", 0.0)
    applied_mode = st.session_state.get("top_k_mode", "Per inventory number")
    length_adjusted = st.session_state.get("apply_length_adjustment", False)

    # Show search info
    info_text = f"{len(df_results)} results found"
    if applied_mode == "Overall (across all inventories)":
        info_text = f"{len(df_results)} top results (overall ranking"
    else:
        info_text += " (top K per inventory"

    if length_adjusted:
        info_text += f", length-adjusted similarity ≥ {applied_threshold:.2f})"
    else:
        info_text += f", similarity ≥ {applied_threshold:.2f})"

    st.success(info_text)

    if length_adjusted:
        st.info(
            "ℹ️ **Length-aware scoring enabled**: Longer chunks receive a boost (up to 1.0x for 300+ words, 0.7x for very short) to balance semantic match with content richness."
        )

    # Check if results are from "Compare Both" mode
    is_compare_mode = "search_source" in df_results.columns

    if is_compare_mode:
        st.info(
            "📊 **Side-by-side comparison:** Results below show original Dutch (left) and translated English (right) embeddings separately."
        )

    # Get filter options from actual results
    years_available = df_results["jaar_int"].dropna().astype(int)
    if len(years_available) > 0:
        year_min_result = int(years_available.min())
        year_max_result = int(years_available.max())
    else:
        year_min_result = year_max_result = None

    doc_categories_available = df_results["doc_category"].dropna().unique().tolist()
    vestigingen_available = df_results["vestiging"].dropna().unique().tolist()

    # Get unique plaatsen from results (handling pipe-separated values)
    plaatsen_set = set()
    for plaats in df_results["plaats"].dropna():
        if isinstance(plaats, str):
            plaatsen_set.update([p.strip() for p in plaats.split("|") if p.strip()])
    plaatsen_available = sorted(list(plaatsen_set))

    # Add sticky CSS for filter column
    st.markdown(
        """
    <style>
    /* Sticky filter panel */
    @media (min-width: 768px) {
        [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stVerticalBlock"] {
            position: sticky !important;
            top: 3.5rem !important;
            max-height: calc(100vh - 5rem) !important;
            overflow-y: auto !important;
            align-self: flex-start !important;
        }
    }
    
    /* Smooth scrolling for filter panel */
    [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stVerticalBlock"] {
        scrollbar-width: thin;
    }
    
    /* Mobile: no sticky behavior */
    @media (max-width: 767px) {
        [data-testid="stHorizontalBlock"] > div:first-child [data-testid="stVerticalBlock"] {
            position: relative !important;
        }
    }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Create two-column layout: filters on left, results on right
    filter_col, results_col = st.columns([1, 3])

    # Filters section (left column)
    with filter_col:
        st.subheader("Filters")

        st.markdown("#### Period")
        st.caption("Based on document creation date")

        if year_min_result and year_max_result:
            # Create histogram data
            year_counts = df_results["jaar_int"].value_counts().sort_index()

            # Show histogram
            st.bar_chart(year_counts)

            # Only show slider if there's a range of years
            if year_min_result < year_max_result:
                year_range = st.slider(
                    "Year range",
                    min_value=year_min_result,
                    max_value=year_max_result,
                    value=(year_min_result, year_max_result),
                    step=1,
                    label_visibility="collapsed",
                )
                apply_year_filter = True
            else:
                # All results from single year
                st.info(f"All from {year_min_result}")
                year_range = (year_min_result, year_max_result)
                apply_year_filter = False
        else:
            st.info("No year data available")
            apply_year_filter = False

        st.markdown("#### Document Category")
        doc_categories_filter = st.multiselect(
            "Select categories",
            options=doc_categories_available,
            default=[],
            label_visibility="collapsed",
        )

        st.markdown("#### Establishment")
        vestigingen_filter = st.multiselect(
            "Select establishments",
            options=vestigingen_available,
            default=[],
            label_visibility="collapsed",
        )

        st.markdown("#### Place")
        plaatsen_filter = st.multiselect(
            "Select places",
            options=plaatsen_available,
            default=[],
            label_visibility="collapsed",
        )

    # Apply filters to results
    df_display = df_results.copy()

    if apply_year_filter and year_min_result and year_max_result:
        df_display = df_display[
            (df_display["jaar_int"] >= year_range[0])
            & (df_display["jaar_int"] <= year_range[1])
        ]

    if doc_categories_filter:
        df_display = df_display[df_display["doc_category"].isin(doc_categories_filter)]

    if vestigingen_filter:
        df_display = df_display[df_display["vestiging"].isin(vestigingen_filter)]

    if plaatsen_filter:
        df_display = df_display[
            df_display["plaats"].apply(
                lambda x: any(p in str(x).split("|") for p in plaatsen_filter)
                if pd.notna(x)
                else False
            )
        ]

    # Sort by similarity
    df_display = df_display.sort_values("similarity", ascending=False).reset_index(
        drop=True
    )

    # Results section (right column)
    with results_col:
        if df_display.empty:
            st.warning(
                "No results match the selected filters. Try adjusting your filter criteria."
            )
        else:
            # Show summary metrics
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Inventory numbers", len(selected_inv_nrs))
            col_b.metric("Filtered results", len(df_display))
            col_c.metric("Highest similarity", f"{df_display['similarity'].max():.3f}")

            # SPECIAL HANDLING FOR COMPARE BOTH MODE
            if is_compare_mode:
                # Split results into original and translated
                df_original = df_display[
                    df_display["search_source"] == "original"
                ].reset_index(drop=True)
                df_translated = df_display[
                    df_display["search_source"] == "translated"
                ].reset_index(drop=True)

                st.markdown("### 📄 Side-by-Side Comparison")

                # Create two columns
                comp_col_left, comp_col_right = st.columns(2)

                # Helper function to fetch text pairs for a chunk
                def get_text_pair_for_chunk(inv_nr, tanap_id, chunk_id):
                    try:
                        translations = get_translations_by_chunks(
                            str(inv_nr), [int(chunk_id)], tanap_id=str(tanap_id)
                        )
                        trans_key = (str(inv_nr), int(chunk_id))
                        if trans_key in translations:
                            return translations[trans_key]
                    except Exception:
                        pass
                    return {}

                # LEFT: Original (Dutch) embeddings results - but show both languages
                with comp_col_left:
                    st.markdown("#### 🇳🇱 From Dutch Embeddings")
                    if df_original.empty:
                        st.info("No results from original Dutch embeddings")
                    else:
                        st.caption(f"**{len(df_original)} results**")
                        for display_idx, (idx, row) in enumerate(
                            df_original.iterrows()
                        ):
                            pages_list = (
                                str(row["pages"]).split(";")
                                if pd.notna(row["pages"]) and row["pages"]
                                else [row["start_page"]]
                            )
                            pages_display = (
                                ", ".join(pages_list)
                                if len(pages_list) > 1
                                else pages_list[0]
                            )

                            header = f"**{display_idx + 1}.** Inv. {row['inv_nr']} | {row['start_page']} | {row['similarity']:.3f}"
                            if "word_count" in row and pd.notna(row["word_count"]):
                                header += f" | {int(row['word_count'])}w"
                            header += f" | {row['plaats']}"

                            with st.expander(header, expanded=False):
                                st.markdown(f"**TANAP ID:** {row['tanap_id']}")
                                st.markdown(f"**Date:** {row['datum']}")
                                st.markdown(f"**Pages:** {pages_display}")

                                text_pair = get_text_pair_for_chunk(
                                    row["inv_nr"], row["tanap_id"], row["chunk_id"]
                                )

                                st.markdown("**Dutch (original):**")
                                st.text_area(
                                    "Dutch",
                                    value=row["text"],
                                    height=80,
                                    disabled=True,
                                    key=f"dutch_left_{row['inv_nr']}_{row['chunk_id']}_{display_idx}",
                                )

                                st.markdown("**English (translation):**")
                                translated = text_pair.get("text_translated_detailed")
                                if translated:
                                    st.text_area(
                                        "Translation",
                                        value=translated,
                                        height=80,
                                        disabled=True,
                                        key=f"trans_left_{row['inv_nr']}_{row['chunk_id']}_{display_idx}",
                                    )
                                else:
                                    st.info("Translation not available")

                # RIGHT: Translated (English) embeddings results - but show both languages
                with comp_col_right:
                    st.markdown("#### 🇬🇧 From English Embeddings")
                    if df_translated.empty:
                        st.info("No results from translated English embeddings")
                    else:
                        st.caption(f"**{len(df_translated)} results**")
                        for display_idx, (idx, row) in enumerate(
                            df_translated.iterrows()
                        ):
                            pages_list = (
                                str(row["pages"]).split(";")
                                if pd.notna(row["pages"]) and row["pages"]
                                else [row["start_page"]]
                            )
                            pages_display = (
                                ", ".join(pages_list)
                                if len(pages_list) > 1
                                else pages_list[0]
                            )

                            header = f"**{display_idx + 1}.** Inv. {row['inv_nr']} | {row['start_page']} | {row['similarity']:.3f}"
                            if "word_count" in row and pd.notna(row["word_count"]):
                                header += f" | {int(row['word_count'])}w"
                            header += f" | {row['plaats']}"

                            with st.expander(header, expanded=False):
                                st.markdown(f"**TANAP ID:** {row['tanap_id']}")
                                st.markdown(f"**Date:** {row['datum']}")
                                st.markdown(f"**Pages:** {pages_display}")

                                text_pair = get_text_pair_for_chunk(
                                    row["inv_nr"], row["tanap_id"], row["chunk_id"]
                                )

                                st.markdown("**Dutch (original):**")
                                original = text_pair.get("text_original")
                                if original:
                                    st.text_area(
                                        "Original",
                                        value=original,
                                        height=80,
                                        disabled=True,
                                        key=f"orig_right_{row['inv_nr']}_{row['chunk_id']}_{display_idx}",
                                    )
                                else:
                                    st.info("Original Dutch text not available")

                                st.markdown("**English (translation):**")
                                translated = (
                                    text_pair.get("text_translated_detailed")
                                    or row["text"]
                                )
                                st.text_area(
                                    "English",
                                    value=translated,
                                    height=80,
                                    disabled=True,
                                    key=f"english_right_{row['inv_nr']}_{row['chunk_id']}_{display_idx}",
                                )

            # NORMAL MODE: Display all results with both original and translation
            else:
                st.markdown("### 📄 Results")

                for idx, row in df_display.iterrows():
                    # Parse pages string to show all pages
                    pages_list = (
                        str(row["pages"]).split(";")
                        if pd.notna(row["pages"]) and row["pages"]
                        else [row["start_page"]]
                    )
                    pages_display = (
                        ", ".join(pages_list) if len(pages_list) > 1 else pages_list[0]
                    )

                    # Build header with similarity info
                    header = f"**{idx + 1}.** Inv. no. {row['inv_nr']} | {row['start_page']} | Similarity: {row['similarity']:.3f}"

                    # Add score breakdown for hybrid search
                    if "bm25_score" in row and pd.notna(row["bm25_score"]):
                        header += f" (semantic: {row['semantic_score']:.3f}, BM25: {row['bm25_score']:.3f})"

                    # Add word count if available
                    if "word_count" in row and pd.notna(row["word_count"]):
                        header += f" | {int(row['word_count'])} words"

                    # Add raw similarity if length adjustment was applied
                    if (
                        length_adjusted
                        and "similarity_raw" in row
                        and pd.notna(row["similarity_raw"])
                    ):
                        header += f" (raw: {row['similarity_raw']:.3f})"

                    # Add search source indicator if in comparison mode
                    if "search_source" in row and pd.notna(row["search_source"]):
                        source_label = (
                            "🇳🇱 Dutch"
                            if row["search_source"] == "original"
                            else "🇬🇧 English"
                        )
                        header += f" | {source_label}"

                    header += f" | {row['datum']} | {row['plaats']}"

                    with st.expander(header):
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.markdown(f"**TANAP ID:** {row['tanap_id']}")
                            st.markdown(f"**Document Category:** {row['doc_category']}")
                            st.markdown(f"**Establishment:** {row['vestiging']}")
                            st.markdown(f"**Place:** {row['plaats']}")
                            st.markdown(f"**Description:** {row['beschrijving']}")
                            st.markdown(f"**Date:** {row['datum']}")
                            st.markdown(f"**Pages:** {pages_display}")

                            # Show word count prominently
                            if "word_count" in row and pd.notna(row["word_count"]):
                                st.markdown(
                                    f"**Chunk length:** {int(row['word_count'])} words"
                                )

                            # Determine what text to show based on search mode
                            text_pair = get_translations_by_chunks(
                                str(row["inv_nr"]),
                                [int(row["chunk_id"])],
                                tanap_id=str(row["tanap_id"]),
                            ).get((str(row["inv_nr"]), int(row["chunk_id"])), {})

                            if selected_mode == "translated":
                                # In translated mode, row["text"] is English
                                st.markdown("**Original Dutch text:**")
                                original_text = text_pair.get("text_original")
                                if original_text:
                                    st.text(original_text)
                                else:
                                    st.info("Original Dutch text not available")

                                st.markdown("---")
                                st.markdown("**Translated English text:**")
                                translated_text = (
                                    text_pair.get("text_translated_detailed")
                                    or row["text"]
                                )
                                st.text(translated_text)
                            else:
                                # In original mode, row["text"] is Dutch
                                st.markdown("**Original Dutch text:**")
                                st.text(row["text"])

                                st.markdown("---")
                                st.markdown("**Translated English text:**")
                                translated_text = text_pair.get(
                                    "text_translated_detailed"
                                )
                                if translated_text:
                                    st.text(translated_text)
                                else:
                                    st.info("Translation not available")

                        with col2:
                            if row["transcription_url"]:
                                st.markdown(
                                    f"[🔗 View transcription]({row['transcription_url']})"
                                )

            # Expand raw table
            with st.expander("📊 Full results table", expanded=False):
                # Build columns list dynamically based on what's available
                base_columns = [
                    "inv_nr",
                    "tanap_id",
                    "similarity",
                ]

                # Add score columns if available
                if "semantic_score" in df_display.columns:
                    base_columns.append("semantic_score")
                if "bm25_score" in df_display.columns:
                    base_columns.append("bm25_score")

                # Add word_count if available
                if "word_count" in df_display.columns:
                    base_columns.append("word_count")

                # Add raw similarity if length adjustment was applied
                if length_adjusted and "similarity_raw" in df_display.columns:
                    base_columns.append("similarity_raw")

                # Add remaining columns
                base_columns.extend(
                    [
                        "datum",
                        "jaar",
                        "plaats",
                        "vestiging",
                        "doc_category",
                        "pages",
                        "transcription_url",
                        "text",
                    ]
                )

                # Only include columns that exist in the dataframe
                display_columns = [
                    col for col in base_columns if col in df_display.columns
                ]

                st.dataframe(
                    df_display[display_columns],
                    width="stretch",
                )

            # Optional: similarity histogram
            with st.expander("📊 Similarity distribution"):
                st.bar_chart(df_display["similarity"])

            # Download combined CSV
            safe_name = st.session_state.get("query_text", "query").replace(" ", "_")[
                :60
            ]
            csv_bytes = df_display.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Download results as CSV",
                data=csv_bytes,
                file_name=f"results_{safe_name}.csv",
                mime="text/csv",
            )

st.markdown("---")
st.caption(
    "This experimental interface uses semantic embeddings (OpenAI) and FAISS for similarity search."
)
