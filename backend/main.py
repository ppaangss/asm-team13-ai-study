import json
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from backend.graph import graph
from backend.parser import parse_sections
from backend.schemas import UploadResponse, ChatRequest, ChatEvent

app = FastAPI(title="기획서 검증 에이전트 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSONA_NODES = {"investor", "cto", "mentor", "reporter"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)):
    if not file.filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="TXT 파일만 지원합니다.")

    raw = (await file.read()).decode("utf-8")
    sections = parse_sections(raw)

    if not sections:
        raise HTTPException(status_code=400, detail="기획서 섹션을 파싱할 수 없습니다.")

    thread_id = str(uuid.uuid4())
    return UploadResponse(
        thread_id=thread_id,
        first_persona="investor",
        sections_json=json.dumps(sections, ensure_ascii=False),
    )


@app.post("/chat/start")
async def chat_start(
    thread_id: str = Query(...),
    sections_json: str = Query(...),
):
    sections = json.loads(sections_json)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "sections": sections,
        "messages": [],
        "round": 0,
        "persona_outputs": [],
        "final_report": "",
    }

    async def event_generator():
        async for chunk in graph.astream(initial_state, config, stream_mode="messages"):
            msg, meta = chunk
            node = meta.get("langgraph_node", "")
            if node in PERSONA_NODES:
                content = getattr(msg, "content", "")
                if content:
                    event = ChatEvent(token=content, node=node, done=False)
                    yield f"data: {event.model_dump_json()}\n\n"
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
        async for chunk in graph.astream(
            Command(resume=req.message), config, stream_mode="messages"
        ):
            msg, meta = chunk
            node = meta.get("langgraph_node", "")
            if node in PERSONA_NODES:
                content = getattr(msg, "content", "")
                if content:
                    is_reporter = node == "reporter"
                    event = ChatEvent(token=content, node=node, done=False, is_final=is_reporter)
                    yield f"data: {event.model_dump_json()}\n\n"
                    if is_reporter:
                        is_final = True
        done_event = ChatEvent(token="", node="", done=True, is_final=is_final)
        yield f"data: {done_event.model_dump_json()}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
