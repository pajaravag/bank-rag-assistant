"""LLM provider interface. Concrete providers live beside it and are
instantiated exclusively through `LLMProviderFactory`."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class LLMError(Exception):
    """Raised when the provider fails after retries; carries a user-safe message."""


@dataclass
class LLMResult:
    """Reply text plus the usage metadata analytics needs."""

    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list[dict]) -> LLMResult:
        """Sends OpenAI-style messages [{role, content}, ...] and returns the reply."""
