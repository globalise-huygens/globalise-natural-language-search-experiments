import os
from pathlib import Path
import traceback

import streamlit as st
import pandas as pd

from app_core import (
    list_available_inv_nrs,
    ensure_database_from_text_inputs,
    search_query,
)

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

# Show intro text in an expander - collapsed if results are present
has_results = (
    "search_results" in st.session_state
    and not st.session_state.get("search_results", pd.DataFrame()).empty
)
with st.expander("ℹ️ About this tool", expanded=not has_results):
    st.markdown(
        """
        Interactive search in historical VOC documents using OpenAI embeddings and semantic matching.
        
        **Data & Storage:**
        - The app uses precomputed embeddings for 20 inventory numbers, automatically downloaded from cloud storage on first run
        - Data is cached locally in `text-metadata-sqlite/` (database) and `embeddings/` (FAISS indexes)
        - Total data size: approximately 200MB
        
        **API Key & Costs:**
        - An OpenAI API key is required (enter in sidebar - stored only in your browser session, never on servers)
        - Each search query costs approximately $0.0002 (one embedding generation per query)
        - Optional translation (for non-Dutch queries) adds minimal cost (~$0.0001)
        - Precomputed document embeddings are reused, so they don't incur costs per query
        
        **Search Features:**
        - **Semantic Search:** Uses OpenAI embeddings (text-embedding-3-large) to find conceptually similar documents even with different wording
        - **Optional Hybrid Search (BM25):** Combine semantic search with keyword matching for better retrieval of proper names and technical terms:
          - Searches for exact word matches (after stemming) in documents and metadata
          - Blends semantic and keyword results with adjustable weight (0%–100%)
          - Shows separate scores for transparency (semantic score + BM25 score)
          - Best for queries with specific names, places, or technical terms
        - 300-word chunks with 75-word overlap across 20 inventory numbers
        - Chunks respect document boundaries (TANAP IDs) but can cross scan boundaries
        - Metadata (year, place, establishment, document category) enriches chunks and enables filtering
        - Multi-language queries supported with automatic translation to modern Dutch
        - Flexible result ranking: top K per inventory or top K overall across all inventories
        - Similarity threshold filtering to control result quality
        
        **Methodology:**
        - Text chunks are enriched with metadata building on [Renate Smit's work](https://github.com/globalise-huygens/Inventorization-and-Metadata)
        - For detailed methodology and technical documentation, see the [GitHub repository](https://github.com/globalise-huygens/globalise-natural-language-search-experiments/tree/streamlit)
        - For different settings (chunk size, overlap), run the app locally, rebuild the database and re-generate embeddings (note: this requires API key and incurs costs)
        """
    )

# Search interface - prominent at the top
st.markdown("## Search")

# Translation option
translate_query = st.checkbox(
    "Query in language other than Dutch",
    value=False,
    help="If checked, the query will be automatically translated to Dutch before searching.",
)

query_text = st.text_input(
    "Enter your search query (any language)",
    placeholder="E.g. abuse of power by the VOC, consequences of volcanic eruptions, living conditions of enslaved persons, ...",
)

run_search = st.button("Search", type="primary")

# Sidebar with configuration
with st.sidebar:
    st.header("⚙️ Configuration")

    # API key input - stored in session state only (never persisted)
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

    # Only allow DB rebuild in local development (not on Streamlit Cloud)
    is_cloud = os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD")

    st.markdown("---")
    st.subheader("🔧 Database options (local only)")

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
        options=["Per inventory number", "Overall (across all inventories)"],
        help="Choose whether to get top K results from each inventory separately, or top K results overall ranked by similarity.",
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

    # Similarity threshold
    min_similarity = st.number_input(
        "Minimum similarity threshold",
        min_value=0.0,
        max_value=1.0,
        value=0.40,
        step=0.01,
        help="Only show results with similarity score above this threshold (0-1 scale)",
    )

    # --- Result quality options ---
    st.markdown("---")
    st.subheader("📏 Result quality options")

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

    # --- Hybrid search (BM25) options ---
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

    st.markdown("---")
    st.caption("Database path: text-metadata-sqlite/voc_documents.db")
    st.caption("Embeddings folder: embeddings/")
    st.caption("BM25 indices folder: bm25_indices/")

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
                df_results = search_query(
                    query_text=query_text,
                    inv_nrs=selected_inv_nrs,
                    top_k=int(top_k),
                    translate_if_not_dutch=translate_query,
                    use_bm25=use_bm25,
                    bm25_weight=bm25_weight,
                )

                # Calculate word counts
                df_results["word_count"] = df_results["text"].str.split().str.len()

                # Apply minimum length filter
                original_count = len(df_results)
                df_results = df_results[df_results["word_count"] >= min_chunk_length]
                filtered_count = original_count - len(df_results)

                if filtered_count > 0:
                    st.info(
                        f"ℹ️ Filtered out {filtered_count} chunks shorter than {min_chunk_length} words."
                    )

                # Apply length-aware scoring if enabled
                if apply_length_adjustment:
                    # Calculate adjusted similarity with gentle length boost
                    # Formula: adjusted = raw_similarity * (0.7 + 0.3 * min(word_count/300, 1.0))
                    # This gives a 0.7x-1.0x multiplier based on length
                    df_results["length_factor"] = 0.7 + 0.3 * df_results[
                        "word_count"
                    ].apply(lambda x: min(x / 300, 1.0))
                    df_results["adjusted_similarity"] = (
                        df_results["similarity"] * df_results["length_factor"]
                    )

                    # Sort by adjusted similarity
                    df_results = df_results.sort_values(
                        "adjusted_similarity", ascending=False
                    )

                    # Use adjusted similarity for threshold filtering
                    df_results = df_results[
                        df_results["adjusted_similarity"] >= min_similarity
                    ]

                    # Apply overall top-K ranking if selected (using adjusted similarity)
                    if (
                        top_k_mode == "Overall (across all inventories)"
                        and top_k_overall
                    ):
                        df_results = df_results.nlargest(
                            int(top_k_overall), "adjusted_similarity"
                        )

                    # Keep original similarity for reference, use adjusted as primary
                    df_results["similarity_raw"] = df_results["similarity"]
                    df_results["similarity"] = df_results["adjusted_similarity"]
                else:
                    # Original behavior: use raw similarity
                    df_results = df_results[df_results["similarity"] >= min_similarity]

                    # Apply overall top-K ranking if selected
                    if (
                        top_k_mode == "Overall (across all inventories)"
                        and top_k_overall
                    ):
                        df_results = df_results.nlargest(
                            int(top_k_overall), "similarity"
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

            # Display results with clickable links
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

                        st.markdown("**Full text chunk:**")
                        st.text(row["text"])

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
