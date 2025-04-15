from ast import parse
import json
from typing import List, Tuple, Union
from pydantic import BaseModel, create_model, Field

from assets import ROBOTICS_SYSTEM_MESSAGE
from llm_calls import call_llm_model
from markdown_io import read_raw_data
from typing import Optional
from pydantic import Field

from api_management import get_supabase_client
from utils import (
    generate_pdf_summary,
    enrich_company_metadata,
    correlate_with_abm,
    extract_launch_date_from_article
)
from abm_docs import get_abm_report_text

# Initialize Supabase client
supabase = get_supabase_client()

# Dynamic listing model with alias support
def create_dynamic_listing_model(field_names: List[str]):
    required_fields = [
        "Company", "Company Info", "Focus", "Region",
        "Humanoid Robotics Use Case", "Single Use Cases", "Task Streamlining",
        "Raised Funding", "Recent Developments", "Partnerships",
        "Relevancy Score", "Correlation Reason",
        "Article Name", "Article Summary", "Article Date", "Article URL"
    ]
    all_fields = list(set(required_fields + field_names))

    field_definitions = {
        # field: (Union[str, int], Field(..., alias=field.lower().replace(" ", "_")))
        field: (Optional[str], Field(default=None, alias=field.lower().replace(" ", "_")))
        for field in all_fields
    }

    class Config:
        populate_by_name = True
        extra = "allow"

    return create_model('DynamicListingModel', __config__=Config, **field_definitions)

# Container model with alias support
def create_listings_container_model(listing_model: BaseModel):
    class Config:
        populate_by_name = True
        extra = "allow"

    model = create_model(
        'DynamicListingsContainer',
        __config__=Config,
        listings=(List[listing_model], Field(..., alias="listings"))
    )
    model.model_config = Config
    return model





def save_formatted_data(unique_name: str, formatted_data):
    if isinstance(formatted_data, str):
        try:
            data_json = json.loads(formatted_data)
        except json.JSONDecodeError:
            data_json = {"raw_text": formatted_data}
    elif hasattr(formatted_data, "dict"):
        data_json = formatted_data.dict()
    else:
        data_json = formatted_data

    supabase.table("scraped_data").update({
        "formatted_data": data_json
    }).eq("unique_name", unique_name).execute()

    print(f"\033[35mINFO: Scraped data saved for {unique_name}\033[0m")
    print(f"[DEBUG] Fields found in parsed data for {unique_name}: {list(data_json.keys())}")

def scrape_urls(unique_names: List[str], fields: List[str], selected_model: str, abm_context: str = ""):
    total_input_tokens = 0
    total_output_tokens = 0
    total_cost = 0
    parsed_results = []

    DynamicListingModel = create_dynamic_listing_model(fields)
    DynamicListingsContainer = create_listings_container_model(DynamicListingModel)
    prompt_to_use = ROBOTICS_SYSTEM_MESSAGE

    if not abm_context:
        abm_context = get_abm_report_text()

    for uniq in unique_names:
        markdown = read_raw_data(uniq)
        if not markdown:
            print(f"\033[34mNo raw_data found for {uniq}, skipping.\033[0m")
            continue

        response_format = DynamicListingsContainer

        parsed, token_counts, cost = call_llm_model(
            data=markdown,
            model=selected_model,
            system_message=prompt_to_use,
            response_format=response_format,
            abm_context=abm_context
        )
        print(f"[DEBUG] Returned top-level fields: {list(parsed.keys()) if isinstance(parsed, dict) else type(parsed)}")
        if isinstance(parsed, dict) and "listings" in parsed:
            for i, listing in enumerate(parsed["listings"]):
                print(f"[DEBUG] Listing {i} fields: {list(listing.keys())}")

        if isinstance(parsed, dict) and "listings" in parsed:
            for listing in parsed["listings"]:
                enrich_company_metadata(listing)
                correlate_with_abm(listing, abm_context)
                if not listing.get("Project launch date") or listing["Project launch date"] == "TBD":
                    result = extract_launch_date_from_article(markdown, selected_model)
                    if (
                        result.get("project_launch_date") != "TBD"
                        and result["project_launch_date"] not in markdown
                    ):
                        result["project_launch_date"] = "TBD"
                    listing.update(result)

        save_formatted_data(uniq, parsed)

        total_input_tokens += token_counts["input_tokens"]
        total_output_tokens += token_counts["output_tokens"]
        total_cost += cost

        parsed_results.append({
            "unique_name": uniq,
            "parsed_data": parsed
        })

    return total_input_tokens, total_output_tokens, total_cost, parsed_results

