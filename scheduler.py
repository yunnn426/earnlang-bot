import os
import sys
from openai import OpenAI
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv
from database import get_all_users

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini")  # "openai" or "gemini"
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")

_LLM_CONFIGS = {
    "openai": {
        "api_key_env": "OPENAI_API_KEY",
        "base_url": None,
        "model": "gpt-4o-mini",
    },
    "gemini": {
        "api_key_env": "GEMINI_API_KEY",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash-lite",
    },
}


def _get_llm_client() -> tuple[OpenAI, str]:
    if LLM_PROVIDER not in _LLM_CONFIGS:
        raise ValueError(
            f"LLM_PROVIDER='{LLM_PROVIDER}' 는 지원되지 않습니다. "
            f"사용 가능: {list(_LLM_CONFIGS.keys())}"
        )
    cfg = _LLM_CONFIGS[LLM_PROVIDER]
    api_key = os.getenv(cfg["api_key_env"])
    if not api_key:
        raise RuntimeError(f"{cfg['api_key_env']}가 설정되지 않았습니다.")
    client = OpenAI(api_key=api_key, base_url=cfg["base_url"])
    return client, cfg["model"]

LANGUAGES = {
    "jp": {"name": "일본어", "flag": "🇯🇵"},
    "en": {"name": "영어", "flag": "🇺🇸"},
    "zh": {"name": "중국어", "flag": "🇨🇳"},
}

_COMMON_RULES = (
    "인사말, 서론, 부연 설명 절대 금지. 문장과 형식만 출력해.\n"
    "이모지는 문장 번호(1️⃣ 2️⃣ 3️⃣)에만 사용. 그 외 이모지 금지\n"
    "Slack mrkdwn 포맷:\n"
    "   - 마크다운 헤더(#, ##), 코드블록(```) 사용 금지\n"
    "   - 굵게: *텍스트*\n"
)

_LANG_INSTRUCTIONS = {
    "jp": {
        "role": "너는 일본어 학습을 돕는 선생님이야. 매일 학습할 수 있는 일본어 문장을 생성해줘.",
        "rules": (
            "1. 후리가나는 한자에만 붙여. 히라가나/카타카나에는 절대 붙이지 마. "
            "예: 食(た)べる ← 올바름, おはよう(おはよう) ← 이런 건 금지\n"
            "2. '읽기'에는 문장 전체를 영어 로마자(romaji)로 표기. 예: taberu, ohayou gozaimasu\n"
        ),
        "format": "1️⃣ *日本語文장*\n읽기: ...\n번역: ...\n문법: ...\n\n━━━━━━━━━━\n\n",
    },
    "en": {
        "role": "너는 영어 학습을 돕는 선생님이야. 매일 학습할 수 있는 영어 문장을 생성해줘.",
        "rules": "1. 발음 가이드는 한글 표기로 제공. 예: pronunciation → 프로넌시에이션\n",
        "format": "1️⃣ *English sentence*\n발음: ...\n번역: ...\n문법: ...\n\n━━━━━━━━━━\n\n",
    },
    "zh": {
        "role": "너는 중국어 학습을 돕는 선생님이야. 매일 학습할 수 있는 중국어 문장을 생성해줘.",
        "rules": "1. 모든 중국어 문장에 병음(pinyin)을 반드시 표기해줘. 예: 你好 (nǐ hǎo)\n",
        "format": "1️⃣ *中文句子*\n병음: ...\n번역: ...\n문법: ...\n\n━━━━━━━━━━\n\n",
    },
}


def _build_system_instruction(lang: str) -> str:
    cfg = _LANG_INSTRUCTIONS[lang]
    return (
        f"{cfg['role']}\n\n"
        f"반드시 지켜야 할 규칙:\n"
        f"{cfg['rules']}"
        f"{_COMMON_RULES}"
        f"각 문장은 아래 형식으로만 작성:\n\n"
        f"{cfg['format']}"
    )

