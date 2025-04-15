from typing import List
from api_management import get_supabase_client
supabase = get_supabase_client()

def read_raw_data(unique_name: str) -> str:
    response = supabase.table("scraped_data").select("raw_data").eq("unique_name", unique_name).execute()
    data = response.data
    return data[0]["raw_data"] if data and len(data) > 0 else ""

def save_raw_data(unique_name: str, url: str, raw_data: str):
    supabase.table("scraped_data").upsert({
        "unique_name": unique_name,
        "url": url,
        "raw_data": raw_data,
    }).execute()

import requests
from bs4 import BeautifulSoup

def get_paginated_urls(base_url: str, max_pages: int = 5) -> List[str]:
    urls = []
    for page in range(1, max_pages + 1):
        page_url = f"{base_url.rstrip('/')}/page/{page}/"
        try:
            response = requests.get(page_url, timeout=10)
            if response.status_code != 200:
                break
            soup = BeautifulSoup(response.text, "html.parser")
            article_links = [
                a['href'] for a in soup.find_all("a", href=True)
                if '/20' in a['href'] and 'page' not in a['href']  # crude filter for article URLs
            ]
            urls.extend(article_links)
        except Exception as e:
            print(f"[WARN] Failed to fetch {page_url}: {e}")
    return list(set(urls))  # remove dupes
