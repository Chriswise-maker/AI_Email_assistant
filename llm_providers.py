"""
LLM Providers Module
Defines the abstract base class and concrete implementations for different LLM providers.
"""

from abc import ABC, abstractmethod
import os
import json
from groq import Groq
from openai import OpenAI  # DeepSeek is OpenAI-compatible

class LLMProvider(ABC):
    @abstractmethod
    def analyze_email(self, email_content: str, system_prompt: str, model: str) -> dict:
        """
        Send email content to LLM and return structured analysis.
        
        Args:
            email_content: The body of the email to analyze.
            system_prompt: The system prompt guiding the LLM.
            model: The specific model ID to use.
            
        Returns:
            dict: The analysis result (category, priority, summary).
        """
        pass

class GroqProvider(LLMProvider):
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)

    def analyze_email(self, email_content: str, system_prompt: str, model: str) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": email_content}
                ],
                temperature=0.3,
                max_tokens=512,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"Groq API Error: {e}")
            return None

class DeepSeekProvider(LLMProvider):
    def __init__(self, api_key: str):
        # DeepSeek uses the OpenAI SDK with a custom base URL
        self.client = OpenAI(
            api_key=api_key, 
            base_url="https://api.deepseek.com"
        )

    def analyze_email(self, email_content: str, system_prompt: str, model: str) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": email_content}
                ],
                temperature=0.3,
                max_tokens=512,
                # DeepSeek might not support response_format="json_object" strictly, 
                # but it usually follows instructions well. We'll try to parse JSON.
            )
            content = response.choices[0].message.content
            # Clean potential markdown fences (DeepSeek R1 tends to use them)
            if "```json" in content:
                content = content.replace("```json", "").replace("```", "")
            return json.loads(content)
        except Exception as e:
            print(f"DeepSeek API Error: {e}")
            return None

def get_provider(provider_name: str, api_key: str) -> LLMProvider:
    if provider_name.lower() == "groq":
        return GroqProvider(api_key)
    elif provider_name.lower() == "deepseek":
        return DeepSeekProvider(api_key)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
