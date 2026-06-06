"""
data_verification_node 단위 테스트
3단계 파이프라인: 주장 추출 → 병렬 웹 검색 → LLM 검증
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.test_nodes_react import SAMPLE_STATE


# ── 공통 픽스처 ──────────────────────────────────────────────────────────────

def _make_claim_result(claims: list[str]):
    m = MagicMock()
    m.claims = claims
    return m


def _make_verify_result(items: list[dict]):
    result = MagicMock()
    result.items = [MagicMock(**{"model_dump.return_value": item}) for item in items]
    return result


SAMPLE_ITEMS = [
    {"claim": "국내 SaaS 시장 2조원", "status": "confirmed",
     "reason": "검색 결과와 일치", "source": "https://example.com"},
]


# ── 테스트: 수치 주장이 있을 때 정상 처리 ─────────────────────────────────────

@pytest.mark.asyncio
async def test_data_verification_returns_debug_log_with_type():
    """정상 실행 시 type이 'data_verification'인 debug_log를 반환한다."""
    from backend.nodes import data_verification_node

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:

        mock_extractor.ainvoke = AsyncMock(return_value=_make_claim_result(["국내 SaaS 시장 2조원"]))
        mock_search.invoke = MagicMock(return_value="SaaS 시장 1.8조원 규모")
        mock_verifier.ainvoke = AsyncMock(return_value=_make_verify_result(SAMPLE_ITEMS))

        result = await data_verification_node(SAMPLE_STATE)

    log = result["debug_log"]
    assert len(log) == 1
    assert log[0]["type"] == "data_verification"


@pytest.mark.asyncio
async def test_data_verification_items_contain_required_fields():
    """검증 결과 각 항목은 claim, status, reason, source 필드를 포함한다."""
    from backend.nodes import data_verification_node

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:

        mock_extractor.ainvoke = AsyncMock(return_value=_make_claim_result(["국내 SaaS 시장 2조원"]))
        mock_search.invoke = MagicMock(return_value="SaaS 시장 1.8조원 규모")
        mock_verifier.ainvoke = AsyncMock(return_value=_make_verify_result(SAMPLE_ITEMS))

        result = await data_verification_node(SAMPLE_STATE)

    items = result["debug_log"][0]["items"]
    assert len(items) == 1
    item = items[0]
    for field in ("claim", "status", "reason", "source"):
        assert field in item, f"'{field}' 필드 누락"


# ── 테스트: 수치 주장이 없을 때 ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_verification_returns_empty_items_when_no_claims():
    """기획서에 수치 주장이 없으면 items가 빈 리스트인 debug_log를 반환한다."""
    from backend.nodes import data_verification_node

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor:
        mock_extractor.ainvoke = AsyncMock(return_value=_make_claim_result([]))

        result = await data_verification_node(SAMPLE_STATE)

    log = result["debug_log"]
    assert log[0]["type"] == "data_verification"
    assert log[0]["items"] == []


# ── 테스트: 최대 4개 제한 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_verification_limits_claims_to_4():
    """5개 이상 주장이 추출되어도 웹 검색은 최대 4개까지만 실행한다."""
    from backend.nodes import data_verification_node

    five_claims = [f"주장 {i}" for i in range(5)]
    search_call_count = []

    def counting_search(claim):
        search_call_count.append(claim)
        return "검색 결과"

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:

        mock_extractor.ainvoke = AsyncMock(return_value=_make_claim_result(five_claims))
        mock_search.invoke = MagicMock(side_effect=counting_search)
        mock_verifier.ainvoke = AsyncMock(return_value=_make_verify_result([]))

        await data_verification_node(SAMPLE_STATE)

    assert len(search_call_count) == 4, (
        f"웹 검색이 {len(search_call_count)}회 호출됨 (최대 4회여야 함)"
    )


# ── 테스트: 주장 추출 LLM 실패 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_verification_returns_empty_when_extractor_fails():
    """주장 추출 LLM이 실패하면 items가 빈 리스트인 debug_log를 반환한다."""
    from backend.nodes import data_verification_node

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor:
        mock_extractor.ainvoke = AsyncMock(side_effect=RuntimeError("LLM 오류"))

        result = await data_verification_node(SAMPLE_STATE)

    log = result["debug_log"]
    assert log[0]["type"] == "data_verification"
    assert log[0]["items"] == []


# ── 테스트: 검증 LLM 실패 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_data_verification_returns_empty_items_when_verifier_fails():
    """검증 LLM이 실패해도 debug_log 구조는 유지되고 items는 빈 리스트다."""
    from backend.nodes import data_verification_node

    with patch("backend.nodes._bound_claim_extractor") as mock_extractor, \
         patch("backend.nodes.web_search") as mock_search, \
         patch("backend.nodes._bound_claim_verifier") as mock_verifier:

        mock_extractor.ainvoke = AsyncMock(return_value=_make_claim_result(["국내 SaaS 시장 2조원"]))
        mock_search.invoke = MagicMock(return_value="검색 결과")
        mock_verifier.ainvoke = AsyncMock(side_effect=RuntimeError("LLM 오류"))

        result = await data_verification_node(SAMPLE_STATE)

    log = result["debug_log"]
    assert log[0]["type"] == "data_verification"
    assert log[0]["items"] == []
