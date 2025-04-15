import os
from openai import OpenAI
from assets import get_api_key
from litellm import completion
from litellm.exceptions import RateLimitError

class MyLLMClient:
    def __init__(self):
        self.primary_model = "gpt-4o"
        self.fallback_model = "gpt-4o-mini"
        
        self.api_key = get_api_key(self.primary_model)
        os.environ["OPENAI_API_KEY"] = self.api_key  # this sets for primary initially

        # Preload fallback API key too just in case
        os.environ["OPENAI_API_KEY"] = get_api_key(self.fallback_model)

        self.model = self.primary_model

    def send_prompt(self, prompt):
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt}
        ]
        try:
            response = completion(model=self.model, messages=messages)
        except RateLimitError:
            print(f"[⚠️] Rate limit hit for {self.model}, retrying with {self.fallback_model}...")
            self.model = self.fallback_model
            response = completion(model=self.model, messages=messages)
        return response.choices[0].message.content.strip()

