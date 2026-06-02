from __future__ import annotations

from pathlib import Path

import chromadb

from backend.config import UPSTAGE_API_KEY, CHROMA_DB_PATH, RAG_TOP_K, EXAMPLES_DIR, PERSONA_KNOWLEDGE_DIR, PERSONA_CHROMA_DB_PATH
from backend.file_reader import read_file_text, SUPPORTED_EXTENSIONS
from backend.parser import parse_sections


def _get_embedder_passage():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-large", api_key=UPSTAGE_API_KEY)


def _get_embedder_query():
    from langchain_upstage import UpstageEmbeddings
    return UpstageEmbeddings(model="solar-embedding-1-large", api_key=UPSTAGE_API_KEY)


_persistent_client: chromadb.PersistentClient | None = None


def get_collection(db_path: str | None = None) -> chromadb.Collection:
    """ChromaDB 컬렉션 반환. db_path 미지정 시 config의 CHROMA_DB_PATH 사용."""
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
    """data/examples/ TXT 파일을 섹션 단위로 청킹해 ChromaDB에 저장. 중복 없이 멱등 실행."""
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
            # 이미 인덱싱된 문서는 건너뜀 (멱등성 보장)
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


def retrieve(
    query: str,
    top_k: int | None = None,
    collection: chromadb.Collection | None = None,
) -> str:
    """쿼리와 유사한 예시 섹션 top_k개를 레이블 포함 문자열로 반환. 컬렉션이 비어 있으면 ''."""
    if collection is None:
        collection = get_collection()
    if collection.count() == 0:
        return ""

    k = top_k if top_k is not None else RAG_TOP_K
    embedder = _get_embedder_query()
    query_vec = embedder.embed_query(query)

    try:
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(k, collection.count()),
        )
    except Exception:
        return ""

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return ""

    MAX_RAG_CHARS = 2000
    lines = ["=== 유사 사례 참조 ==="]
    total = 0
    for doc, meta in zip(docs, metas):
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
    """페르소나별 ChromaDB 컬렉션 반환. 단일 클라이언트로 3개 컬렉션 공유."""
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
    """knowledge/{persona}/ 마크다운 문서를 섹션 단위로 청킹해 ChromaDB에 저장."""
    if collection is None:
        collection = get_persona_collection(persona)

    knowledge_path = Path(PERSONA_KNOWLEDGE_DIR) / persona
    if not knowledge_path.exists():
        return

    texts, ids, metadatas = [], [], []
    for file in sorted(knowledge_path.glob("*.md")):
        raw = file.read_text(encoding="utf-8")
        sections = parse_sections(raw)
        for section_title, section_content in sections.items():
            doc_id = f"{file.stem}::{section_title}"
            if collection.get(ids=[doc_id])["ids"]:
                continue
            chunk = f"[{section_title}]\n{section_content}"
            texts.append(chunk)
            ids.append(doc_id)
            metadatas.append({"source": file.stem, "section": section_title, "persona": persona})

    if not texts:
        return

    embedder = _get_embedder_passage()
    vectors = embedder.embed_documents(texts)
    collection.add(documents=texts, embeddings=vectors, ids=ids, metadatas=metadatas)


def retrieve_persona(
    persona: str,
    query: str,
    top_k: int | None = None,
    collection: chromadb.Collection | None = None,
) -> str:
    """페르소나 전문 문서에서 쿼리와 유사한 섹션 top_k개를 반환. 비어 있으면 ''."""
    if collection is None:
        collection = get_persona_collection(persona)
    if collection.count() == 0:
        return ""

    k = top_k if top_k is not None else RAG_TOP_K
    embedder = _get_embedder_query()
    query_vec = embedder.embed_query(query)

    try:
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(k, collection.count()),
        )
    except Exception:
        return ""

    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    if not docs:
        return ""

    MAX_PERSONA_RAG_CHARS = 2000
    lines = ["=== 전문가 참고 자료 ==="]
    total = 0
    for doc, meta in zip(docs, metas):
        if total + len(doc) > MAX_PERSONA_RAG_CHARS:
            break
        lines.append(f"\n[{meta['source']} — {meta['section']}]")
        lines.append(doc)
        total += len(doc)
    return "\n".join(lines)
