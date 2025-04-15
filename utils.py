import os
import json
import uuid
import requests
from datetime import datetime, timedelta
from litellm import completion
from assets import MODELS_USED
from api_management import get_api_key
from news_utils import get_media_mentions  
from api_management import get_api_key

def generate_unique_name(prefix="doc"):
    """
    Generate a unique name for the document using a prefix and a UUID.
    """
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def generate_pdf_summary(pdf_text: str, model: str):
    """
    Generate a detailed summary of the ABM PDF content.
    The summary should include key points, highlights, and any significant sections in the document.
    """
    # Retrieve the appropriate environment variable for API access
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    # Detailed prompt for generating a detailed summary from the PDF content
    prompt = f"""
    You are an assistant that generates detailed summaries of stakeholder documents. Please read the following ABM PDF content and provide a detailed summary.

    The summary should include:
    - Key highlights
    - Important sections such as strategic updates, financial performance, or innovation updates
    - Relevant actions or strategic plans
    - Any mentions of future directions, key business priorities, or goals
    - If there are tables, charts, or other data-heavy sections, summarize their key points

    Your summary should cover the following aspects:
    - Financial performance and key metrics
    - Innovation updates or strategic goals
    - Any changes or developments in ABM's business areas (maintenance, sustainability, facility management, etc.)
    - Key partnerships or business collaborations mentioned
    - Any other significant details that ABM stakeholders would need to focus on

    --- 
    {pdf_text}

    Only return a clear and concise summary, without additional commentary, formatting, or unnecessary details. Focus on delivering a comprehensive overview that captures all relevant information.
    """

    # Call to the language model to generate the summary
    response = completion(
        model=model,
        messages=[
            {"role": "system", "content": "You summarize stakeholder PDFs in detail, including financial performance, strategic goals, and other significant details."},
            {"role": "user", "content": prompt}
        ]
    )

    try:
        # Extract and return the summary from the model's response
        return response.choices[0].message.content.strip()
    except Exception as e:
        print("[generate_pdf_summary] Error:", e)
        return "Summary unavailable."


def enrich_company_metadata(listing, model: str):
    # Normalize enriched keys to expected format (e.g., "Capital Raised" instead of "capital_raised")
   
    """
    Extract and enrich company metadata using the company's own sources (website + article).
    This version includes detailed prompts and logic for high-precision field extraction.
    """
    website_text = listing.get("company_website_content", "")
    article_text = listing.get("article_text", "")
    listing.setdefault("article_summary", listing.get("Article Summary", "N/A"))
# Normalize keys to match Pydantic aliases if needed
    if "capital_raised" in listing and "Capital Raised" not in listing:
        listing["Capital Raised"] = listing["capital_raised"]


    if not website_text and not article_text:
        print("[enrich_company_metadata] No website or article content available.")
        return

    combined_source = f"WEBSITE:\n{website_text}\n\nARTICLE:\n{article_text}"

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
You are a Robotics Company Profiling AI. Your task is to extract structured metadata from the following company sources:

- WEBSITE content (for mission, use case, product details)
- ARTICLE content (for external context like product launch, funding, and industry news)

Your job is to combine these two sources into one detailed company profile in JSON format.

--- COMPANY SOURCE CONTENT START ---
{combined_source}
--- COMPANY SOURCE CONTENT END ---

Use the structure below and fill in each field with detailed, informative responses. Be concise but insightful.

