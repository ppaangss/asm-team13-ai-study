import pytest
from unittest.mock import patch, MagicMock


def test_build_persona_index_skips_when_dir_missing(tmp_path):
    """persona_docs 디렉터리가 없으면 조용히 종료."""
    collection = MagicMock()
    collection.count.return_value = 0

    with patch("backend.rag.PERSONA_KNOWLEDGE_DIR", str(tmp_path / "nonexistent")):
        from backend.rag import build_persona_index
        build_persona_index("investor", collection=collection)

    collection.add.assert_not_called()


def test_build_persona_index_indexes_md_files(tmp_path):
    """knowledge/investor/*.md 파일을 ChromaDB에 인덱싱."""
    investor_dir = tmp_path / "investor"
    investor_dir.mkdir()
    (investor_dir / "test_doc.md").write_text(
        "# 테스트\n\n## 섹션1\n내용입니다.", encoding="utf-8"
    )

    collection = MagicMock()
    collection.get.return_value = {"ids": []}
    collection.count.return_value = 0

    mock_embedder = MagicMock()
    mock_embedder.embed_documents.return_value = [[0.1, 0.2, 0.3]]

    with patch("backend.rag.PERSONA_KNOWLEDGE_DIR", str(tmp_path)), \
         patch("backend.rag._get_embedder_passage", return_value=mock_embedder):
        from backend.rag import build_persona_index
        build_persona_index("investor", collection=collection)

    collection.add.assert_called_once()
    args = collection.add.call_args
    assert len(args.kwargs["ids"]) >= 1


def test_retrieve_persona_returns_empty_when_collection_empty():
    """컬렉션이 비어 있으면 빈 문자열 반환."""
    collection = MagicMock()
    collection.count.return_value = 0

    from backend.rag import retrieve_persona
    result = retrieve_persona("investor", "시장 규모 분석", collection=collection)
    assert result == ""


def test_retrieve_persona_returns_formatted_string():
    """컬렉션에 문서가 있으면 포맷된 문자열 반환."""
    collection = MagicMock()
    collection.count.return_value = 2
    collection.query.return_value = {
        "documents": [["# VC 프레임워크\n\n투자자 평가 기준"]],
        "metadatas": [[{"source": "vc_evaluation_framework", "section": "팀"}]],
    }

    mock_embedder = MagicMock()
    mock_embedder.embed_query.return_value = [0.1, 0.2, 0.3]

    with patch("backend.rag._get_embedder_query", return_value=mock_embedder):
        from backend.rag import retrieve_persona
        result = retrieve_persona("investor", "팀 역량", collection=collection)

    assert "VC 프레임워크" in result or "투자자 평가" in result
    assert result != ""


def test_get_persona_collection_returns_named_collection():
    """get_persona_collection이 페르소나별 컬렉션명을 사용하는지 확인."""
    mock_client = MagicMock()
    mock_client.get_or_create_collection.return_value = MagicMock()

    with patch("chromadb.PersistentClient", return_value=mock_client):
        from backend.rag import get_persona_collection
        get_persona_collection("cto", db_path="/tmp/test_db")

    call_kwargs = mock_client.get_or_create_collection.call_args
    assert "persona_cto" in str(call_kwargs)
