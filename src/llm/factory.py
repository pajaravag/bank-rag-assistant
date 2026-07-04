"""Factory pattern: builds the configured LLM provider from settings.

Registry-based so new providers (Ollama, OpenAI, ...) plug in with a
`register` call and an .env change — no edits to consuming code.
"""

from __future__ import annotations

from typing import Callable

from src.config import Settings
from src.llm.base import LLMError, LLMProvider
from src.llm.groq_provider import GroqProvider

_BuilderFn = Callable[[Settings], LLMProvider]


class LLMProviderFactory:
    _registry: dict[str, _BuilderFn] = {}

    @classmethod
    def register(cls, name: str, builder: _BuilderFn) -> None:
        cls._registry[name.lower()] = builder

    @classmethod
    def create(cls, settings: Settings) -> LLMProvider:
        name = settings.llm_provider.lower()
        builder = cls._registry.get(name)
        if builder is None:
            raise LLMError(
                f"Unknown LLM provider '{name}'. Available: {sorted(cls._registry)}"
            )
        return builder(settings)


LLMProviderFactory.register(
    "groq",
    lambda s: GroqProvider(
        api_key=s.groq_api_key,
        model=s.llm_model,
        temperature=s.llm_temperature,
        max_tokens=s.llm_max_tokens,
    ),
)