{{
  "company_info": "Summarize what the company builds with clear mention of its robotics applications, the environments it serves (e.g., warehouse, hospital), and target users (e.g., logistics, facility managers). Avoid generic tech language.",
  

  "region": "Country or region where the company is based. Example: 'US', 'Europe', 'Japan', 'India'.",

  "focus": "Summarize the company’s robotics focus in 2–5 words. Be specific. Example: 'warehouse automation', 'hospital disinfection robots'.",

  "company_size": "Small / Medium / Large — infer from employee size, global reach, or client base.",

  "capital_raised": "Mention total capital raised (e.g., '$43M Series A', 'Total $120M funding'). If not found, infer status (e.g., 'Likely Seed Stage', 'Undisclosed but growth-stage'). Return 'Not Disclosed' only if no clues exist.",

  "funding_stage_inferred": "Try to infer: Seed / Series A / Series B / Series C / Public / Unknown — based on article tone, company size, and recent funding clues.",

  "recent_developments": "List 2–3 key updates from the past 6–12 months. These could include product launches, pilots, new features, expansions, or funding events.",

  "partnerships": "Mention any significant partnerships (business, research, tech etc.). Return 'None' if no evidence found.",


  "humanoids_focus": "Yes/No — plus a 3–4 line explanation of whether and how the company builds humanoid robots and use case.",

  "single_use_case_type": "Yes/No — plus a 3–4 line rationale about their focus on one type of robot vs multipurpose.",

  "streamlined_tasks": "3–4 lines listing and describing specific tasks this company’s robotics solutions are designed to optimize.",

  "project_launch_date": "Extract this ONLY from article content. Format: 'Month Year'. Return 'TBD' if not found."
}}

 Output only a valid JSON object. No explanations, markdown, or extra formatting.
"""

    try:
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You extract company profile insights from website and article text."},
                {"role": "user", "content": prompt}
            ]
        )

        enriched = json.loads(response.choices[0].message.content)

        # Fallbacks
        enriched.setdefault("region", "Unknown")
        enriched.setdefault("focus", "Not Available")
        enriched.setdefault("company_size", "Unknown")
        enriched.setdefault("capital_raised", "Not Disclosed")
        enriched.setdefault("recent_developments", "No updates available")
        enriched.setdefault("partnerships", "None")
        enriched.setdefault("media_mentions", 0)
        enriched.setdefault("humanoids_focus", "No")
        enriched.setdefault("single_use_case_type", "No")
        enriched.setdefault("streamlined_tasks", "")
        enriched.setdefault("project_launch_date", "TBD")
        enriched.setdefault("company_info", "Not provided")

        #  Normalize to Pydantic alias field names
        mapping = {
            "company_info": "Company Info",
            "focus": "Focus",
            "region": "Region",
            "company_size": "Company Size",
            "capital_raised": "Capital Raised",
            "recent_developments": "Recent Developments",
            "partnerships": "Partnerships",
            "media_mentions": "Media Mentions",
            "humanoids_focus": "Humanoid Robotics Use Case",
            "single_use_case_type": "Single Use Cases",
            "streamlined_tasks": "Task Streamlining",
            "project_launch_date": "Project Launch Date"
        }
        for k, v in mapping.items():
            if k in enriched:
                listing[v] = enriched[k]

        listing["description"] = enriched.get("company_info", "Not provided")
        listing.update(enriched)

        gnews_api_key = get_api_key("GNEWS")
        if gnews_api_key:
            company_name = listing.get("Company") or listing.get("company") or enriched.get("company_info", "")
            mentions_count = get_media_mentions(company_name, gnews_api_key)
            listing["media_mentions"] = mentions_count

    except Exception as e:
        print("[enrich_company_metadata] JSON parse error:", e)
   

# utils.py

def build_prompt(fields, content):
    return (
        "You are an information extraction assistant.\n"
        "From the following content, extract the fields listed below.\n\n"
        f"Fields to extract: {', '.join(fields)}\n\n"
        "Please return the result as a **valid JSON array of objects**, "
        "where each object corresponds to a single extracted entity.\n\n"
        "Example:\n"
        "[\n"
        "  {\n"
        + "".join([f'    "{field}": "..."' + (",\n" if i < len(fields) - 1 else "\n") for i, field in enumerate(fields)])
        + "  }\n"
        "]\n\n"
        f"Content:\n{content}"
    )

def correlate_with_abm(listing, abm_summary: str, model: str):
    """
    Evaluate how well a company aligns with ABM Industries’ goals.

    Updates:
    - listing["Relevancy Score"]: "1–5"
    - listing["Correlation Reason"]: structured A–D reasoning
    """

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    company_data = {
        "description": listing.get("description", ""),
        "focus": listing.get("focus", ""),
        "region": listing.get("region", ""),
        "capital_raised": listing.get("capital_raised", ""),
        "recent_developments": listing.get("recent_developments", ""),
        "partnerships": listing.get("partnerships", ""),
        "streamlined_tasks": listing.get("streamlined_tasks", []),
        "humanoids_focus": listing.get("humanoids_focus", ""),
        "single_use_case_type": listing.get("single_use_case_type", ""),
        "project_launch_date": listing.get("project_launch_date", ""),
        "company_size": listing.get("company_size", "")
    }

    # ✳️ PROMPT: A–D evaluation
    prompt = f"""
