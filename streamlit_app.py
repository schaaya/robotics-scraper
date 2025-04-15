# if abm_file is not None:
#     import fitz  # type: ignore # PyMuPDF
#     doc = fitz.open(stream=abm_file.read(), filetype="pdf")
#     abm_context = "\n\n".join([page.get_text() for page in doc])
#     if generate_summary:
#         abm_summary = generate_pdf_summary(abm_context, model_selection)
#     #abm_summary = generate_pdf_summary(abm_context, model_selection)  
    


import streamlit as st
from streamlit_tags import st_tags_sidebar
import pandas as pd
import json
import re
import sys
import asyncio
import numpy as np
from markdown_io import get_paginated_urls


# ---local imports---
from scraper import scrape_urls
from markdown import fetch_and_store_markdowns
from assets import MODELS_USED
from api_management import get_supabase_client
from abm_docs import extract_text_from_pdf, get_abm_report_text
from utils import generate_pdf_summary

# Windows compatibility
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

st.set_page_config(page_title="Robotics Articles Scraper")
supabase = get_supabase_client()
if supabase is None:
    st.error("🚨 Supabase is not configured!")
    st.stop()

st.title("🤖 Robotics Articles Scraper")

# Session state setup
if 'scraping_state' not in st.session_state:
    st.session_state['scraping_state'] = 'idle'
if 'results' not in st.session_state:
    st.session_state['results'] = None

st.sidebar.title("ABM Strategy Settings")

with st.sidebar.expander("🔑 Enter API Keys", expanded=False):
    for model, required_keys in MODELS_USED.items():
        for key_name in required_keys:
            st.text_input(
                f"{key_name} ({model})",
                type="password",
                key=f"{key_name}_{model}"
            )

    st.session_state['SUPABASE_URL'] = st.text_input("SUPABASE URL")
    st.session_state['SUPABASE_ANON_KEY'] = st.text_input("SUPABASE ANON KEY", type="password")

generate_summary = st.sidebar.toggle("Generate Summary from ABM PDF", value=False)
abm_file = st.sidebar.file_uploader("Upload ABM PDF", type=["pdf"])

abm_context = ""
abm_summary = ""
if abm_file:
    import fitz
    from litellm.exceptions import RateLimitError

    doc = fitz.open(stream=abm_file.read(), filetype="pdf")
    abm_context = "\n\n".join([page.get_text() for page in doc])

    if generate_summary:
        try:
            abm_summary = generate_pdf_summary(abm_context, "gpt-4o")
        except RateLimitError:
            st.warning("Rate limit hit for gpt-4o — falling back to gpt-4o-mini.")
            abm_summary = generate_pdf_summary(abm_context, "gpt-4o-mini")

DEFAULT_FIELDS = [
    "Article Name", "Article Summary", "Article Date", "Article URL",
    "Company", "Company Info", "Region", "Company Size", "Raised Funding",
    "Recent Developments", "Partnerships", "Media Mentions", "Focus",
    "Humanoid Robotics Use Case", "Single Use Cases", "Task Streamlining",
    "Project launch date", "Relevancy Score", "Correlation Reason"
]

show_tags = st.sidebar.toggle("Enable Scraping")
fields = DEFAULT_FIELDS.copy()
if show_tags:
    manual_fields = st_tags_sidebar(label='Enter Fields to Extract:', value=[], key='fields_input')
    if manual_fields:
        fields = list(set(DEFAULT_FIELDS + manual_fields))

st.sidebar.markdown("---")

model_selection = st.sidebar.selectbox("Select Model", options=list(MODELS_USED.keys()), index=0)

if "urls_splitted" not in st.session_state:
    st.session_state["urls_splitted"] = []

st.sidebar.write("## Add URLs")
with st.sidebar.container():
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if "text_temp" not in st.session_state:
            st.session_state["text_temp"] = ""
        url_text = st.text_area("Enter one or more URLs:", st.session_state["text_temp"], key="url_text_input", height=68)
        enable_pagination = st.checkbox("Auto-follow pagination", value=True)
        num_pages = st.number_input("Pages to crawl", min_value=1, max_value=20, value=3)

    with col2:
        if st.button("Add URLs"):
            if url_text.strip():
                new_urls = []
                input_urls = re.split(r"\s+", url_text.strip())
                for url in input_urls:
                    if enable_pagination:
                        new_urls += get_paginated_urls(url, int(num_pages))
                    else:
                        new_urls.append(url)

                if "urls_splitted" not in st.session_state:
                    st.session_state["urls_splitted"] = []
                st.session_state["urls_splitted"].extend(new_urls)

                # Debug print
                print("[DEBUG] Final URLs to scrape:", st.session_state["urls_splitted"])

                st.session_state["text_temp"] = ""
                st.rerun()

        if st.button("Clear URLs"):
            st.session_state["urls_splitted"] = []
            st.rerun()

    with st.expander("Added URLs", expanded=True):
        if st.session_state["urls_splitted"]:
            st.markdown("\n".join([f"- {url}" for url in st.session_state["urls_splitted"]]))
        else:
            st.write("No URLs added yet.")

st.sidebar.markdown("---")


