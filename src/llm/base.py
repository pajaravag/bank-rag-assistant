"""LLM provider interface. Concrete providers live beside it and are
instantiated exclusively through `LLMProviderFactory`."""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMError(Exception):
    """Raised when the provider fails after retries; carries a user-safe message."""


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> str:
        """Sends OpenAI-style messages [{role, content}, ...] and returns the reply text."""