You are an expert analyst evaluating how well a robotics company aligns with ABM Industries' strategic goals.

ABM's strategy and services are summarized below:
\"\"\"{abm_summary[:4000]}\"\"\"

ABM Services:
- Building maintenance, HVAC, lighting
- Parking & janitorial
- Landscaping, sustainability & energy
- Smart facilities (data-driven operations)
- Commercial expansion into logistics and warehousing (if mentioned)

Company Details:
{json.dumps(company_data, indent=2)}

TASK:
Evaluate the company’s relevance to ABM across the following four categories and write **1–2 polished sentences** for each. Be specific, reference ABM’s strategy, and make each point meaningful.

A. Overlap with ABM’s core or adjacent services  
B. Fit with ABM’s smart facilities and innovation strategy  
C. Robotics innovation or uniqueness  
D. Stage of technology maturity

Write your final response using this exact format:
A. [your sentence]  
B. [your sentence]  
C. [your sentence]  
D. [your sentence]

Only return this plain-text response. No bullet points, no markdown, no JSON, and no extra commentary.
"""

    try:
        #  Step 1: Generate correlation reasoning
        response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert in business strategy and robotics alignment."},
                {"role": "user", "content": prompt}
            ]
        )

        content = response.choices[0].message.content.strip()
        listing["Correlation Reason"] = content

        #  Step 2: Generate score based on the A–D output
        score_prompt = f"""
Using the following A–D reasoning, assign a Relevancy Score from 1 (no alignment) to 5 (very strong alignment).
Only return the number. Do not explain.

\"\"\"{content}\"\"\"
"""
        score_response = completion(
            model=model,
            messages=[
                {"role": "system", "content": "You are a strategic evaluator assigning fit scores from 1 to 5."},
                {"role": "user", "content": score_prompt}
            ]
        )

        # Extract and sanitize score
        score = score_response.choices[0].message.content.strip()
        listing["Relevancy Score"] = score if score in ["1", "2", "3", "4", "5"] else "1"

    except Exception as e:
        print("[correlate_with_abm] Error:", e)
        listing["Relevancy Score"] = "1"
        listing["Correlation Reason"] = "Could not extract explanation."


def extract_single_use_case(listing, model: str):
    """
    Extracts if the company works on single-use robotics.
    """
    company_website_content = listing.get("company_website_content", "")
    if not company_website_content:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
    You are an AI assistant analyzing robotics news and company information. Identify whether the company is developing robots for specific, single-use cases (e.g., a vacuum cleaner or delivery robot).
    If the company works on a single-use case robot, mention "Yes" and describe the task or function the robot is built for. If the company does not focus on single-use case robots, say "No" and provide a brief reason.

    Return this JSON:
    {{
      "single_use_case_type": "Yes/No",
      "description": "If 'Yes', describe the robot's use case. If 'No', provide a short reason explaining the lack of focus."
    }}
    """
    
    response = completion(
        model=model,
        messages=[{"role": "system", "content": "You extract information on single-use robotics."}, {"role": "user", "content": prompt}]
    )
    try:
        enriched = json.loads(response.choices[0].message.content)
        listing.update(enriched)
    except Exception as e:
        print("[extract_single_use_case] JSON parse error:", e)

