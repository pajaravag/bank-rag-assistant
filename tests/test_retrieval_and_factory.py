import pytest

from src.config import Settings
from src.llm.base import LLMError, LLMProvider, LLMResult
from src.llm.factory import LLMProviderFactory
from src.models import Chunk, RetrievedChunk
from src.retrieval.strategies import RetrievalStrategy, RerankedSearch, _dedupe


def make_hit(text: str, url: str = "https://x.co", score: float = 0.9) -> RetrievedChunk:
    return RetrievedChunk(chunk=Chunk(url=url, title="T", text=text, chunk_index=0), score=score)


def test_dedupe_removes_whitespace_variants():
    hits = [make_hit("Hola  mundo"), make_hit("hola mundo"), make_hit("otro texto")]
    assert len(_dedupe(hits)) == 2


class FakeStrategy(RetrievalStrategy):
    def retrieve(self, query):
        return [make_hit("candidato uno"), make_hit("candidato uno"), make_hit("candidato dos")]


class FakeReranker:
    def rerank(self, query, candidates):
        return sorted(candidates, key=lambda c: c.chunk.text)  # deterministic order


def test_reranked_search_dedupes_and_truncates():
    strategy = RerankedSearch(FakeStrategy(), FakeReranker(), final_k=1)
    results = strategy.retrieve("q")
    assert len(results) == 1


def test_factory_unknown_provider_raises():
    settings = Settings(llm_provider="does-not-exist", groq_api_key="x")
    with pytest.raises(LLMError, match="Unknown LLM provider"):
        LLMProviderFactory.create(settings)


def test_factory_builds_registered_provider():
    class FakeProvider(LLMProvider):
        def chat(self, messages):
            return LLMResult(text="ok", model="fake")

    LLMProviderFactory.register("fake", lambda s: FakeProvider())
    provider = LLMProviderFactory.create(Settings(llm_provider="fake"))
    assert provider.chat([]).text == "ok"


def test_groq_provider_requires_api_key():
    settings = Settings(llm_provider="groq", groq_api_key="")
    with pytest.raises(LLMError, match="GROQ_API_KEY"):
        LLMProviderFactory.create(settings)
