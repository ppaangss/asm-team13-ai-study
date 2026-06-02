import uuid
import streamlit as st
from langgraph.types import Command
from app.parser import parse_proposal
from app.graph import build_graph
from app.core import config

st.set_page_config(page_title="기획서 검증 에이전트", layout="wide")
st.title("🧪 기획서 검증 에이전트")
st.caption("투자자·CTO·멘토 페르소나가 발표 전 '가장 아플 질문'을 미리 던집니다.")


@st.cache_resource
def get_graph():
    return build_graph()


def _render_transcript(values: dict):
    for t in values.get("transcript", []):
        if t.get("type") == "answer":
            with st.chat_message("user"):
                st.markdown(t.get("content", ""))
        else:
            with st.chat_message("assistant"):
                label = f"**[{t.get('persona','')}]**"
                if t.get("type") == "feedback":
                    st.markdown(f"{label} _({t.get('assessment','')})_ {t.get('content', '')}")
                else:
                    st.markdown(f"{label} {t.get('content', '')}")


def _current_question(graph, cfg) -> dict | None:
    state = graph.get_state(cfg)
    if state.tasks and state.tasks[0].interrupts:
        return state.tasks[0].interrupts[0].value
    return None


graph = get_graph()

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.started = False
    st.session_state.done = False

cfg = {"configurable": {"thread_id": st.session_state.thread_id}}

if not st.session_state.started:
    uploaded = st.file_uploader("기획서 txt 파일 업로드", type=["txt", "md"])
    max_rounds = st.slider("질문 라운드 수", 3, 9, config.MAX_ROUNDS)
    if uploaded and st.button("모의 심사 시작", type="primary"):
        text = uploaded.read().decode("utf-8", errors="ignore")
        sections = parse_proposal(text)
        if not sections:
            st.error("표준 양식(마크다운 # / ## 헤딩)을 인식하지 못했습니다. templates/기획서_양식.md 를 참고하세요.")
        else:
            with st.spinner("세 페르소나가 기획서를 분석 중입니다..."):
                graph.invoke({
                    "sections": sections, "persona_analyses": [], "weaknesses": [],
                    "question_pool": [], "asked": [], "transcript": [],
                    "current_question": {}, "current_answer": "",
                    "round": 0, "max_rounds": max_rounds, "final_report": {},
                }, cfg)
            st.session_state.started = True
            st.rerun()

else:
    _render_transcript(graph.get_state(cfg).values)

    if not st.session_state.done:
        q = _current_question(graph, cfg)
        if q:
            with st.chat_message("assistant"):
                st.markdown(f"**[{q['persona']}]** {q['question']}")
            if answer := st.chat_input("답변을 입력하세요"):
                graph.invoke(Command(resume=answer), cfg)
                if not _current_question(graph, cfg):
                    st.session_state.done = True
                st.rerun()
        else:
            st.session_state.done = True
            st.rerun()

    if st.session_state.done:
        rpt = graph.get_state(cfg).values.get("final_report", {})
        st.divider()
        st.subheader("📋 종합 리포트")
        st.markdown(rpt.get("summary", ""))
        for w in rpt.get("weaknesses", []):
            with st.expander(f"[{w['severity']}] ({w['section']}) {w['weakness_type']} — {w['persona']}"):
                st.markdown(f"**왜 약점인가:** {w['rationale']}")
                st.markdown(f"**보완 제안:** {w['suggestion']}")
        if st.button("새 기획서로 다시 시작"):
            st.session_state.clear()
            st.rerun()