def extract_task_streamlining(listing, model: str):
    """
    Identifies the tasks a company is streamlining through robotics.
    """
    company_website_content = listing.get("company_website_content", "")
    if not company_website_content:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
    You are an AI assistant analyzing robotics news and company information. Determine whether the company is using robotics to streamline tasks within industries (e.g., improving efficiency in manufacturing, logistics, etc.).
    If the company works on improving processes or automating tasks across industries (like warehouse automation, cleaning, etc.), mention "Yes" and provide details on which tasks are being streamlined. If the company is not focused on task streamlining, say "No" and explain why.

    Return this JSON:
    {{
      "task_streamlining": "Yes/No",
      "description": "If 'Yes', provide specific tasks or processes that the robots are streamlining. If 'No', provide a short reason why."
    }}
    """
    
    response = completion(
        model=model,
        messages=[{"role": "system", "content": "You extract information on task streamlining."}, {"role": "user", "content": prompt}]
    )
    try:
        enriched = json.loads(response.choices[0].message.content)
        listing.update(enriched)
    except Exception as e:
        print("[extract_task_streamlining] JSON parse error:", e)

def extract_humanoid_use_case(listing, model: str):
    """
    Identifies if the company works on humanoid robotics.
    """
    company_website_content = listing.get("company_website_content", "")
    if not company_website_content:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
    You are an AI assistant analyzing robotics companies. Check if the company develops humanoid robots (robots with human-like features and capabilities).
    If the company is working on humanoid robots, respond with "Yes" and explain briefly what their humanoid robots are used for (e.g., service, healthcare, etc.). If the company does not focus on humanoid robotics, respond with "No" and provide a short explanation.

    Return this JSON:
    {{
      "humanoid_use_case": "Yes/No",
      "description": "If 'Yes', describe the use case. If 'No', provide a brief explanation."
    }}
    """
    
    response = completion(
        model=model,
        messages=[{"role": "system", "content": "You extract humanoid robotics information."}, {"role": "user", "content": prompt}]
    )
    try:
        enriched = json.loads(response.choices[0].message.content)
        listing.update(enriched)
    except Exception as e:
        print("[extract_humanoid_use_case] JSON parse error:", e)

def extract_partnerships(listing, model: str):
    """
    Extracts partnership data for the company.
    """
    company_website_content = listing.get("company_website_content", "")
    if not company_website_content:
        return

    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
    You are an AI assistant. Look at the company's website and articles to extract any recent or strategic partnerships they have established.
    If there are any partnerships or collaborations with other companies, mention them here. If no partnerships are available, say "None" and explain that no partnership data is found.

    Return this JSON:
    {{
      "partnerships": "Company A, Company B, etc., or None",
      "description": "Provide a brief explanation of the partnership, what it aims to achieve, or the areas of collaboration."
    }}
    """
    
    response = completion(
        model=model,
        messages=[{"role": "system", "content": "You extract partnerships from web content."}, {"role": "user", "content": prompt}]
    )
    try:
        enriched = json.loads(response.choices[0].message.content)
        listing.update(enriched)
    except Exception as e:
        print("[extract_partnerships] JSON parse error:", e)

def extract_launch_date_from_article(article_text: str, model: str):
    """
    Extracts the launch date for any upcoming robotics project mentioned in the article.
    """
    env_var = list(MODELS_USED[model])[0]
    api_key = get_api_key(model)
    if api_key:
        os.environ[env_var] = api_key

    prompt = f"""
You are a date extraction assistant. Your job is to find the launch date of any robotics project **only if it is clearly stated** in the article.

Examples of valid statements:
- "The robots will begin deployment in Q2 2025"
- "Shipping starts in July 2024"
- "The company plans to roll out the product in October"

 If there is no such clear and explicit statement, return "TBD".

 Never infer or guess the launch date. Only extract if the article **directly mentions** it.

Article:
\"\"\"{article_text[:4000]}\"\"\"

Return a JSON object:
{{
  "project_launch_date": "Month Year" or "TBD"
}}
"""

    response = completion(
        model=model,
        messages=[{"role": "system", "content": "You extract project launch dates from tech news."}, {"role": "user", "content": prompt}]
    )

    try:
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print("[extract_launch_date_from_article] JSON parse error:", e)
        return {"project_launch_date": "TBD"}

