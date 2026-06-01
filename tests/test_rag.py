import pytest
import chromadb
from pathlib import Path


class _FakeEmbedder:
    """API 호출 없이 테스트용 임의 벡터 반환."""
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(i % 10) / 10] * 8 for i in range(len(texts))]

    def embed_query(self, text: str) -> list[float]:
        return [0.5] * 8


@pytest.fixture
def fake_col():
    """인메모리 ChromaDB 컬렉션 (테스트 격리)."""
    import uuid
    client = chromadb.EphemeralClient()
    return client.create_collection(f"test_planning_examples_{uuid.uuid4().hex}")


def test_example_files_exist():
    examples_dir = Path(__file__).parent.parent / "data" / "examples"
    files = list(examples_dir.glob("*.txt"))
    assert len(files) >= 3


def test_build_index_adds_docs(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    from backend.rag import build_index
    build_index(collection=fake_col)
    assert fake_col.count() > 0


def test_build_index_idempotent(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    from backend.rag import build_index
    build_index(collection=fake_col)
    count1 = fake_col.count()
    build_index(collection=fake_col)
    count2 = fake_col.count()
    assert count1 == count2


def test_retrieve_returns_nonempty_string(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    monkeypatch.setattr("backend.rag._get_embedder_query", lambda: _FakeEmbedder())
    from backend.rag import build_index, retrieve
    build_index(collection=fake_col)
    result = retrieve("시장 분석 차별성", collection=fake_col)
    assert isinstance(result, str)
    assert len(result) > 0


def test_retrieve_empty_collection_returns_empty(fake_col, monkeypatch):
    monkeypatch.setattr("backend.rag._get_embedder_query", lambda: _FakeEmbedder())
    from backend.rag import retrieve
    result = retrieve("시장 분析", collection=fake_col)
    assert result == ""