DIFFICULTY_PROMPTS = {
    "jp": {
        "하": (
            "일본어 초급(JLPT N5) 수준의 짧은 일상 회화 문장 3개를 만들어줘. "
            "히라가나 위주로 작성하되, 한자가 있으면 후리가나와 로마자 발음을 함께 표기해줘. "
            "각 문장마다 한국어 번역과 핵심 문법 포인트를 함께 제공해줘."
        ),
        "중": (
            "일본어 중급(JLPT N4~N3) 수준의 실용 문장 3개를 만들어줘. "
            "한자를 적절히 사용하고, 각 문장마다 후리가나, 로마자 발음, 한국어 번역, 문법 해설을 제공해줘."
        ),
        "상": (
            "일본어 고급(JLPT N1~N2) 수준의 문장 3개를 만들어줘. "
            "비즈니스 또는 뉴스에서 사용하는 표현을 포함하고, "
            "각 문장마다 후리가나, 로마자 발음, 한국어 번역, 문법 해설을 제공해줘."
        ),
    },
    "en": {
        "하": (
            "영어 초급(초등 수준) 일상 회화 문장 3개를 만들어줘. "
            "쉬운 단어 위주로 작성하고, 한글 발음 가이드를 함께 표기해줘. "
            "각 문장마다 한국어 번역과 핵심 문법 포인트를 함께 제공해줘."
        ),
        "중": (
            "영어 중급(TOEIC 600~700) 수준의 실용 문장 3개를 만들어줘. "
            "각 문장마다 한글 발음 가이드, 한국어 번역, 문법 해설을 제공해줘."
        ),
        "상": (
            "영어 고급(TOEIC 800+) 수준의 문장 3개를 만들어줘. "
            "비즈니스 또는 뉴스에서 사용하는 표현을 포함하고, "
            "각 문장마다 한글 발음 가이드, 한국어 번역, 문법 해설을 제공해줘."
        ),
    },
    "zh": {
        "하": (
            "중국어 초급(HSK 1~2) 수준의 짧은 일상 회화 문장 3개를 만들어줘. "
            "간체자를 사용하고, 각 문장마다 병음(pinyin), 한국어 번역, 핵심 문법 포인트를 함께 제공해줘."
        ),
        "중": (
            "중국어 중급(HSK 3~4) 수준의 실용 문장 3개를 만들어줘. "
            "각 문장마다 병음(pinyin), 한국어 번역, 문법 해설을 제공해줘."
        ),
        "상": (
            "중국어 고급(HSK 5~6) 수준의 문장 3개를 만들어줘. "
            "비즈니스 또는 뉴스에서 사용하는 표현을 포함하고, "
            "각 문장마다 병음(pinyin), 한국어 번역, 문법 해설을 제공해줘."
        ),
    },
}


def generate_sentences(language: str, difficulty: str) -> str:
    client, model = _get_llm_client()
    prompts = DIFFICULTY_PROMPTS.get(language, DIFFICULTY_PROMPTS["jp"])
    prompt = prompts.get(difficulty, prompts["중"])
    system = _build_system_instruction(language if language in _LANG_INSTRUCTIONS else "jp")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    content = response.choices[0].message.content
    if not content:
        raise ValueError(f"LLM이 빈 응답을 반환했습니다. ({language}/{difficulty})")
    return content


def send_dm(slack_user_id: str, message: str, language: str = "jp") -> None:
    client = WebClient(token=SLACK_BOT_TOKEN)
    lang_info = LANGUAGES.get(language, LANGUAGES["jp"])
    header = f"📚 *오늘의 {lang_info['name']} 학습* 📚"
    client.chat_postMessage(
        channel=slack_user_id,
        text=f"{header}\n\n{message}",
    )


def run(target_uid: str | None = None) -> None:
    cfg = _LLM_CONFIGS.get(LLM_PROVIDER)
    if not cfg:
        print(f"ERROR: LLM_PROVIDER='{LLM_PROVIDER}' 는 지원되지 않습니다.")
        sys.exit(1)
    if not os.getenv(cfg["api_key_env"]):
        print(f"ERROR: {cfg['api_key_env']}가 설정되지 않았습니다.")
        sys.exit(1)
    if not SLACK_BOT_TOKEN:
        print("ERROR: SLACK_BOT_TOKEN이 설정되지 않았습니다.")
        sys.exit(1)

    users = get_all_users()
    if not users:
        print("등록된 사용자가 없습니다.")
        return

    if target_uid:
        users = [u for u in users if u["slack_user_id"] == target_uid]
        if not users:
            print(f"ERROR: UID '{target_uid}'에 해당하는 유저가 없습니다.")
            return
        print(f"[DEV] 대상 유저: {target_uid}")

    # (language, difficulty) 조합별로 한 번만 생성
    cache: dict[tuple[str, str], str] = {}
    for lang, diff in {
        (user.get("language", "jp"), user.get("difficulty", "중")) for user in users
    }:
        try:
            print(f"[{lang}/{diff}] 문장 생성 중...")
            cache[(lang, diff)] = generate_sentences(lang, diff)
        except Exception as e:
            print(f"[{lang}/{diff}] 문장 생성 실패: {e}")

    for user in users:
        try:
            lang = user.get("language", "jp")
            diff = user.get("difficulty", "중")
            sentences = cache.get((lang, diff))
            if not sentences:
                print(f"[User {user['id']}] 생성된 문장 없음 (건너뜀).")
                continue
            send_dm(user["slack_user_id"], sentences, lang)
            print(f"[User {user['id']}] DM 전송 완료.")
        except SlackApiError as e:
            print(f"[User {user['id']}] 슬랙 전송 실패: {e.response['error']}")
        except Exception as e:
            print(f"[User {user['id']}] 오류 발생: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", help="특정 Slack UID에게만 전송 (테스트용)")
    args = parser.parse_args()
    run(target_uid=args.uid)
