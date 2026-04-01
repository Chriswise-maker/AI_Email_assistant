"""
LLM Providers Module
Defines the abstract base class and concrete implementations for different LLM providers.
"""

from abc import ABC, abstractmethod
import os
import json
from groq import Groq
from openai import OpenAI  # DeepSeek is OpenAI-compatible
import google.generativeai as genai
import anthropic

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

class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, thinking_level: str = "low"):
        genai.configure(api_key=api_key)
        self.thinking_level = thinking_level

    def analyze_email(self, email_content: str, system_prompt: str, model: str) -> dict:
        try:
            # Gemini 3 Pro/Flash specific configuration
            generation_config = {
                "temperature": 0.3,
                "max_output_tokens": 1024,
                "response_mime_type": "application/json",
            }
            
            # Apply thinking_level if supported by the SDK/Model (Conceptual implementation for Gemini 3)
            # Note: As of Feb 2026, check if 'thinking_level' is a direct param or part of a specific config object.
            # We will pass it in generation_config if the SDK supports it broadly, or assuming it's a top-level param.
            # For now, sticking to standard generation_config.
            if self.thinking_level == "high":
                # Hypothetical param based on user Request
                generation_config["thinking_level"] = "high" 

            model_instance = genai.GenerativeModel(
                model,
                generation_config=generation_config,
                system_instruction=system_prompt,
            )

            response = model_instance.generate_content(email_content)
            return json.loads(response.text)
        except Exception as e:
            print(f"Gemini API Error: {e}")
            import traceback
            traceback.print_exc()
            return None

class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, thinking_level: str = "medium"):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.thinking_level = thinking_level

    def analyze_email(self, email_content: str, system_prompt: str, model: str) -> dict:
        try:
            params = {
                "model": model,
                "max_tokens": 1024,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": email_content}
                ],
            }

            # If thinking_level is medium or high, pass thinking params.
            # Let the API reject if the model doesn't support it.
            if self.thinking_level in ("medium", "high"):
                params["thinking"] = {"type": "adaptive"}
                params["effort"] = self.thinking_level

            response = self.client.messages.create(**params)

            # With thinking enabled, find the text block (skip thinking blocks)
            content = None
            for block in response.content:
                if block.type == "text":
                    content = block.text
                    break
            if not content:
                content = response.content[0].text

            # Strip accidental markdown fences before parsing
            stripped = content.strip()
            if stripped.startswith("```"):
                stripped = stripped.split("\n", 1)[-1]  # drop opening fence line
                stripped = stripped.rsplit("```", 1)[0].strip()

            return json.loads(stripped)
        except Exception as e:
            print(f"Claude API Error: {e}")
            return None

def get_provider(provider_name: str, api_key: str, config: dict = None) -> LLMProvider:
    config = config or {}
    
    if provider_name.lower() == "groq":
        return GroqProvider(api_key)
    elif provider_name.lower() == "deepseek":
        return DeepSeekProvider(api_key)
    elif provider_name.lower() == "gemini":
        thinking = config.get("providers", {}).get("gemini", {}).get("thinking_level", "low")
        return GeminiProvider(api_key, thinking_level=thinking)
    elif provider_name.lower() == "claude":
        thinking = config.get("providers", {}).get("claude", {}).get("thinking_level", "medium")
        return ClaudeProvider(api_key, thinking_level=thinking)
    else:
        raise ValueError(f"Unknown provider: {provider_name}")
