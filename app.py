"""우리의 하루 — Streamlit 커플 다이어리

실행: streamlit run app.py
설치: pip install -r requirements.txt

[최초 설정]
1. Supabase 프로젝트 생성 → SQL Editor에서 아래 SQL 실행.
2. Streamlit Community Cloud에서 GitHub 저장소의 app.py 배포.
3. 앱 Settings → Secrets에 아래 예시를 본인 값으로 입력.
4. APP_URL에 배포 주소를 넣으면 앱의 'QR' 버튼으로 공유 가능.

[Supabase SQL]
create table public.couple_diary (
    id uuid primary key default gen_random_uuid(),
    pair_id text not null,
    diary_date date not null,
    author text not null check (author in ('a', 'b')),
    mood text not null,
    body text not null check (char_length(body) between 1 and 1000),
    updated_at timestamptz not null default now(),
    read_at timestamptz,
    unique (pair_id, diary_date, author)
);
alter table public.couple_diary enable row level security;
revoke all on table public.couple_diary from anon, authenticated;

[Streamlit Secrets — GitHub에 올리지 마세요]
SUPABASE_URL = "https://프로젝트ID.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "Supabase의 service_role 키"
PAIR_ID = "추측하기-어려운-우리커플-고유문자열"
PARTNER_A_NAME = "나무"
PARTNER_B_NAME = "구름"
PARTNER_A_CODE = "각자다른8자이상비밀번호"
PARTNER_B_CODE = "또다른8자이상비밀번호"
APP_URL = "https://배포이름.streamlit.app"

주의: 한 배포당 한 커플용입니다. service_role 키는 서버 Secrets에만 보관하세요.
       날짜는 한국 시간 기준입니다. 날짜별 각자 한 편이며 수정하면 읽음이 초기화됩니다.
       애플리케이션 코드는 비공개 일기를 GitHub에 저장하지 않습니다.
"""
from __future__ import annotations

import hmac
import html
import io
from datetime import datetime, timezone, timedelta

import qrcode
import requests
import streamlit as st