if st.sidebar.button("START SCRAPING", type="primary"):
    if not st.session_state["urls_splitted"]:
        st.error("Please enter at least one URL.")
    elif show_tags and len(fields) == 0:
        st.error("Please enter at least one field to extract.")
    else:
        all_urls = st.session_state["urls_splitted"]
        unique_names = fetch_and_store_markdowns(all_urls)
        st.session_state.update({
            'urls': all_urls,
            'fields': fields,
            'model_selection': model_selection,
            'unique_names': unique_names,
            'scraping_state': 'scraping'
        })

if st.session_state['scraping_state'] == 'scraping':
    try:
        with st.spinner("Processing..."):
            unique_names = st.session_state["unique_names"]
            total_input_tokens = 0
            total_output_tokens = 0
            total_cost = 0
            all_data = []

            in_tokens_s, out_tokens_s, cost_s, parsed_data = scrape_urls(
                unique_names, st.session_state['fields'], st.session_state['model_selection'], abm_context)
            total_input_tokens += in_tokens_s
            total_output_tokens += out_tokens_s
            total_cost += cost_s
            all_data = parsed_data

            st.session_state.update({
                'in_tokens_s': in_tokens_s,
                'out_tokens_s': out_tokens_s,
                'cost_s': cost_s
            })

            st.session_state['results'] = {
                'data': all_data,
                'input_tokens': total_input_tokens,
                'output_tokens': total_output_tokens,
                'total_cost': total_cost,
                'abm_summary': abm_summary
            }
            st.session_state['scraping_state'] = 'completed'

    except Exception as e:
        st.error(f"An error occurred during scraping: {e}")
        st.session_state['scraping_state'] = 'idle'

if st.session_state['scraping_state'] == 'completed' and st.session_state['results']:
    results = st.session_state['results']
    all_data = results['data']
    abm_summary = results.get('abm_summary', '')

    st.subheader("Scraping Results")
    if abm_summary:
        st.markdown("### ABM PDF Summary")
        st.text(abm_summary)

    all_rows = []
    for i, data_item in enumerate(all_data, start=1):
        if not isinstance(data_item, dict):
            continue

        parsed_obj = data_item.get("parsed_data", {})
        if hasattr(parsed_obj, "model_dump"):
            parsed_obj = parsed_obj.model_dump()
        elif isinstance(parsed_obj, str):
            try:
                parsed_obj = json.loads(parsed_obj)
            except json.JSONDecodeError:
                parsed_obj = {}

        if isinstance(parsed_obj, dict) and "listings" in parsed_obj and isinstance(parsed_obj["listings"], list):
            article_summary = parsed_obj.get("article_summary", "")
            for listing in parsed_obj["listings"]:
                listing["article_summary"] = article_summary
                all_rows.append(listing)
        else:
            all_rows.append(parsed_obj)

    if not all_rows:
        st.warning("No data rows to display.")
    else:
        # Create DataFrame from parsed listings
        df = pd.DataFrame(all_rows)

        # Standardize column names
        df.columns = [str(col).strip().replace("_", " ").title() for col in df.columns]

        # Remove empty strings and duplicates
        df.replace("", np.nan, inplace=True)
        df = df.loc[:, ~df.columns.duplicated()]  # Fix: drop duplicate columns
        
        if "Relevancy Score" in df.columns:
            try:
                df["Relevancy Score"] = pd.to_numeric(df["Relevancy Score"], errors="coerce")
                min_score = st.slider("🎯 Filter by minimum Relevancy Score", min_value=1, max_value=5, value=3)
                df = df[df["Relevancy Score"] >= min_score]
            except Exception:
                st.warning("⚠️ Could not convert Relevancy Score to a numeric format.")

    # Display priority columns first
        priority_cols = [
            "Article Name", "Article Summary", "Article Date", "Article URL",
            "Company", "Company Info", "Focus", "Region",
            "Humanoid Robotics Use Case", "Single Use Cases", "Task Streamlining",
            "Raised Funding", "Recent Developments", "Partnerships",
            "Relevancy Score", "Correlation Reason"
        ]
        display_cols = [col for col in priority_cols if col in df.columns]
        other_cols = [col for col in df.columns if col not in display_cols]
        display_df = df[display_cols + other_cols]

       

        st.subheader("📊 Extracted Company Insights")
        st.dataframe(display_df, use_container_width=True)

    st.subheader("Download Extracted Data")

    col1, col2 = st.columns(2)
    with col1:
        json_data = json.dumps(
            all_data,
            default=lambda o: o.dict() if hasattr(o, 'dict') else str(o),
            indent=4
        )
        st.download_button("Download JSON", data=json_data, file_name="scraped_data.json")

    with col2:  # ✅ moved out from under col1
        if not display_df.empty:
            csv_data = display_df.to_csv(index=False)
            st.download_button("Download CSV", data=csv_data, file_name="scraped_data.csv")
        else:
            st.warning("No structured data available to download as CSV.")


   
    


    # Clear results
    if st.sidebar.button("Clear Results"):
        st.session_state['scraping_state'] = 'idle'
        st.session_state['results'] = None

