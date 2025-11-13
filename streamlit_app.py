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
    emb_ok = emb_dir.exists() and (any(emb_dir.glob("*.index")) or any(emb_dir.glob("*.db")))
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
if 'api_key' not in st.session_state:
    st.session_state.api_key = ""

st.title("🔎 VOC Natural Language Search Explorer")
st.markdown(
    """
    Interactive search in historical VOC documents using OpenAI embeddings and semantic matching.
    - Uses a pre-built database with 20 inventory numbers.
    - Uses pre-generated embeddings on 300-word chunks (with 50-word overlap) per inventory number. The chunks can cross scan borders, but not document borders.
    - Any search query can be entered; select the box 'Query in language other than Dutch' to auto-translate the query to modern Dutch.
    - For different settings (e.g. chunk size, overlap), run the app locally and rebuild the database.
    """
)

with st.sidebar:
    st.header("⚙️ Configuration")
    
    # API key input - stored in session state only (never persisted)
    api_key_input = st.text_input(
        "OpenAI API key",
        value=st.session_state.api_key,
        type="password",
        help="Your API key is only stored in memory during this session and never saved to disk or servers."
    )
    
    # Update session state when user changes the key
    if api_key_input != st.session_state.api_key:
        st.session_state.api_key = api_key_input
        # Set environment variable for app_core to use
        if api_key_input:
            os.environ["OPENAI_API_KEY"] = api_key_input
    
    # Only allow DB rebuild in local development (not on Streamlit Cloud)
    is_cloud = os.getenv("STREAMLIT_SHARING_MODE") or os.getenv("STREAMLIT_CLOUD")
    
    if not is_cloud:
        st.markdown("---")
        st.subheader("🔧 Database options (local only)")
        build_db = st.checkbox("Rebuild database", value=False, help="Reads all CSVs and reconstructs chunks.")
        apply_norm = st.checkbox("Normalize spelling", value=False)
        chunk_size = st.number_input("Chunk size (words)", min_value=100, max_value=2000, value=300, step=50)
        overlap = st.number_input("Overlap (words)", min_value=0, max_value=500, value=75, step=10)
    else:
        build_db = False
        apply_norm = True
        chunk_size = 300
        overlap = 75
        st.info("📌 Database and embeddings are pre-computed. Only search is available.")
    
    st.markdown("---")
    st.subheader("🔍 Search options")

    inv_options = list_available_inv_nrs()
    selected_inv_nrs = st.multiselect("Inventory numbers", inv_options, default=inv_options[:20] if len(inv_options) > 0 else [])

    top_k = st.number_input("Top K results per inventory number", min_value=1, max_value=2000, value=25)

    st.markdown("---")
    st.caption("Database path: text-metadata-sqlite/voc_documents.db")
    st.caption("Embeddings folder: embeddings/")

# Use the session state API key
api_key = st.session_state.api_key

if build_db:
    if not api_key:
        st.error("API key required for building database (for potential embedding generation later).")
    else:
        with st.spinner("Building database from CSVs..."):
            try:
                total = ensure_database_from_text_inputs(
                    apply_normalization=apply_norm, chunk_size=chunk_size, overlap=overlap
                )
                st.success(f"Database built with {total} chunks.")
            except Exception as e:
                st.error(f"Error building database: {e}")
                st.code(traceback.format_exc())

st.markdown("## 🔍 Search Query")

# Translation option
translate_query = st.checkbox(
    "Query in language other than Dutch", 
    value=False,
    help="If checked, the query will be automatically translated to Dutch before searching."
)

query_text = st.text_input(
    "Enter your search query (any language)",
    placeholder="E.g. events around a specific place...",
)

run_search = st.button("Search")

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
                )
                # Store results in session state
                st.session_state['search_results'] = df_results
                st.session_state['query_text'] = query_text
            except Exception as e:
                st.error(f"Search failed: {e}")
                st.code(traceback.format_exc())
                st.session_state['search_results'] = pd.DataFrame()

