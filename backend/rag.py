from __future__ import annotations

from pathlib import Path

import chromadb

from backend.config import UPSTAGE_API_KEY, CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR, PERSONA_KNOWLEDGE_DIR, PERSONA_CHROMA_DB_PATH
from backend.file_reader import read_file_text, SUPPORTED_EXTENSIONS
from backend.parser import parse_sections, parse_markdown_sections


def _get_embedder_passage():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-large", api_key=UPSTAGE_API_KEY)


def _get_embedder_query():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-large", api_key=UPSTAGE_API_KEY)


# ── [추가] Upstage Reranker 로딩 함수 ──────────────────────────────────────
def _get_reranker():
    from langchain_upstage import UpstageRerank
    return UpstageRerank(model="solar-reranking-1-lite", api_key=UPSTAGE_API_KEY)


_persistent_client: chromadb.PersistentClient | None = None


def get_collection(db_path: str | None = None) -> chromadb.Collection:
    global _persistent_client
    path = db_path or CHROMA_DB_PATH
    if db_path is None:
        if _persistent_client is None:
            _persistent_client = chromadb.PersistentClient(path=path)
        client = _persistent_client
    else:
        client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(
        name="planning_examples",
        metadata={"hnsw:space": "cosine"},
    )


def build_index(collection: chromadb.Collection | None = None) -> None:
    if collection is None:
        collection = get_collection()

    examples_path = Path(EXAMPLES_DIR)
    if not examples_path.exists():
        return

    texts, ids, metadatas = [], [], []
    for file in sorted(examples_path.glob("*")):
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        raw = read_file_text(file)
        sections = parse_sections(raw)
        for section_title, section_content in sections.items():
            doc_id = f"{file.stem}::{section_title}"
            if collection.get(ids=[doc_id])["ids"]:
                continue
            chunk = f"[{section_title}]\n{section_content}"
            texts.append(chunk)
            ids.append(doc_id)
            metadatas.append({"source": file.stem, "section": section_title})

    if not texts:
        return

    embedder = _get_embedder_passage()
    vectors = embedder.embed_documents(texts)
    collection.add(documents=texts, embeddings=vectors, ids=ids, metadatas=metadatas)


# ── [개조] 일반 RAG Retrieve (Reranker 적용) ──────────────────────────────────
def retrieve(
    query: str,
    top_k: int | None = None,
    collection: chromadb.Collection | None = None,
) -> str:
    if collection is None:
        collection = get_collection()
    if collection.count() == 0:
        return ""

    k = top_k if top_k is not None else RAG_TOP_K
    embedder = _get_embedder_query()
    query_vec = embedder.embed_query(query)

    try:
        # 1차 검색: Reranker를 태우기 위해 넉넉하게 10개(혹은 전체 개수만큼) 추출
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(10, collection.count()),
        )
    except Exception:
        return ""

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return ""

    # 2차 검색 (Reranking): Upstage Reranker를 사용하여 쿼리와의 문맥 연관도 재정렬
    try:
        from langchain_core.documents import Document
        reranker = _get_reranker()
        
        # LangChain Reranker 포맷에 맞게 변환
        langchain_docs = [
            Document(page_content=doc, metadata=meta) for doc, meta in zip(docs, metas)
        ]
        # 점수가 높은 순으로 정렬되어 반환됨
        reranked_results = reranker.rerank_documents(langchain_docs, query=query, top_n=k)
        
        final_docs = [r_doc.page_content for r_doc in reranked_results]
        final_metas = [r_doc.metadata for r_doc in reranked_results]
    except Exception:
        # Reranker API 실패 시 기비용 아끼기 위해 1차 검색 결과 백업 사용
        final_docs, final_metas = docs[:k], metas[:k]

    MAX_RAG_CHARS = 2000
    lines = ["=== 유사 사례 참조 ==="]
    total = 0
    for doc, meta in zip(final_docs, final_metas):
        if total + len(doc) > MAX_RAG_CHARS:
            break
        lines.append(f"\n[출처: {meta['source']} — {meta['section']}]")
        lines.append(doc)
        total += len(doc)
    return "\n".join(lines)


# ── 페르소나 전문 지식 RAG ──────────────────────────────────────

_persona_client: chromadb.PersistentClient | None = None


def get_persona_collection(
    persona: str,
    db_path: str | None = None,
) -> chromadb.Collection:
    global _persona_client
    path = db_path or PERSONA_CHROMA_DB_PATH
    if db_path is None:
        if _persona_client is None:
            _persona_client = chromadb.PersistentClient(path=path)
        client = _persona_client
    else:
        client = chromadb.PersistentClient(path=path)
    return client.get_or_create_collection(
        name=f"persona_{persona}",
        metadata={"hnsw:space": "cosine"},
    )


def build_persona_index(
    persona: str,
    collection: chromadb.Collection | None = None,
) -> None:
    if collection is None:
        collection = get_persona_collection(persona)

    knowledge_path = Path(PERSONA_KNOWLEDGE_DIR) / persona
    if not knowledge_path.exists():
        return

    for file in sorted(knowledge_path.glob("*.md")):
        raw = file.read_text(encoding="utf-8")
        sections = parse_markdown_sections(raw)

        existing = collection.get(where={"source": file.stem})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

        texts, ids, metadatas = [], [], []
        for section_title, section_content in sections.items():
            doc_id = f"{file.stem}::{section_title}"
            chunk = f"[{section_title}]\n{section_content}"
            texts.append(chunk)
            ids.append(doc_id)
            metadatas.append({"source": file.stem, "section": section_title, "persona": persona})

        if not texts:
            continue

        embedder = _get_embedder_passage()
        vectors = embedder.embed_documents(texts)
        collection.add(documents=texts, embeddings=vectors, ids=ids, metadatas=metadatas)


# ── [개조] 페르소나 RAG Retrieve (Reranker 적용) ──────────────────────────────
def retrieve_persona(
    persona: str,
    query: str,
    top_k: int | None = None,
    collection: chromadb.Collection | None = None,
) -> str:
    if collection is None:
        collection = get_persona_collection(persona)
    if collection.count() == 0:
        return ""

    k = top_k if top_k is not None else RAG_TOP_K
    embedder = _get_embedder_query()
    query_vec = embedder.embed_query(query)

    try:
        # 1차 검색: 넉넉하게 10개 추출
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(10, collection.count()),
        )
    except Exception:
        return ""

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return ""

    # 2차 검색 (Reranking)
    try:
        from langchain_core.documents import Document
        reranker = _get_reranker()
        
        langchain_docs = [
            Document(page_content=doc, metadata=meta) for doc, meta in zip(docs, metas)
        ]
        reranked_results = reranker.rerank_documents(langchain_docs, query=query, top_n=k)
        
        final_docs = [r_doc.page_content for r_doc in reranked_results]
        final_metas = [r_doc.metadata for r_doc in reranked_results]
    except Exception:
        final_docs, final_metas = docs[:k], metas[:k]

    MAX_PERSONA_RAG_CHARS = 2000
    lines = ["=== 전문가 참고 자료 ==="]
    total = 0
    for doc, meta in zip(final_docs, final_metas):
        if total + len(doc) > MAX_PERSONA_RAG_CHARS:
            break
        lines.append(f"\n[{meta['source']} — {meta['section']}]")
        lines.append(doc)
        total += len(doc)
    return "\n".join(lines)