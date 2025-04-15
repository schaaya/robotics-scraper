import asyncio
import hashlib
from typing import List
from api_management import get_supabase_client
from crawl4ai import AsyncWebCrawler
from markdown_io import save_raw_data
from pagination import paginate_urls
from utils import generate_unique_name

supabase = get_supabase_client()

async def get_fit_markdown_async(url: str) -> str:
    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=url)
        return result.markdown if result.success else ""

def fetch_fit_markdown(url: str) -> str:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(get_fit_markdown_async(url))
    finally:
        loop.close()

def deterministic_name(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

def fetch_and_store_markdowns(urls: List[str], selected_model="gpt-4o", abm_context="") -> List[str]:
    unique_names = []
    url_name_map = {}

    def normalize_url(url: str) -> str:
        return url.split("#")[0].rstrip("/")

    for url in urls:
        url = normalize_url(url)  # ✅ Normalize early
        unique_name = generate_unique_name(url)
        unique_names.append(unique_name)
        url_name_map[unique_name] = url

        # Step 1: Fetch raw markdown and save to Supabase BEFORE paginating
        try:
            raw_md = fetch_fit_markdown(url)
            save_raw_data(unique_name, url, raw_md)
            print(f"[DEBUG] Saved raw_data for {url}")
        except Exception as e:
            print(f"[ERROR] Could not fetch raw markdown for {url}: {e}")

    # Step 2: Run pagination on the already saved content
    _, _, _, pagination_results = paginate_urls(
        unique_names=unique_names,
        model=selected_model,
        indication="",
        urls=list(url_name_map.values()),
        abm_context=abm_context
    )

    for result in pagination_results:
        unique_name = result["unique_name"]
        page_urls = getattr(result.pagination_data, "page_urls", []) if hasattr(result, "pagination_data") else []


        combined_markdown = ""
        for page_url in page_urls:
            try:
                md = fetch_fit_markdown(page_url)
                combined_markdown += md + "\n\n"
            except Exception as e:
                print(f"[markdown] Error fetching page {page_url}: {e}")

        save_raw_data(unique_name, url=url_name_map[unique_name], raw_data=combined_markdown)

    return unique_names
