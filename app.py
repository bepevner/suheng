"""우리의 하루 — 인터넷 없이 사용하는 커플 다이어리
설치(최초 1회 인터넷 필요): pip install -r requirements.txt
실행: streamlit run app.py --server.address 0.0.0.0
컴퓨터: http://localhost:8501
휴대폰: 같은 Wi-Fi에서 http://컴퓨터의내부IP:8501 로 접속.
첫 화면에서 두 사람의 이름과 비밀번호를 설정합니다.
오른쪽 ⋯ 메뉴에 위 휴대폰 접속 주소를 입력하면 QR이 만들어집니다.
컴퓨터를 켜고 앱을 실행하는 동안만 접속 가능합니다.
DB 파일 couple_diary.sqlite3는 이 파일 옆에 자동 생성됩니다.
백업은 앱을 종료한 상태에서 DB 파일을 복사하세요.
같은 공유기라도 게스트망/기기간 통신 차단/방화벽 설정에 따라 접속이 제한됩니다.
공유기 포트포워딩이나 공용 인터넷 공개용으로 사용하지 마세요.
"""
from __future__ import annotations

import hmac
import hashlib
import secrets
import sqlite3
import uuid
from pathlib import Path
import html
import io
from datetime import datetime, timezone, timedelta

import qrcode
import streamlit as st

st.set_page_config(page_title="우리의 하루", page_icon="💌", layout="centered", initial_sidebar_state="collapsed")
KST = timezone(timedelta(hours=9))
MOODS = ["😊 행복해", "🥰 설레", "😌 평온해", "😴 피곤해", "😢 속상해", "😤 답답해"]
DB_PATH = Path(__file__).resolve().with_name("couple_diary.sqlite3")

def connect():
    connection = sqlite3.connect(str(DB_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    return connection

with connect() as db:
    db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    db.execute("""CREATE TABLE IF NOT EXISTS couple_diary (
        id TEXT PRIMARY KEY, pair_id TEXT NOT NULL, diary_date TEXT NOT NULL,
        author TEXT NOT NULL, mood TEXT NOT NULL, body TEXT NOT NULL,
        updated_at TEXT NOT NULL, read_at TEXT,
        UNIQUE(pair_id, diary_date, author))""")

def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260000).hex()

st.markdown("""<style>

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
    with connect() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def check_password(identity, password):
    stored = setting(f"PARTNER_{identity.upper()}_CODE")
    if not stored:
        return False
    salt, expected = stored.split(":", 1)
    return hmac.compare_digest(password_hash(password, salt), expected)


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
    params, payload = params or {}, payload or {}
    try:
        with connect() as db:
            if method == "GET":
                rows = db.execute("SELECT * FROM couple_diary WHERE pair_id=? AND diary_date=?",
                                  (params["pair_id"][3:], params["diary_date"][3:])).fetchall()
                return [dict(row) for row in rows]
            if method == "POST":
                db.execute("""INSERT INTO couple_diary
                    (id,pair_id,diary_date,author,mood,body,updated_at,read_at)
                    VALUES (?,?,?,?,?,?,?,NULL)
                    ON CONFLICT(pair_id,diary_date,author) DO UPDATE SET
                    mood=excluded.mood, body=excluded.body,
                    updated_at=excluded.updated_at, read_at=NULL""",
                    (str(uuid.uuid4()),payload["pair_id"],payload["diary_date"],payload["author"],
                     payload["mood"],payload["body"],payload["updated_at"]))
                return []
            if method == "PATCH":
                cursor = db.execute("""UPDATE couple_diary SET read_at=?
                    WHERE id=? AND pair_id=? AND author=? AND updated_at=? AND read_at IS NULL""",
                    (payload["read_at"],params["id"][3:],params["pair_id"][3:],
                     params["author"][3:],params["updated_at"][3:]))
                return [{"updated":True}] if cursor.rowcount else []
            raise StorageError("지원하지 않는 저장 요청이에요.")
    except sqlite3.Error:
        raise StorageError("로컬 저장에 실패했어요. 저장 공간과 폴더 쓰기 권한을 확인해 주세요.") from None


if not setting("PAIR_ID"):
    st.title("💌 우리의 하루")
    st.caption("최초 한 번만 설정하면 돼요. 일기는 이 컴퓨터에 저장돼요.")
    with st.form("initial_setup"):
        name_a = st.text_input("첫 번째 이름", value="나무", max_chars=20)
        code_a = st.text_input("첫 번째 비밀번호 · 8자 이상", type="password")
        name_b = st.text_input("두 번째 이름", value="구름", max_chars=20)
        code_b = st.text_input("두 번째 비밀번호 · 8자 이상", type="password")
        setup = st.form_submit_button("우리 공간 만들기", type="primary", use_container_width=True)
    if setup:
        if not name_a.strip() or not name_b.strip() or name_a.strip() == name_b.strip():
            st.error("서로 다른 이름을 입력해 주세요.")
        elif len(code_a) < 8 or len(code_b) < 8 or code_a == code_b:
            st.error("서로 다른 비밀번호를 각각 8자 이상 입력해 주세요.")
        else:
            salt_a, salt_b = secrets.token_hex(16), secrets.token_hex(16)
            values = {"PAIR_ID": str(uuid.uuid4()), "PARTNER_A_NAME":name_a.strip(),
                      "PARTNER_B_NAME":name_b.strip(),
                      "PARTNER_A_CODE":salt_a+":"+password_hash(code_a,salt_a),
                      "PARTNER_B_CODE":salt_b+":"+password_hash(code_b,salt_b)}
            with connect() as db:
                db.execute("BEGIN IMMEDIATE")
                exists = db.execute("SELECT 1 FROM settings WHERE key='PAIR_ID'").fetchone()
                if not exists:
                    db.executemany("INSERT INTO settings(key,value) VALUES (?,?)", values.items())
            st.rerun()
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
        elif check_password(identity, password):
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
        share_url = st.text_input("휴대폰 접속 주소", placeholder="http://192.168.0.10:8501", key="share_url")
        st.caption("같은 Wi-Fi에서 접속할 컴퓨터의 내부 IP 주소를 입력하세요.")
        if share_url.startswith(("http://", "https://")):
            qr = qrcode.make(share_url)
            buffer = io.BytesIO()
            qr.save(buffer, format="PNG")
            st.image(buffer.getvalue(), caption="카메라로 스캔해 접속", width=190)
            st.download_button("QR 저장", buffer.getvalue(), "our_diary_qr.png", "image/png")
        else:
            st.caption("위에 휴대폰 접속 주소를 입력하면 QR이 표시돼요.")
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