# Display results if available
if 'search_results' in st.session_state and not st.session_state['search_results'].empty:
    df_results = st.session_state['search_results']
    
    st.success(f"{len(df_results)} results found across {len(selected_inv_nrs)} inventory numbers.")
    
    # Get filter options from actual results
    years_available = df_results['jaar_int'].dropna().astype(int)
    if len(years_available) > 0:
        year_min_result = int(years_available.min())
        year_max_result = int(years_available.max())
    else:
        year_min_result = year_max_result = None
    
    doc_categories_available = df_results['doc_category'].dropna().unique().tolist()
    vestigingen_available = df_results['vestiging'].dropna().unique().tolist()
    
    # Get unique plaatsen from results (handling pipe-separated values)
    plaatsen_set = set()
    for plaats in df_results['plaats'].dropna():
        if isinstance(plaats, str):
            plaatsen_set.update([p.strip() for p in plaats.split("|") if p.strip()])
    plaatsen_available = sorted(list(plaatsen_set))
    
    # Add sticky CSS for filter column
    st.markdown("""
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
    """, unsafe_allow_html=True)
    
    # Create two-column layout: filters on left, results on right
    filter_col, results_col = st.columns([1, 3])
    
    # Filters section (left column)
    with filter_col:
        st.subheader("Filters")
        
        st.markdown("#### Period")
        st.caption("Based on document creation date")
        
        if year_min_result and year_max_result:
            # Create histogram data
            year_counts = df_results['jaar_int'].value_counts().sort_index()
            
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
                    label_visibility="collapsed"
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
            label_visibility="collapsed"
        )
        
        st.markdown("#### Establishment")
        vestigingen_filter = st.multiselect(
            "Select establishments",
            options=vestigingen_available,
            default=[],
            label_visibility="collapsed"
        )
        
        st.markdown("#### Place")
        plaatsen_filter = st.multiselect(
            "Select places",
            options=plaatsen_available,
            default=[],
            label_visibility="collapsed"
        )
    
    # Apply filters to results
    df_display = df_results.copy()
    
    if apply_year_filter and year_min_result and year_max_result:
        df_display = df_display[
            (df_display['jaar_int'] >= year_range[0]) & 
            (df_display['jaar_int'] <= year_range[1])
        ]
    
    if doc_categories_filter:
        df_display = df_display[df_display['doc_category'].isin(doc_categories_filter)]
    
    if vestigingen_filter:
        df_display = df_display[df_display['vestiging'].isin(vestigingen_filter)]
    
    if plaatsen_filter:
        df_display = df_display[
            df_display['plaats'].apply(
                lambda x: any(p in str(x).split("|") for p in plaatsen_filter) if pd.notna(x) else False
            )
        ]
    
    # Sort by similarity
    df_display = df_display.sort_values("similarity", ascending=False).reset_index(drop=True)
    
    # Results section (right column)
    with results_col:
        if df_display.empty:
            st.warning("No results match the selected filters. Try adjusting your filter criteria.")
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
                pages_list = str(row['pages']).split(';') if pd.notna(row['pages']) and row['pages'] else [row['start_page']]
                pages_display = ", ".join(pages_list) if len(pages_list) > 1 else pages_list[0]
                
                with st.expander(
                    f"**{idx + 1}.** Inv {row['inv_nr']} | Similarity: {row['similarity']:.3f} | {row['datum']} | {row['plaats']}"
                ):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**TANAP ID:** {row['tanap_id']}")
                        st.markdown(f"**Document Category:** {row['doc_category']}")
                        st.markdown(f"**Establishment:** {row['vestiging']}")
                        st.markdown(f"**Place:** {row['plaats']}")
                        st.markdown(f"**Description:** {row['beschrijving']}")
                        st.markdown(f"**Date:** {row['datum']}")
                        st.markdown(f"**Pages:** {pages_display}")
                        
                        st.markdown("**Full text chunk:**")
                        st.text(row['text'])
                    
                    with col2:
                        if row['transcription_url']:
                            st.markdown(f"[🔗 View transcription]({row['transcription_url']})")

            # Expand raw table
            with st.expander("📊 Full results table", expanded=False):
                st.dataframe(
                    df_display[[
                        "inv_nr",
                        "tanap_id",
                        "similarity",
                        "datum",
                        "jaar",
                        "plaats",
                        "vestiging",
                        "doc_category",
                        "pages",
                        "transcription_url",
                        "text",
                    ]],
                    width='stretch',
                )

            # Optional: similarity histogram
            with st.expander("📊 Similarity distribution"):
                st.bar_chart(df_display["similarity"])

            # Download combined CSV
            safe_name = st.session_state.get('query_text', 'query').replace(" ", "_")[:60]
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
