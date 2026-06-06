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


# ── FlashrankRerank (로컬 Reranker, API 키 불필요) ──────────────────────────
def _flashrank_rerank(docs: list, metas: list, query: str, top_k: int) -> tuple:
    from flashrank import Ranker, RerankRequest
    ranker = Ranker(model_name="ms-marco-MiniLM-L-12-v2", cache_dir="/tmp/flashrank")
    passages = [{"id": i, "text": doc, "meta": meta} for i, (doc, meta) in enumerate(zip(docs, metas))]
    request = RerankRequest(query=query, passages=passages)
    results = ranker.rerank(request)[:top_k]
    reranked_docs  = [r["text"] for r in results]
    reranked_metas = [r["meta"] for r in results]
    return reranked_docs, reranked_metas


# ── [추가] 대안 1: 하이브리드 청킹을 위한 TextSplitter 세팅 ──────────────────────
def _get_text_splitter():
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    # 섹션 내부가 2000자 제한을 넘겨 누락되는 것을 막기 위해 800자 단위로 자르고, 200자 오버랩 설정
    return RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n", "\n", " ", ""]
    )


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

    # [수정] 대안 1 하이브리드 청커 로드
    splitter = _get_text_splitter()
    texts, ids, metadatas = [], [], []
    
    for file in sorted(examples_path.glob("*")):
        if file.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        raw = read_file_text(file)
        sections = parse_sections(raw)
        
        for section_title, section_content in sections.items():
            full_section_text = f"[{section_title}]\n{section_content}"
            
            # [수정] 구조 분할 후 2차적으로 글자 수 기준 슬라이싱 실행
            chunks = splitter.split_text(full_section_text)
            
            for idx, chunk in enumerate(chunks):
                # ID 중복을 막기 위해 chunk index를 접미사로 결합
                doc_id = f"{file.stem}::{section_title}::chunk_{idx}"
                
                if collection.get(ids=[doc_id])["ids"]:
                    continue
                
                texts.append(chunk)
                ids.append(doc_id)
                metadatas.append({
                    "source": file.stem, 
                    "section": section_title,
                    "chunk_index": idx
                })

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

    # 2차 검색 (Reranking): Upstage REST API로 문맥 연관도 재정렬
    try:
        final_docs, final_metas = _flashrank_rerank(docs, metas, query, k)
    except Exception:
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

    # [수정] 대안 1 하이브리드 청커 로드
    splitter = _get_text_splitter()

    for file in sorted(knowledge_path.glob("*.md")):
        raw = file.read_text(encoding="utf-8")
        sections = parse_markdown_sections(raw)

        existing = collection.get(where={"source": file.stem})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])

        texts, ids, metadatas = [], [], []
        for section_title, section_content in sections.items():
            full_section_text = f"[{section_title}]\n{section_content}"
            
            # [수정] 구조 분할 후 2차적으로 글자 수 기준 슬라이싱 실행
            chunks = splitter.split_text(full_section_text)
            
            for idx, chunk in enumerate(chunks):
                doc_id = f"{file.stem}::{section_title}::chunk_{idx}"
                texts.append(chunk)
                ids.append(doc_id)
                metadatas.append({
                    "source": file.stem, 
                    "section": section_title, 
                    "persona": persona,
                    "chunk_index": idx
                })

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

    # 2차 검색 (Reranking): Upstage REST API로 문맥 연관도 재정렬
    try:
        final_docs, final_metas = _flashrank_rerank(docs, metas, query, k)
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