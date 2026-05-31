import streamlit as st
import httpx
import json

# 페이지 설정
st.set_page_config(page_title="기획서 검증 에이전트", page_icon="💬", layout="centered")

API_BASE = "http://localhost:8000"
PERSONA_AVATAR = {"investor": "💼", "cto": "💻", "mentor": "🦉", "reporter": "🤖"}
PERSONA_NAME = {"investor": "깐깐한 투자자", "cto": "냉철한 CTO", "mentor": "예리한 멘토", "reporter": "오케스트레이터"}

# 카카오톡 스타일 Custom CSS 적용
def inject_custom_css():
    st.markdown("""
        <style>
        /* Pretendard 가변 폰트 불러오기 */
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css');

        /* 전체 폰트 적용 (가변 폰트 지원) */
        * {
            font-family: 'Pretendard Variable', Pretendard, -apple-system, system-ui, sans-serif !important;
        }

        /* 전체 배경색 (Coinbase Canvas) */
        .stApp {
            background-color: #ffffff;
            color: #0a0b0d;
        }

        /* 상단 헤더 숨기기 */
        header {visibility: hidden;}

        /* 챗봇 프로필 아이콘 */
        .stChatMessageAvatar {
            background-color: transparent !important;
            border-radius: 50%;
        }

        /* 챗봇 메세지 (왼쪽, Surface Soft) */
        [data-testid="stChatMessage"]:not([data-testid="stChatMessage"][aria-label="user"]) {
            background-color: #f7f7f7;
            color: #0a0b0d;
            border-radius: 24px;
            padding: 16px 24px;
            margin: 12px 0px;
            max-width: 85%;
            border: 1px solid #dee1e6;
            box-shadow: none;
        }

        /* 왼쪽 메세지 텍스트 가시성 강화 */
        [data-testid="stChatMessage"]:not([data-testid="stChatMessage"][aria-label="user"]) .stMarkdown p {
            color: #0a0b0d !important;
            font-weight: 450 !important;
            line-height: 1.6;
        }

        /* 사용자 메세지 (오른쪽, Coinbase Blue) */
        [data-testid="stChatMessage"][aria-label="user"] {
            background-color: #0052ff;
            color: #ffffff;
            border-radius: 24px;
            padding: 16px 24px;
            margin: 12px 0px 12px auto;
            max-width: 85%;
            flex-direction: row-reverse;
            box-shadow: none;
            border: none;
        }

        /* 사용자 메세지 안의 텍스트 색상 강제 (하얀색) */
        [data-testid="stChatMessage"][aria-label="user"] .stMarkdown p {
            color: #ffffff !important;
            font-weight: 450 !important;
            line-height: 1.6;
        }

        /* 사용자 메세지 안의 아바타 여백 조절 */
        [data-testid="stChatMessage"][aria-label="user"] .stChatMessageAvatar {
            margin-left: 1rem;
            margin-right: 0;
            background-color: #ffffff !important;
            color: #0052ff !important;
        }

        /* 하단 입력창 고정 및 스타일링 */
        .stChatInputContainer {
            background-color: #ffffff !important;
            padding: 16px !important;
            border-top: 1px solid #dee1e6;
        }

        /* 불필요한 Streamlit 컨테이너 숨김 */
        .st-emotion-cache-28gi3v.ewh6kot2 {
            display: none !important;
        }

        /* 파일 업로더 영역 (Native Container Wrapping) */
        [data-testid="stVerticalBlock"]:has(.upload-container-marker) {
            background-color: rgb(255, 255, 255);
            padding: 28px 24px;
            border-radius: 24px;
            border: 1px solid rgb(222, 225, 230);
            box-shadow: rgba(0, 0, 0, 0.02) 0px 4px 12px;
            text-align: center;
            margin-bottom: 40px;
            margin-top: 32px;
        }

        /* 파일 업로더 설명 텍스트 강화 */
        [data-testid="stVerticalBlock"]:has(.upload-container-marker) p {
            font-weight: 450;
            line-height: 1.6;
        }

        /* 스타일 적용을 위한 마커 숨김 */
        .upload-container-marker {
            display: none;
        }

        /* 🚀 메인 CTA 버튼 (모의 심사 시작하기) */
        .primary-cta-container .stButton > button {
            background-color: #0052ff !important;
            color: #ffffff !important;
            border-radius: 100px !important;
            padding: 16px 32px !important;
            border: none !important;
            transition: background-color 0.2s ease;
        }

        .primary-cta-container .stButton > button * {
            color: #ffffff !important;
            font-weight: 600 !important;
            font-size: 16px !important;
        }

        .primary-cta-container .stButton > button:hover {
            background-color: #003ecc !important;
            border-color: transparent !important;
        }

        /* 나가기 버튼 (Secondary Light) */
        .exit-button-container .stButton > button {
            background-color: #eef0f3 !important;
            color: #0a0b0d !important;
            padding: 8px 16px !important;
            border-radius: 100px !important;
            border: none !important;
        }
        .exit-button-container .stButton > button * {
            color: #0a0b0d !important;
            font-weight: 600 !important;
        }
        .exit-button-container .stButton > button:hover {
            background-color: #dee1e6 !important;
        }

        /* 제목 스타일링 (Coinbase Display 느낌) */
        h1, h2, h3 {
            color: #0a0b0d;
            font-weight: 700 !important; /* 가변 폰트를 활용한 확실한 두께감 */
            letter-spacing: -1px !important;
        }

        /* 본문 텍스트 (Body) */
        p {
            color: #5b616e;
            font-weight: 400;
        }
        </style>
    """, unsafe_allow_html=True)


