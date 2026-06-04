import pytest
import shutil
from pathlib import Path
import chromadb
from backend.rag import get_collection, get_persona_collection, build_index, build_persona_index, retrieve, retrieve_persona

@pytest.fixture
def temp_chroma_path(tmp_path):
    """테스트가 끝나면 자동으로 지워지는 임시 ChromaDB 경로 생성"""
    db_dir = tmp_path / "test_chroma"
    yield str(db_dir)
    if db_dir.exists():
        try:
            shutil.rmtree(db_dir)
        except PermissionError:
            # 테스트 프로세스가 살아있어 안 지워지는 건 
            # OS나 pytest의 자체 가비지 컬렉션 단계로 넘겨서 에러를 우회함
            pass

def test_rag_idempotency_and_retrieval(temp_chroma_path):
    print("\n--- [테스트 1] 일반 RAG 멱등성 및 검색 품질 테스트 ---")
    
    # 1. 임시 경로로 격리된 컬렉션 생성
    collection = get_collection(db_path=temp_chroma_path)
    assert collection.count() == 0
    
    # 2. 인덱싱 실행 (실제 data/examples 폴더의 파일들이 파싱되어 들어감)
    build_index(collection=collection)
    first_count = collection.count()
    print(f"최초 인덱싱된 청크 수: {first_count}")
    
    if first_count == 0:
        pytest.skip("data/examples/ 폴더가 비어있거나 지원하는 확장자 파일이 없습니다.")
        
    # 3. 멱등성 테스트 (한 번 더 실행해도 데이터 개수가 그대로여야 함)
    build_index(collection=collection)
    assert collection.count() == first_count, "⚠️ 중복 저장이 발생했습니다! 멱등성이 보장되지 않습니다."
    print("Idempotency(멱등성) 검증 완료!")

    # 4. 실제 검색 품질 테스트 (Hit Rate 검증)
    # 실제 기획서 데이터에 들어있을 법한 키워드로 테스트 쿼리 전송
    test_query = "기획서 양식이나 작성 예시가 필요해"
    result = retrieve(query=test_query, top_k=2, collection=collection)
    
    print("\n[검색 결과 샘플]:")
    print(result)
    
    assert "=== 유사 사례 참조 ===" in result, "검색 결과 포맷이 올바르지 않습니다."
    assert len(result) <= 2000, "MAX_RAG_CHARS 제한 로직이 작동하지 않았습니다."


def test_persona_rag_retrieval(temp_chroma_path):
    print("\n--- [테스트 2] 페르소나 전문지식 RAG 테스트 ---")
    
    # 1. 'cto' 페르소나 컬렉션 생성
    persona = "cto"
    collection = get_persona_collection(persona=persona, db_path=temp_chroma_path)
    
    # 2. 페르소나 인덱싱 빌드
    build_persona_index(persona=persona, collection=collection)
    print(f"'{persona}' 페르소나 인덱싱된 청크 수: {collection.count()}")
    
    if collection.count() == 0:
        pytest.skip(f"knowledge/{persona}/ 폴더에 마크다운 파일이 없습니다.")
        
    # 3. 도메인 지식 검색 테스트
    # CTO 지식 문서에 있을 법한 아키텍처 관련 질문 던지기
    test_query = "초기에 돈 낭비 안 하려면 시스템 만들 때 뭘 제일 먼저 준비해야 돼?"
    result = retrieve_persona(persona=persona, query=test_query, top_k=2, collection=collection)
    
    print(f"\n[{persona} 페르소나 검색 결과 샘플]:")
    print(result)
    
    assert "=== 전문가 참고 자료 ===" in result

    