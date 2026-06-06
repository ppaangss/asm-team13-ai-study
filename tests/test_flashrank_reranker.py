"""
_flashrank_rerank() 단위 테스트
RED → GREEN → REFACTOR 사이클로 작성됨
"""
import pytest
from unittest.mock import patch, MagicMock


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

SAMPLE_DOCS = [
    "투자자는 수익 모델과 시장성을 중심으로 평가한다",
    "CTO는 기술 실현 가능성과 아키텍처를 검토한다",
    "멘토는 문제 정의와 팀 구성의 논리적 일관성을 본다",
    "MVP 범위를 좁히면 빠른 검증이 가능하다",
    "시장 규모 데이터 없이는 투자 설득이 어렵다",
]

SAMPLE_METAS = [
    {"source": "investor_guide", "section": "수익"},
    {"source": "cto_guide",      "section": "기술"},
    {"source": "mentor_guide",   "section": "팀"},
    {"source": "mvp_guide",      "section": "범위"},
    {"source": "market_guide",   "section": "시장"},
]


# ── 테스트: 반환 개수 ─────────────────────────────────────────────────────────

def test_flashrank_rerank_returns_exactly_top_k_docs():
    """top_k=3이면 정확히 3개의 문서와 메타를 반환한다."""
    from backend.rag import _flashrank_rerank
    docs, metas = _flashrank_rerank(SAMPLE_DOCS, SAMPLE_METAS, query="수익 모델", top_k=3)
    assert len(docs) == 3
    assert len(metas) == 3


def test_flashrank_rerank_returns_top_1_when_top_k_is_1():
    """top_k=1이면 가장 관련성 높은 문서 1개만 반환한다."""
    from backend.rag import _flashrank_rerank
    docs, metas = _flashrank_rerank(SAMPLE_DOCS, SAMPLE_METAS, query="수익 모델 검증", top_k=1)
    assert len(docs) == 1
    assert len(metas) == 1


# ── 테스트: 재정렬 효과 ───────────────────────────────────────────────────────

def test_flashrank_rerank_puts_relevant_doc_at_top():
    """투자자 수익 쿼리에 대해 investor_guide 문서가 상위에 온다."""
    from backend.rag import _flashrank_rerank
    docs, metas = _flashrank_rerank(SAMPLE_DOCS, SAMPLE_METAS, query="투자자 수익 모델 시장성", top_k=3)
    top_source = metas[0]["source"]
    assert top_source in ("investor_guide", "market_guide"), (
        f"수익/시장 관련 쿼리에서 '{top_source}'가 1위로 예상치 않은 결과"
    )


def test_flashrank_rerank_docs_and_metas_stay_aligned():
    """반환된 docs[i]와 metas[i]는 같은 원본 문서를 가리켜야 한다."""
    from backend.rag import _flashrank_rerank
    docs, metas = _flashrank_rerank(SAMPLE_DOCS, SAMPLE_METAS, query="기술 스택 아키텍처", top_k=3)
    for doc, meta in zip(docs, metas):
        original_idx = SAMPLE_DOCS.index(doc)
        assert SAMPLE_METAS[original_idx] == meta, (
            f"docs와 metas 정렬 불일치: doc='{doc[:20]}...', meta={meta}"
        )


# ── 테스트: 엣지 케이스 ───────────────────────────────────────────────────────

def test_flashrank_rerank_when_docs_fewer_than_top_k():
    """문서 수가 top_k보다 적으면 가진 문서 전부를 반환한다."""
    from backend.rag import _flashrank_rerank
    small_docs  = SAMPLE_DOCS[:2]
    small_metas = SAMPLE_METAS[:2]
    docs, metas = _flashrank_rerank(small_docs, small_metas, query="수익", top_k=5)
    assert len(docs) == 2
    assert len(metas) == 2


# ── 테스트: retrieve() fallback 연동 ─────────────────────────────────────────

def test_retrieve_uses_flashrank_reranker(monkeypatch):
    """retrieve()가 _flashrank_rerank를 호출하고 그 결과를 사용한다."""
    import chromadb
    from backend.rag import build_index, retrieve

    class _FakeEmbedder:
        def embed_documents(self, texts):
            return [[0.1] * 8 for _ in texts]
        def embed_query(self, text):
            return [0.1] * 8

    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    monkeypatch.setattr("backend.rag._get_embedder_query",   lambda: _FakeEmbedder())

    client = chromadb.EphemeralClient()
    import uuid
    col = client.create_collection(f"test_{uuid.uuid4().hex}")
    build_index(collection=col)

    reranker_called = []

    def fake_rerank(docs, metas, query, top_k):
        reranker_called.append(True)
        return docs[:top_k], metas[:top_k]

    monkeypatch.setattr("backend.rag._flashrank_rerank", fake_rerank)
    retrieve("수익 모델", collection=col)

    assert reranker_called, "retrieve()가 _flashrank_rerank를 호출하지 않았다"


def test_retrieve_falls_back_when_flashrank_raises(monkeypatch):
    """_flashrank_rerank가 예외를 던지면 1차 검색 결과를 그대로 사용한다."""
    import chromadb
    from backend.rag import build_index, retrieve

    class _FakeEmbedder:
        def embed_documents(self, texts):
            return [[0.1] * 8 for _ in texts]
        def embed_query(self, text):
            return [0.1] * 8

    monkeypatch.setattr("backend.rag._get_embedder_passage", lambda: _FakeEmbedder())
    monkeypatch.setattr("backend.rag._get_embedder_query",   lambda: _FakeEmbedder())

    client = chromadb.EphemeralClient()
    import uuid
    col = client.create_collection(f"test_{uuid.uuid4().hex}")
    build_index(collection=col)

    def broken_rerank(docs, metas, query, top_k):
        raise RuntimeError("Flashrank 강제 실패")

    monkeypatch.setattr("backend.rag._flashrank_rerank", broken_rerank)

    result = retrieve("수익 모델", collection=col)
    assert isinstance(result, str), "fallback이어도 문자열을 반환해야 한다"
