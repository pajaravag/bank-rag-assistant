"""Groq implementation of the LLMProvider interface."""

from __future__ import annotations

import logging

from groq import APIError, APIConnectionError, Groq, RateLimitError

from src.llm.base import LLMError, LLMProvider

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    def __init__(self, api_key: str, model: str, temperature: float, max_tokens: int) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set — add it to your .env file")
        self.client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(self, messages: list[dict]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
        except RateLimitError as exc:
            logger.warning("Groq rate limit hit: %s", exc)
            raise LLMError("The LLM provider is rate-limiting requests; try again in a moment") from exc
        except APIConnectionError as exc:
            logger.error("Groq connection error: %s", exc)
            raise LLMError("Could not reach the LLM provider; check your network") from exc
        except APIError as exc:
            logger.error("Groq API error: %s", exc)
            raise LLMError(f"LLM provider error: {getattr(exc, 'message', str(exc))}") from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMError("The LLM returned an empty response")
        return content
