import os
import streamlit as st
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from database import upsert_user, get_user_by_slack_id, delete_user

load_dotenv()

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

LANGUAGE_OPTIONS = {
    "일본어 🇯🇵": "jp",
    "영어 🇺🇸": "en",
    "중국어 🇨🇳": "zh",
}

LANGUAGE_LABELS = {v: k for k, v in LANGUAGE_OPTIONS.items()}

st.set_page_config(page_title="Earn-Language-Bot", page_icon="📚")
st.title("Earn-Language-Bot")
st.caption("매일 아침 외국어 학습 문장을 슬랙 DM으로 보내드립니다.")

tab_register, tab_manage = st.tabs(["학습 신청", "설정 확인 / 해지"])

# --- 학습 신청 ---
with tab_register:
    with st.form("user_form"):
        email = st.text_input(
            "슬랙 가입 이메일",
            placeholder="you@example.com",
        )
        language_label = st.selectbox(
            "학습 언어",
            options=list(LANGUAGE_OPTIONS.keys()),
            index=0,
        )
        difficulty = st.selectbox(
            "난이도",
            options=["하", "중", "상"],
            index=1,
        )
        submitted = st.form_submit_button("신청")

    if submitted:
        if not email:
            st.error("이메일을 입력해주세요.")
        elif not SLACK_BOT_TOKEN:
            st.error("에러가 발생했습니다.")
        else:
            try:
                language = LANGUAGE_OPTIONS[language_label]
                client = WebClient(token=SLACK_BOT_TOKEN)
                resp = client.users_lookupByEmail(email=email)
                slack_user_id = resp["user"]["id"]
                user_id = upsert_user(slack_user_id, difficulty, language)
                st.success("신청 완료! 내일 아침부터 학습 문장이 도착합니다.")
            except SlackApiError as e:
                st.error(f"이메일로 사용자를 찾을 수 없습니다: {e.response['error']}")
            except Exception as e:
                st.error(f"등록 중 오류가 발생했습니다: {e}")

# --- 설정 확인 / 해지 ---
with tab_manage:
    with st.form("lookup_form"):
        lookup_email = st.text_input(
            "슬랙 가입 이메일",
            placeholder="you@example.com",
        )
        lookup_submitted = st.form_submit_button("확인")

    if lookup_submitted:
        if not lookup_email:
            st.error("이메일을 입력해주세요.")
        elif not SLACK_BOT_TOKEN:
            st.error("에러가 발생했습니다.")
        else:
            try:
                client = WebClient(token=SLACK_BOT_TOKEN)
                resp = client.users_lookupByEmail(email=lookup_email)
                slack_user_id = resp["user"]["id"]
                user = get_user_by_slack_id(slack_user_id)
                if user:
                    st.session_state["lookup_user"] = user
                else:
                    st.info("신청 내역이 없습니다.")
                    st.session_state.pop("lookup_user", None)
            except SlackApiError:
                st.error("이메일로 사용자를 찾을 수 없습니다.")
                st.session_state.pop("lookup_user", None)
            except Exception as e:
                st.error(f"조회 중 오류가 발생했습니다: {e}")
                st.session_state.pop("lookup_user", None)

    if "lookup_user" in st.session_state:
        user = st.session_state["lookup_user"]
        lang_code = user.get("language", "jp")
        lang_label = LANGUAGE_LABELS.get(lang_code, lang_code)
        st.markdown(
            f"언어: **{lang_label}** | 난이도: **{user.get('difficulty', '중')}**"
        )
        if st.button("해지"):
            try:
                delete_user(user["id"])
                st.session_state.pop("lookup_user", None)
                st.success("해지 완료!")
                st.rerun()
            except Exception as e:
                st.error(f"해지 중 오류가 발생했습니다: {e}")