# 세션 상태 초기화
if "page" not in st.session_state:
    st.session_state.page = "upload" # "upload" 또는 "chat"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file = None
if "thread_id" not in st.session_state:
    st.session_state.thread_id = None
if "is_done" not in st.session_state:
    st.session_state.is_done = False
if "chat_started" not in st.session_state:
    st.session_state.chat_started = False


def render_upload_page():
    # 1. Hero Section (헤더 영역) - Dark Hero Band
    st.markdown("""
        <div style="background-color: #0a0b0d; color: #ffffff; padding: 64px 32px; border-radius: 24px; text-align: center; margin-bottom: 48px; box-shadow: 0 20px 40px rgba(0,0,0,0.2);">
            <h1 style="color: #ffffff !important; font-size: 48px; font-weight: 700; letter-spacing: -1.5px; margin-bottom: 16px; border: none; padding: 0;">기획의 빈틈을 찾다</h1>
            <p style="color: #a8acb3; font-size: 18px; max-width: 600px; margin: 0 auto; line-height: 1.6;">
                실제 발표나 중간평가에 들어가기 전에, <span style="color: #ffffff; font-weight: 600;">3명의 다중 페르소나 AI 심사위원</span>에게 가장 날카로운 압박 질문을 미리 맞아보세요.
            </p>
        </div>
    """, unsafe_allow_html=True)

    # 2. Feature Cards (페르소나 소개 영역)
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("""
            <div style="background-color: #ffffff; padding: 28px 24px; border-radius: 24px; height: 100%; border: 1px solid #dee1e6; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">
                <div style="font-size: 40px; margin-bottom: 20px;">💼</div>
                <h3 style="font-size: 20px; margin-bottom: 12px; font-weight: 700; color: #0a0b0d !important;">깐깐한 투자자</h3>
                <p style="font-size: 15px; color: #5b616e; margin: 0; line-height: 1.6;">"이거 이미 시장에 있지 않나요?"<br>시장성과 수익성을 검증합니다.</p>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown("""
            <div style="background-color: #ffffff; padding: 28px 24px; border-radius: 24px; height: 100%; border: 1px solid #dee1e6; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">
                <div style="font-size: 40px; margin-bottom: 20px;">💻</div>
                <h3 style="font-size: 20px; margin-bottom: 12px; font-weight: 700; color: #0a0b0d !important;">냉철한 CTO</h3>
                <p style="font-size: 15px; color: #5b616e; margin: 0; line-height: 1.6;">"이 기간 안에 구현 가능한가요?"<br>기술 실현 가능성을 평가합니다.</p>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown("""
            <div style="background-color: #ffffff; padding: 28px 24px; border-radius: 24px; height: 100%; border: 1px solid #dee1e6; box-shadow: 0 4px 12px rgba(0,0,0,0.02);">
                <div style="font-size: 40px; margin-bottom: 20px;">🦉</div>
                <h3 style="font-size: 20px; margin-bottom: 12px; font-weight: 700; color: #0a0b0d !important;">예리한 멘토</h3>
                <p style="font-size: 15px; color: #5b616e; margin: 0; line-height: 1.6;">"기능이 너무 많은데 뭘 버릴 건가요?"<br>논리적 일관성과 범위를 지적합니다.</p>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<br><br>", unsafe_allow_html=True)

    # 3. Upload Container (업로드 영역)
    with st.container():
        st.markdown('<span class="upload-container-marker"></span>', unsafe_allow_html=True)
        st.markdown('<h2 style="font-size: 24px; margin-bottom: 8px;">기획서 업로드</h2>', unsafe_allow_html=True)
        st.markdown('<p style="margin-bottom: 24px;">TXT 또는 PDF 형식의 기획서를 올려주시면 즉시 분석을 시작합니다.</p>', unsafe_allow_html=True)

        uploaded_file = st.file_uploader("파일 첨부", type=['txt', 'pdf'], label_visibility="collapsed")

        if uploaded_file is not None:
            st.success(f"'{uploaded_file.name}' 파일이 성공적으로 업로드 되었습니다!")
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<div class="primary-cta-container">', unsafe_allow_html=True)
            if st.button("🚀 모의 심사 시작하기", use_container_width=True):
                with st.spinner("기획서 분석 중..."):
                    files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "text/plain")}
                    resp = httpx.post(f"{API_BASE}/upload", files=files)
                    if resp.status_code != 200:
                        st.error(f"업로드 실패: {resp.text}")
                    else:
                        data = resp.json()
                        st.session_state.thread_id = data["thread_id"]
                        st.session_state.page = "chat"
                        st.session_state.messages = [
                            {"role": "assistant", "name": "reporter",
                             "content": "기획서 파싱 완료. 첫 번째 질문을 불러오는 중입니다...",
                             "avatar": "🤖"}
                        ]
                        st.session_state.is_done = False
                        st.session_state.chat_started = False
                        st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


def _stream_and_display(url: str, method: str, params: dict = None, body: dict = None):
    """SSE 스트림을 받아 Streamlit에 실시간으로 렌더링한다."""
    current_node = None
    full_response = ""
    placeholder = None
    chat_ctx = None

    with httpx.Client(timeout=120) as client:
        if method == "GET_WITH_PARAMS":
            stream_ctx = client.stream("POST", url, params=params)
        else:  # POST_JSON
            stream_ctx = client.stream("POST", url, json=body)

        with stream_ctx as stream:
            for line in stream.iter_lines():
                if not line.startswith("data: "):
                    continue
                event = json.loads(line[6:])

                if event.get("done"):
                    if placeholder and full_response:
                        placeholder.markdown(full_response)
                    if event.get("is_final"):
                        st.session_state.is_done = True
                    break

                node = event.get("node", "")
                token = event.get("token", "")
                if not token:
                    continue

                if node != current_node:
                    if full_response and placeholder:
                        # save previous message
                        st.session_state.messages.append({
                            "role": "assistant",
                            "name": current_node,
                            "content": full_response,
                            "avatar": PERSONA_AVATAR.get(current_node, "🤖"),
                        })
                    current_node = node
                    full_response = ""
                    avatar = PERSONA_AVATAR.get(node, "🤖")
                    name = PERSONA_NAME.get(node, node)
                    chat_ctx = st.chat_message("assistant", avatar=avatar)
                    chat_ctx.__enter__()
                    st.caption(f"**{name}**")
                    placeholder = st.empty()

                full_response += token
                if placeholder:
                    placeholder.markdown(full_response + "▌")

    # Save final message
    if full_response and current_node:
        st.session_state.messages.append({
            "role": "assistant",
            "name": current_node,
            "content": full_response,
            "avatar": PERSONA_AVATAR.get(current_node, "🤖"),
        })


def render_chat_page():
    col1, col2 = st.columns([8, 2])
    with col1:
        st.subheader("💬 기획서 검증 방")
    with col2:
        st.markdown('<div class="exit-button-container">', unsafe_allow_html=True)
        if st.button("나가기"):
            st.session_state.page = "upload"
            st.session_state.messages = []
            st.session_state.thread_id = None
            st.session_state.is_done = False
            st.session_state.chat_started = False
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")

    # 대화 기록 렌더링
    for msg in st.session_state.messages:
        avatar = msg.get("avatar", "🧑‍💻" if msg["role"] == "user" else "🤖")
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                st.caption(f"**{msg.get('name', '심사위원')}**")
            st.markdown(msg["content"])

    # 첫 로드 시 자동으로 투자자 첫 질문 가져오기
    if not st.session_state.chat_started and st.session_state.thread_id:
        _stream_and_display(
            url=f"{API_BASE}/chat/start",
            body={"thread_id": st.session_state.thread_id, "message": ""},
            method="POST_JSON"
        )
        st.session_state.chat_started = True
        st.rerun()

    # 사용자 입력
    if not st.session_state.is_done:
        if prompt := st.chat_input("답변을 입력해주세요..."):
            st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "👤"})
            with st.chat_message("user", avatar="👤"):
                st.markdown(prompt)
            _stream_and_display(
                url=f"{API_BASE}/chat",
                body={"thread_id": st.session_state.thread_id, "message": prompt},
                method="POST_JSON"
            )
            st.rerun()
    else:
        st.info("심사가 완료되었습니다. 위의 종합 리포트를 확인하세요.")


# 메인 앱 로직
def main():
    inject_custom_css()

    if st.session_state.page == "upload":
        render_upload_page()
    elif st.session_state.page == "chat":
        render_chat_page()

if __name__ == "__main__":
    main()
