import asyncio
import json
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from backend.config import UPSTAGE_API_KEY, TAVILY_API_KEY, MAX_ROUNDS
from backend.nodes import _derive_thresholds
from backend.file_reader import extract_text, SUPPORTED_EXTENSIONS
from backend.graph import graph
from backend.parser import parse_sections
from backend.rag import build_index, build_persona_index
from backend.schemas import UploadResponse, ChatRequest, ChatEvent


def _check_api_keys() -> list[str]:
    """누락된 필수 API 키 목록 반환."""
    missing = []
    if not UPSTAGE_API_KEY:
        missing.append("UPSTAGE_API_KEY")
    if not TAVILY_API_KEY:
        missing.append("TAVILY_API_KEY")
    return missing


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = _check_api_keys()
    if missing:
        import sys
        keys = ", ".join(missing)
        print(
            f"\n[경고] 필수 API 키가 설정되지 않았습니다: {keys}\n"
            "  → 프로젝트 루트의 .env 파일에 해당 키를 추가하세요.\n"
            "  → 키 없이 실행하면 LLM/임베딩 호출 시 오류가 발생합니다.\n",
            file=sys.stderr,
        )
    await asyncio.to_thread(build_index)
    for persona in ["investor", "cto", "mentor"]:
        await asyncio.to_thread(build_persona_index, persona)
    yield


app = FastAPI(title="기획서 검증 에이전트 API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSONA_NODES = {"investor", "cto", "mentor"}
QUESTION_NODES = {"investor", "cto", "mentor"}

# 업로드된 기획서 섹션을 thread_id 기준으로 서버 메모리에 보관
_sessions: dict[str, dict[str, str]] = {}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    missing = _check_api_keys()
    if missing:
        keys = ", ".join(missing)
        raise HTTPException(
            status_code=503,
            detail=f"필수 API 키가 설정되지 않았습니다: {keys}. 프로젝트 루트의 .env 파일을 확인해주세요.",
        )

    from pathlib import Path
    if Path(file.filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="TXT, MD, PDF, DOCX 파일만 지원합니다.")

    raw = extract_text(await file.read(), file.filename)
    sections = parse_sections(raw)

    if not sections:
        raise HTTPException(status_code=400, detail="기획서 섹션을 파싱할 수 없습니다.")

    thread_id = str(uuid.uuid4())
    _sessions[thread_id] = sections  # 섹션을 서버에 보관, thread_id로 조회
    return UploadResponse(thread_id=thread_id, first_persona="investor")


@app.post("/chat/start")
async def chat_start(req: ChatRequest):
    thread_id = req.thread_id
    sections = _sessions.get(thread_id)
    if not sections:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다. 다시 업로드해주세요.")

    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "sections": sections,
        "messages": [],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
        "orchestrator_plan": [],
        "sections_by_persona": {},
        "persona_findings": [],
        "review_count": 0,
        "orchestrator_request": {},
        "followup_count": 0,
        "current_persona": "",
        "needs_followup": False,
        "debug_log": [],
        "pending_debug": {},
        "verification_results": [],
        "answer_fact_checks": [],
        "max_rounds": req.max_rounds if req.max_rounds is not None else MAX_ROUNDS,
        "followup_thresholds": _derive_thresholds(req.followup_threshold if req.followup_threshold is not None else 30),
    }

    async def event_generator():
        q_done: set[str] = set()
        try:
            async for stream_type, data in graph.astream(
                initial_state, config, stream_mode=["messages", "updates"]
            ):
                if stream_type == "messages":
                    msg, meta = data
                    node = meta.get("langgraph_node", "")
                    if node not in PERSONA_NODES:
                        continue
                    content = getattr(msg, "content", "")
                    if not content:
                        continue
                    if node in QUESTION_NODES:
                        if node in q_done:
                            continue
                        if '?' in content:
                            content = content[:content.find('?') + 1]
                            q_done.add(node)
                    event = ChatEvent(token=content, node=node, done=False)
                    yield f"data: {event.model_dump_json()}\n\n"
                elif stream_type == "updates":
                    for node_output in data.values():
                        if not isinstance(node_output, dict):
                            continue
                        for entry in node_output.get("debug_log", []):
                            debug_event = ChatEvent(token="", node="dev", done=False, debug=entry)
                            yield f"data: {debug_event.model_dump_json()}\n\n"
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            done_event = ChatEvent(token="", node="", done=True, is_final=False)
            yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/chat")
async def chat(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    state_snapshot = graph.get_state(config)

    if not state_snapshot or not state_snapshot.next:
        raise HTTPException(status_code=400, detail="이미 완료된 세션이거나 존재하지 않는 thread_id입니다.")

    async def event_generator():
        is_final = False
        q_done: set[str] = set()
        try:
            async for stream_type, data in graph.astream(
                Command(resume=req.message), config, stream_mode=["messages", "updates"]
            ):
                if stream_type == "messages":
                    msg, meta = data
                    node = meta.get("langgraph_node", "")
                    if node not in PERSONA_NODES:
                        continue
                    content = getattr(msg, "content", "")
                    if not content:
                        continue
                    if node in QUESTION_NODES:
                        if node in q_done:
                            continue
                        if '?' in content:
                            content = content[:content.find('?') + 1]
                            q_done.add(node)
                    event = ChatEvent(token=content, node=node, done=False)
                    yield f"data: {event.model_dump_json()}\n\n"
                elif stream_type == "updates":
                    for node_output in data.values():
                        if not isinstance(node_output, dict):
                            continue
                        for entry in node_output.get("debug_log", []):
                            is_report = entry.get("type") == "report"
                            if is_report:
                                is_final = True
                            debug_event = ChatEvent(token="", node="dev", done=False, debug=entry, is_final=is_report)
                            yield f"data: {debug_event.model_dump_json()}\n\n"
        except Exception:
            import traceback; traceback.print_exc()
        finally:
            done_event = ChatEvent(token="", node="", done=True, is_final=is_final)
            yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