st.set_page_config(page_title="우리의 하루", page_icon="💌", layout="centered", initial_sidebar_state="collapsed")
KST = timezone(timedelta(hours=9))
MOODS = ["😊 행복해", "🥰 설레", "😌 평온해", "😴 피곤해", "😢 속상해", "😤 답답해"]
SQL = """create table public.couple_diary (
  id uuid primary key default gen_random_uuid(),
  pair_id text not null,
  diary_date date not null,
  author text not null check (author in ('a', 'b')),
  mood text not null,
  body text not null check (char_length(body) between 1 and 1000),
  updated_at timestamptz not null default now(),
  read_at timestamptz,
  unique (pair_id, diary_date, author)
);
alter table public.couple_diary enable row level security;
revoke all on table public.couple_diary from anon, authenticated;"""
SECRETS_SAMPLE = '''SUPABASE_URL = "https://프로젝트ID.supabase.co"
SUPABASE_SERVICE_ROLE_KEY = "service_role 키"
PAIR_ID = "우리커플-고유문자열"
PARTNER_A_NAME = "나무"
PARTNER_B_NAME = "구름"
PARTNER_A_CODE = "서로다른8자이상비밀번호A"
PARTNER_B_CODE = "서로다른8자이상비밀번호B"
APP_URL = "https://배포이름.streamlit.app"'''

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap');
html, body, [class*="css"], .stApp {font-family:'Noto Sans KR',sans-serif;}
.stApp {background:#fff8f5; color:#413635;}
header[data-testid="stHeader"] {background:transparent; height:0;}
[data-testid="stToolbar"], #MainMenu, footer {display:none;}
.block-container {max-width:490px; padding:0.6rem 0.85rem 0.4rem;}
[data-testid="stVerticalBlock"] {gap:0.38rem;}
[data-testid="stHorizontalBlock"] {gap:0.45rem;}
[data-testid="stColumn"] {min-width:0 !important;}
h1 {font-size:1.35rem!important;padding:0!important;margin:0!important;}
p {margin:0 0 0.25rem;}
[data-testid="stCaptionContainer"] p {font-size:0.73rem;}
[data-testid="stWidgetLabel"] p {font-size:0.8rem;}
.stButton button, .stPopover button, .stFormSubmitButton button {min-height:2rem; padding:0.2rem 0.5rem; border-radius:12px;}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primary"] {background:#c86879;border-color:#c86879;}
[data-testid="stTextArea"] textarea {font-size:0.87rem; padding:0.5rem;}
[data-testid="stForm"] {padding:0.55rem; border:1px solid #efdcd6; border-radius:16px; background:#fff;}
.letter {background:#fff;border:1px solid #efdcd6;border-radius:16px;padding:10px 12px;}
.letter-head {font-size:0.8rem;font-weight:600;margin-bottom:5px;color:#a34e61;}
.letter-body {height:83px;overflow-y:auto;white-space:pre-wrap;overflow-wrap:anywhere;font-size:0.86rem;line-height:1.55;}
.stAlert {padding:0.4rem;}
@media (max-width:640px) {
 .block-container {padding-top:0.4rem;padding-bottom:0.25rem;}
 [data-testid="stHorizontalBlock"] {flex-wrap:nowrap!important;}
 [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {flex:1 1 0!important;width:auto!important;}
}
@media (max-height:700px) {
 .block-container {padding-top:0.2rem;}
 [data-testid="stVerticalBlock"] {gap:0.22rem;}
 .letter-body {height:62px;}
}
</style>""", unsafe_allow_html=True)


def setting(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, default)).strip()
    except FileNotFoundError:
        return default


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def display_time(value: str | None) -> str:
    if not value:
        return ""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(KST).strftime("%m/%d %H:%M")
    except (ValueError, TypeError):
        return ""


class StorageError(Exception):
    pass


def database(method: str, params: dict | None = None, payload: dict | None = None) -> list:
    """Secrets 키를 브라우저에 전달하지 않고 서버에서만 REST 요청합니다."""
    headers = {
        "apikey": setting("SUPABASE_SERVICE_ROLE_KEY"),
        "Authorization": "Bearer " + setting("SUPABASE_SERVICE_ROLE_KEY"),
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation" if method == "POST" else "return=representation",
    }
    try:
        response = requests.request(method, setting("SUPABASE_URL").rstrip("/") + "/rest/v1/couple_diary",
                                    headers=headers, params=params, json=payload, timeout=15)
        if not response.ok:
            # 응답 본문이나 키를 화면/로그에 노출하지 않습니다.
            raise StorageError(f"저장소 연결 오류 ({response.status_code}). 주소·키·테이블 설정을 확인하세요.")
        return response.json() if response.content else []
    except (requests.RequestException, ValueError):
        raise StorageError("저장소에 연결하지 못했어요. 잠시 후 새로고침해 주세요.") from None


required = ["SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "PAIR_ID", "PARTNER_A_CODE", "PARTNER_B_CODE"]
if any(not setting(key) for key in required):
    st.title("💌 우리의 하루")
    st.info("처음 한 번만 저장소와 두 사람의 비밀번호를 설정해 주세요.")
    with st.expander("① Supabase SQL Editor에서 실행", expanded=True):
        st.code(SQL, language="sql")
    with st.expander("② Streamlit 앱 Settings → Secrets에 입력"):
        st.code(SECRETS_SAMPLE, language="toml")
    st.caption("GitHub에는 app.py와 requirements.txt만 업로드하세요. 비밀번호와 키는 업로드하지 마세요.")
    st.stop()

if (len(setting("PARTNER_A_CODE")) < 8 or len(setting("PARTNER_B_CODE")) < 8
        or hmac.compare_digest(setting("PARTNER_A_CODE").encode(), setting("PARTNER_B_CODE").encode())):
    st.error("두 사람의 비밀번호를 서로 다르게, 각각 8자 이상으로 설정하세요.")
    st.stop()

names = {"a": setting("PARTNER_A_NAME", "나무"), "b": setting("PARTNER_B_NAME", "구름")}
# 로그인 실패 잠금은 세션 단위 보조 장치입니다. 강력하고 고유한 비밀번호를 사용하세요.
if "who" not in st.session_state:
    st.title("💌 우리의 하루")
    st.caption("너의 오늘을 읽고, 나의 마음을 남겨요.")
    with st.form("login"):
        identity = st.selectbox("나는", ["a", "b"], format_func=lambda x: names[x])
        password = st.text_input("나만의 비밀번호", type="password")
        login = st.form_submit_button("우리 공간 들어가기", type="primary", use_container_width=True)
    if login:
        now = datetime.now(timezone.utc).timestamp()
        if now < st.session_state.get("blocked_until", 0):
            st.error("잠시 후 다시 시도해 주세요. (최대 60초)")
        elif hmac.compare_digest(password.encode(), setting(f"PARTNER_{identity.upper()}_CODE").encode()):
            st.session_state.who = identity
            st.session_state.failures = 0
            st.rerun()
        else:
            st.session_state.failures = st.session_state.get("failures", 0) + 1
            if st.session_state.failures >= 5:
                st.session_state.blocked_until = now + 60
                st.session_state.failures = 0
            st.error("비밀번호를 확인해 주세요.")
    st.stop()

who = st.session_state.who
other = "b" if who == "a" else "a"

left, right = st.columns([3, 1])
with left:
    st.title("💌 우리의 하루")
with right:
    with st.popover("⋯"):
        st.caption(f"{names[who]} 님으로 접속 중")
        if setting("APP_URL"):
            qr = qrcode.make(setting("APP_URL"))
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            st.image(buffer.getvalue(), caption="카메라로 스캔해 접속", width=190)
            st.download_button("QR 저장", buffer.getvalue(), "our_diary_qr.png", "image/png")
        else:
            st.caption("Secrets에 APP_URL을 넣으면 접속 QR이 표시돼요.")
        st.caption("날짜별 한 편 · 수정하면 상대의 확인 상태가 초기화돼요.")
        st.caption("새 글과 확인 상태는 새로고침 버튼으로 불러와요.")
        if st.button("로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

c1, c2 = st.columns([3, 1])
with c1:
    day = st.date_input("날짜", value=datetime.now(KST).date(), max_value=datetime.now(KST).date(),
                        label_visibility="collapsed", key="diary_day")
with c2:
    if st.button("↻ 새로고침", use_container_width=True):
        st.rerun()

try:
    rows = database("GET", {"pair_id": "eq." + setting("PAIR_ID"), "diary_date": "eq." + day.isoformat(), "select": "*"})
except StorageError as exc:
    st.error(str(exc))
    st.stop()
by_author = {row["author"]: row for row in rows}
mine = by_author.get(who)
theirs = by_author.get(other)

# 날짜가 달라지면 입력 상태를 해당 날짜의 저장 내용으로 초기화합니다.
editor_id = f"{who}:{day.isoformat()}"
if st.session_state.get("editor_id") != editor_id:
    st.session_state.editor_id = editor_id
    st.session_state.draft_body = mine["body"] if mine else ""
    st.session_state.draft_mood = mine["mood"] if mine and mine["mood"] in MOODS else MOODS[0]

with st.form("write_diary", clear_on_submit=False):
    st.selectbox("오늘 내 기분", MOODS, key="draft_mood", label_visibility="collapsed")
    body = st.text_area("내 일기", key="draft_body", height=95, max_chars=1000,
                        placeholder="오늘 너에게 들려주고 싶은 이야기…", label_visibility="collapsed")
    sent = st.form_submit_button("💌 수정 저장" if mine else "💌 마음 보내기", type="primary", use_container_width=True)
if sent:
    clean_body = body.strip()
    if not clean_body:
        st.warning("짧게라도 오늘의 이야기를 적어 주세요.")
    else:
        try:
            database("POST", {"on_conflict": "pair_id,diary_date,author"}, {
                "pair_id": setting("PAIR_ID"), "diary_date": day.isoformat(), "author": who,
                "mood": st.session_state.draft_mood, "body": clean_body,
                "updated_at": stamp(), "read_at": None,
            })
            st.rerun()
        except StorageError as exc:
            st.error(str(exc))

if mine:
    status = f"💗 {names[other]} 님 확인 · {display_time(mine.get('read_at'))}" if mine.get("read_at") else f"✉️ {names[other]} 님이 아직 확인 전이에요"
    st.caption(status)
else:
    st.caption("✏️ 오늘의 마음을 남겨 주세요. 최대 1,000자")

heading = html.escape(f"{names[other]}의 하루 · {theirs['mood']}" if theirs else f"{names[other]}의 하루")
content = html.escape(theirs["body"] if theirs else "아직 일기가 도착하지 않았어요. 조금만 기다려 주세요 💌")
st.markdown(f'<div class="letter"><div class="letter-head">{heading}</div><div class="letter-body">{content}</div></div>', unsafe_allow_html=True)
if theirs:
    if theirs.get("read_at"):
        st.caption(f"✓ 내가 확인했어요 · {display_time(theirs['read_at'])}")
    elif st.button("✓ 읽었어요 — 상대에게 알리기", use_container_width=True):
        try:
            # 읽는 동안 상대가 수정했다면 이전 버전에 대한 확인을 새 글에 적용하지 않습니다.
            changed = database("PATCH", {
                "id": "eq." + theirs["id"], "pair_id": "eq." + setting("PAIR_ID"),
                "author": "eq." + other, "updated_at": "eq." + theirs["updated_at"], "read_at": "is.null",
            }, {"read_at": stamp()})
            if not changed:
                st.info("일기가 변경되었어요. 새로고침한 뒤 다시 확인해 주세요.")
            else:
                st.rerun()
        except StorageError as exc:
            st.error(str(exc))
else:
    st.caption("💞 서로의 작은 하루가 쌓이는 곳")
