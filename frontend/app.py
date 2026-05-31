import streamlit as st
import time

# 페이지 설정
st.set_page_config(page_title="기획서 검증 에이전트", page_icon="💬", layout="centered")

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
                st.session_state.uploaded_file = uploaded_file
                st.session_state.page = "chat"
                # 초기 안내 메세지 세팅
                st.session_state.messages = [
                    {"role": "assistant", "name": "오케스트레이터", "content": f"기획서 파싱을 완료했습니다. 지금부터 투자자, CTO, 멘토 심사위원의 압박 질문을 시작하겠습니다. 준비되셨나요?", "avatar": "🤖"}
                ]
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)


def render_chat_page():
    # 헤더
    col1, col2 = st.columns([8, 2])
    with col1:
        st.subheader("💬 기획서 검증 방")
    with col2:
        st.markdown('<div class="exit-button-container">', unsafe_allow_html=True)
        if st.button("나가기"):
            st.session_state.page = "upload"
            st.session_state.messages = []
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("---")

    # 대화 기록 렌더링
    for msg in st.session_state.messages:
        # 사용자 메세지는 고정된 아바타 아이콘 사용, 챗봇은 이름에 따라 다른 이모지 사용 가능
        avatar = msg.get("avatar", "🧑‍💻" if msg["role"] == "user" else "🤖")
        with st.chat_message(msg["role"], avatar=avatar):
            if msg["role"] == "assistant":
                st.caption(f"**{msg.get('name', '심사위원')}**")
            st.markdown(msg["content"])

    # 채팅 입력창
    if prompt := st.chat_input("답변을 입력해주세요..."):
        # 1. 사용자 메세지 추가
        st.session_state.messages.append({"role": "user", "content": prompt, "avatar": "👤"})
        with st.chat_message("user", avatar="👤"):
            st.markdown(prompt)
            
        # 2. 챗봇(페르소나) 응답 (모의 구현)
        # 실제 구현시에는 여기서 LangGraph 로직을 호출하여 응답을 받아와야 합니다.
        with st.chat_message("assistant", avatar="💼"):
            st.caption("**투자자**")
            message_placeholder = st.empty()
            full_response = ""
            # 타이핑 효과 시뮬레이션
            mock_response = "방금 답변하신 내용은 시장 차별성 측면에서 부족해 보입니다. 이미 유사한 OOO 서비스가 시장을 점유하고 있는데, 유저가 굳이 이 서비스를 써야할 이유가 무엇인가요?"
            for chunk in mock_response.split():
                full_response += chunk + " "
                time.sleep(0.1)
                message_placeholder.markdown(full_response + "▌")
            message_placeholder.markdown(full_response)
            
        st.session_state.messages.append({"role": "assistant", "name": "투자자", "content": mock_response, "avatar": "💼"})


# 메인 앱 로직
def main():
    inject_custom_css()
    
    if st.session_state.page == "upload":
        render_upload_page()
    elif st.session_state.page == "chat":
        render_chat_page()

if __name__ == "__main__":
    main()
