import os
from pathlib import Path
import traceback

import streamlit as st
import pandas as pd

from app_core import (
    list_available_inv_nrs,
    ensure_database_from_text_inputs,
    search_query,
    get_filter_options,
)


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
    - Build the database from source files first.
    - Generate embeddings (one-time) per inventory number.
    - Then perform a search query; the query can be auto-translated to modern Dutch.
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
        st.info("💡 **Note:** To use the new metadata filters (Place, Establishment, etc.), you need to rebuild the database from the `text_input_metadata` folder.")
        build_db = st.checkbox("Rebuild database", value=False, help="Reads all CSVs and reconstructs chunks.")
        apply_norm = st.checkbox("Normalize spelling", value=True)
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
    selected_inv_nrs = st.multiselect("Inventory numbers", inv_options, default=inv_options[:5] if len(inv_options) > 0 else [])

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
    value="sounds and noises associated with natural disasters",
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
    
    # Filters section (applied to results)
    with st.expander("🎛️ Filter Results", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Period Filter")
            st.caption("Filter based on document creation date (TANAP metadata)")
            
            if year_min_result and year_max_result:
                # Create histogram data
                year_counts = df_results['jaar_int'].value_counts().sort_index()
                
                # Show histogram
                st.bar_chart(year_counts)
                
                year_range = st.slider(
                    "Select year range",
                    min_value=year_min_result,
                    max_value=year_max_result,
                    value=(year_min_result, year_max_result),
                    step=1
                )
                apply_year_filter = True
            else:
                st.info("No year data available in results")
                apply_year_filter = False
            
            st.markdown("### Document Category")
            doc_categories_filter = st.multiselect(
                "Filter by document category",
                options=doc_categories_available,
                default=[]
            )
        
        with col2:
            st.markdown("### Establishment")
            vestigingen_filter = st.multiselect(
                "Filter by establishment",
                options=vestigingen_available,
                default=[]
            )
            
            st.markdown("### Place")
            plaatsen_filter = st.multiselect(
                "Filter by place",
                options=plaatsen_available,
                default=[]
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
    
    if df_display.empty:
        st.warning("No results match the selected filters. Try adjusting your filter criteria.")
    else:

            # Show summary metrics
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Inventory numbers", len(selected_inv_nrs))
            col_b.metric("Total results", len(df_display))
            col_c.metric("Highest similarity", f"{df_display['similarity'].max():.3f}")

            # Display results with clickable links
            st.markdown("### 📄 Results")
            
            for idx, row in df_display.iterrows():
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
                        st.markdown(f"**Start Page:** {row['start_page']}")
                        
                        st.markdown("**Text excerpt:**")
                        st.text(row['text'][:500] + "..." if len(str(row['text'])) > 500 else row['text'])
                    
                    with col2:
                        if row['transcription_url']:
                            st.markdown(f"[� View transcription]({row['transcription_url']})")

            # Expand raw table
            with st.expander("📊 Full results table", expanded=False):
                st.dataframe(
                    df_display[[
                        "inv_nr",
                        "tanap_id",
                        "similarity",
                        "datum",
                        "plaats",
                        "vestiging",
                        "doc_category",
                        "start_page",
                        "transcription_url",
                        "text",
                    ]],
                    width='stretch',
                )

            # Optional: similarity histogram
            with st.expander("📊 Similarity distribution"):
                st.bar_chart(df_display["similarity"])

            # Download combined CSV
            safe_name = query_text.replace(" ", "_")[:60]
            csv_bytes = df_display.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="💾 Download results as CSV",
                data=csv_bytes,
                file_name=f"results_{safe_name}.csv",
                mime="text/csv",
            )
        else:
            st.warning("No results found.")

st.markdown("---")
st.caption(
    "This experimental interface uses semantic embeddings (OpenAI) and FAISS for similarity search."
)
