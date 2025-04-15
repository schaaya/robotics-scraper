import json
from litellm import completion
from assets import MODELS_USED
from api_management import get_api_key
import os

# Utility to normalize keys to lowercase with underscores
def normalize_keys(obj):
    if isinstance(obj, dict):
        return {
            k.lower().replace(" ", "_"): normalize_keys(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [normalize_keys(i) for i in obj]
    return obj

# The master function
def call_llm_model(data, model, system_message, response_format=None, abm_context=""):
    """
    Calls the LLM with provided content and parses the structured output.
    Ensures JSON is normalized and fields are padded to match schema.

    Returns:
        (parsed_data, token_info, cost)
    """

    # Set API key from MODELS_USED
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    # Build chat prompt
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": data}
    ]
    if abm_context:
        messages.insert(1, {
            "role": "system",
            "content": f"ABM Context:\n{abm_context[:4000]}"
        })

    try:
        # Call the model
        response = completion(model=model, messages=messages)
        raw_content = response.choices[0].message.content.strip("` \n")

        # Strip leading ```json if present
        if raw_content.lower().startswith("json"):
            raw_content = raw_content[4:].strip()

        parsed_json = json.loads(raw_content)
        normalized = normalize_keys(parsed_json)

        # Enforce required listing keys
        required_listing_keys = [
            "company", "company_info", "focus", "region", "company_size",
            "raised_funding", "recent_developments", "partnerships", "media_mentions",
            "humanoid_robotics_use_case", "single_use_cases", "task_streamlining",
            "project_launch_date", "relevancy_score", "correlation_reason",
            "article_name", "article_summary","article_date", "article_url"
        ]

        if "listings" in normalized:
            for listing in normalized["listings"]:
                for key in required_listing_keys:
                    listing.setdefault(key, "")
                # Inherit article_summary if missing in listing
                if "article_summary" not in listing or not listing["article_summary"]:
                    listing["article_summary"] = normalized.get("article_summary", "")

        # Validate with Pydantic if provided
        parsed_response = (
            response_format.model_validate(normalized)
            if response_format else normalized
        )

        usage = response.usage
        token_counts = {
            "input_tokens": usage.prompt_tokens if usage else 0,
            "output_tokens": usage.completion_tokens if usage else 0
        }

        return parsed_response, token_counts, 0  # Customize cost if needed

    except Exception as e:
        print(f" JSON parsing failed: {e}")
        print("🛠️ Raw model output:\n", response.choices[0].message.content)
        return {"raw_text": response.choices[0].message.content}, {"input_tokens": 0, "output_tokens": 0}, 0
