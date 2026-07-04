"""Groq implementation of the LLMProvider interface.

Resilient to free-tier throttling: exponential-backoff retries on rate
limits and connection errors, then automatic fallback to a secondary
model before giving up.
"""

from __future__ import annotations

import logging
import time

from groq import APIError, APIConnectionError, Groq, RateLimitError

from src.llm.base import LLMError, LLMProvider, LLMResult

logger = logging.getLogger(__name__)


class GroqProvider(LLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        temperature: float,
        max_tokens: int,
        fallback_model: str | None = None,
        max_retries: int = 3,
        retry_base_seconds: float = 1.0,
    ) -> None:
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set — add it to your .env file")
        self.client = Groq(api_key=api_key)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.fallback_model = fallback_model
        self.max_retries = max_retries
        self.retry_base_seconds = retry_base_seconds

    def chat(self, messages: list[dict]) -> LLMResult:
        models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            models.append(self.fallback_model)

        last_exc: Exception | None = None
        for model in models:
            for attempt in range(self.max_retries):
                try:
                    return self._call(model, messages)
                except (RateLimitError, APIConnectionError) as exc:
                    last_exc = exc
                    delay = self.retry_base_seconds * (2**attempt)
                    logger.warning(
                        "%s on %s (attempt %d/%d) — retrying in %.1fs",
                        exc.__class__.__name__, model, attempt + 1, self.max_retries, delay,
                    )
                    time.sleep(delay)
                except APIError as exc:
                    # Non-retryable (bad request, auth, ...) — fail fast
                    logger.error("Groq API error on %s: %s", model, exc)
                    raise LLMError(f"LLM provider error: {getattr(exc, 'message', str(exc))}") from exc
            if model != models[-1]:
                logger.warning("Model %s exhausted retries — falling back to %s", model, models[-1])

        raise LLMError(
            "The LLM provider is unavailable (rate limit or network) after retries; try again shortly"
        ) from last_exc

    def _call(self, model: str, messages: list[dict]) -> LLMResult:
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content = response.choices[0].message.content
        if not content:
            raise LLMError("The LLM returned an empty response")
        usage = response.usage
        return LLMResult(
            text=content,
            model=model,
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
        )
