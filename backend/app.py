"""
МЕТЭК Сочи — бэкенд (FastAPI).

  POST /api/callback   — заявка на обратный звонок → письмо «Заказ на обратный звонок №N»
  GET  /upload         — вход (логин + пароль + TOTP) или страница загрузки прайса
  POST /upload/login   — шаг 1: логин + пароль (bcrypt)
  POST /upload/totp    — шаг 2: код TOTP (Google Authenticator / Яндекс Ключ) → cookie-сессия
  POST /upload/logout
  GET  /upload/list    — версии прайса (нужна сессия)
  POST /upload/file    — .xlsx/.ods → importer → site/prices.json (битый файл не публикуется)
  GET  /healthz

Конфиг: backend/config.env (см. config.env.example) или переменные окружения.
Ключи: python3 admin_tools.py password | totp
"""
from __future__ import annotations

import asyncio
import hmac
import json
import logging
import os
import re
import secrets
import smtplib
import ssl
import threading
import time
import zipfile
from datetime import datetime
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from pathlib import Path

import bcrypt
import pyotp
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, field_validator
from starlette.middleware.base import BaseHTTPMiddleware

from importer import ImportFormatError, parse_price_file, publish
from sqlalchemy import text
from sqlalchemy.orm import Session
from db import get_engine
from catalog_service import replace_catalog
from catalog_routes import router as catalog_router

BASE_DIR = Path(__file__).resolve().parent


# ── конфиг ───────────────────────────────────────────────────────────────────
def _load_config_env() -> None:
    """KEY=VALUE из config.env рядом с app.py; переменные окружения имеют приоритет."""
    cfg = BASE_DIR / "config.env"
    if not cfg.exists():
        return
    for line in cfg.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


_load_config_env()

def env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()

ADMIN_USER = env("ADMIN_USER")
ADMIN_PASS_HASH = env("ADMIN_PASS_HASH")
ADMIN_TOTP_SECRET = env("ADMIN_TOTP_SECRET").replace(" ", "").upper()
TRUST_PROXY = env("TRUST_PROXY", "0") == "1"          # брать IP из X-Forwarded-For (только за nginx)
COOKIE_SECURE = env("COOKIE_SECURE", "auto")          # auto | 1 | 0
SITE_DIR = Path(env("SITE_DIR") or (BASE_DIR.parent / "site"))
PRICES_JSON = SITE_DIR / "prices.json"

SMTP_HOST = env("SMTP_HOST")
SMTP_PORT = int(env("SMTP_PORT", "465"))
SMTP_USER = env("SMTP_USER")
SMTP_PASS = env("SMTP_PASS")
MAIL_FROM = env("MAIL_FROM") or SMTP_USER
MAIL_TO = [a.strip() for a in env("MAIL_TO").split(",") if a.strip()]
MAIL_FROM_NAME = env("MAIL_FROM_NAME", "Сайт МЕТЭК Сочи")

DATA = BASE_DIR / "data"
INCOMING = DATA / "incoming"
BACKUPS = DATA / "backups"
ORDERS_FILE = DATA / "orders.json"
INCOMING.mkdir(parents=True, exist_ok=True)

MAX_UPLOAD_MB = 10
MAX_UNZIPPED_MB = 60           # защита от zip-бомбы внутри xlsx/ods
KEEP_VERSIONS = 5
SESSION_TTL = 8 * 3600
SESSION_IDLE = 3600
SESSION_COOKIE = "__Host-metek_session"   # префикс __Host- требует Secure + path=/
SESSION_COOKIE_PLAIN = "metek_session"    # для локального http
ZIP_MAGIC = b"PK\x03\x04"
LOGIN_FAILS = 8
LOGIN_WINDOW = 900

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("metek")
if not (ADMIN_USER and ADMIN_PASS_HASH):
    log.warning("ADMIN_USER/ADMIN_PASS_HASH не заданы — вход в /upload невозможен")
if not ADMIN_TOTP_SECRET:
    log.warning("ADMIN_TOTP_SECRET не задан — вход только по паролю (сгенерируй: admin_tools.py totp)")
if not (SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_TO):
    log.warning("SMTP не настроен — заявки будут только в логе")

app = FastAPI(title="МЕТЭК Сочи", docs_url=None, redoc_url=None, openapi_url=None)
app.include_router(catalog_router)


# ── безопасность: заголовки, Origin, IP ──────────────────────────────────────
class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        resp = await call_next(request)
        h = resp.headers
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("Referrer-Policy", "same-origin")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Cache-Control", "no-store")
        if "content-security-policy" not in h:
            h["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return resp


app.add_middleware(SecurityHeaders)


def _client_ip(request: Request) -> str:
    if TRUST_PROXY:
        fwd = request.headers.get("x-forwarded-for")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "?"


def _is_https(request: Request) -> bool:
    if COOKIE_SECURE == "1":
        return True
    if COOKIE_SECURE == "0":
        return False
    return (request.url.scheme == "https"
            or (TRUST_PROXY and request.headers.get("x-forwarded-proto") == "https"))


def _same_origin(request: Request) -> None:
    """Защита от CSRF: POST принимаем только со своего origin (Origin/Referer обязателен)."""
    host = request.headers.get("host", "")
    origin = request.headers.get("origin") or request.headers.get("referer") or ""
    m = re.match(r"^https?://([^/]+)", origin)
    if not m or m.group(1).lower() != host.lower():
        raise HTTPException(403, "Запрос отклонён (origin)")


# ── троттлинг ────────────────────────────────────────────────────────────────
class Throttle:
    """Скользящее окно: не больше `limit` событий за `window` секунд на ключ."""
    def __init__(self, limit: int, window: int):
        self.limit, self.window = limit, window
        self._log: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_prune = 0.0

    def _prune(self, now: float) -> None:
        if now - self._last_prune < 60:
            return
        self._last_prune = now
        for k in [k for k, v in self._log.items() if not v or now - v[-1] > self.window]:
            self._log.pop(k, None)

    def blocked(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            self._prune(now)
            recent = [t for t in self._log.get(key, []) if now - t < self.window]
            self._log[key] = recent
            return len(recent) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            self._log.setdefault(key, []).append(time.time())


login_throttle = Throttle(LOGIN_FAILS, LOGIN_WINDOW)
callback_throttle = Throttle(5, 3600)


# ── сессии ───────────────────────────────────────────────────────────────────
_sessions: dict[str, dict] = {}
_pending: dict[str, float] = {}   # токен «пароль принят, ждём код» -> истекает
_sess_lock = threading.Lock()
_totp_last_counter = 0  # защита от повторного использования кода
PENDING_COOKIE = "metek_2fa"
PENDING_TTL = 180


def _cookie_name(request: Request) -> str:
    return SESSION_COOKIE if _is_https(request) else SESSION_COOKIE_PLAIN


def _session_valid(request: Request) -> bool:
    token = request.cookies.get(_cookie_name(request), "")
    now = time.time()
    with _sess_lock:
        sess = _sessions.get(token)
        if not sess:
            return False
        if sess["exp"] < now or now - sess["last"] > SESSION_IDLE:
            _sessions.pop(token, None)
            return False
        sess["last"] = now
        return True


def _require_session(request: Request) -> None:
    if not _session_valid(request):
        raise HTTPException(401, "Требуется вход")


def _new_session(response: Response, request: Request) -> None:
    now = time.time()
    token = secrets.token_urlsafe(32)
    with _sess_lock:
        for t in [t for t, s in _sessions.items() if s["exp"] < now or now - s["last"] > SESSION_IDLE]:
            _sessions.pop(t, None)
        _sessions[token] = {"exp": now + SESSION_TTL, "last": now}
    https = _is_https(request)
    response.set_cookie(
        _cookie_name(request), token, max_age=SESSION_TTL,
        httponly=True, samesite="strict", secure=https, path="/",
    )


def _drop_session(request: Request, response: Response) -> None:
    token = request.cookies.get(_cookie_name(request), "")
    with _sess_lock:
        _sessions.pop(token, None)
    response.delete_cookie(_cookie_name(request), path="/")


def _check_totp(code: str) -> bool:
    global _totp_last_counter
    if not ADMIN_TOTP_SECRET:
        return True
    code = re.sub(r"\D", "", code or "")
    if len(code) != 6:
        return False
    totp = pyotp.TOTP(ADMIN_TOTP_SECRET)
    now = int(time.time())
    for drift in (0, -1, 1):            # ±30 с на расхождение часов
        t = now + drift * 30
        if hmac.compare_digest(totp.at(t), code):
            counter = t // 30
            if counter <= _totp_last_counter:
                return False            # код уже использован
            _totp_last_counter = counter
            return True
    return False


# ── заявка на обратный звонок ────────────────────────────────────────────────
NAME_RE = re.compile(r"^[А-Яа-яЁёA-Za-z][А-Яа-яЁёA-Za-z\s\-\.]{1,59}$")


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10 and digits[0] == "9":
        digits = "7" + digits
    if len(digits) != 11 or digits[0] != "7" or len(set(digits[1:])) == 1:
        return None
    return "+" + digits


class Callback(BaseModel):
    name: str
    phone: str
    website: str = ""   # honeypot: люди его не видят, боты заполняют

    @field_validator("name")
    @classmethod
    def name_ok(cls, v: str) -> str:
        v = " ".join(v.split())
        if not NAME_RE.fullmatch(v):
            raise ValueError("имя: только буквы, 2–60 символов")
        return v

    @field_validator("phone")
    @classmethod
    def phone_ok(cls, v: str) -> str:
        p = normalize_phone(v)
        if not p:
            raise ValueError("телефон: российский номер из 11 цифр")
        return p


_orders_lock = threading.Lock()


def next_order_number() -> int:
    """Сквозной номер заявки, хранится в data/orders.json, пишется атомарно."""
    with _orders_lock:
        n = 0
        if ORDERS_FILE.exists():
            try:
                n = int(json.loads(ORDERS_FILE.read_text()).get("last", 0))
            except Exception:
                log.exception("orders.json повреждён — счётчик продолжу с 0")
        n += 1
        tmp = ORDERS_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps({"last": n, "updated": datetime.now().isoformat(timespec="seconds")}))
        os.replace(tmp, ORDERS_FILE)
        return n


MAIL_TEMPLATE = """Здравствуйте!

На сайте оставлена заявка на обратный звонок №{n}.

Имя:      {name}
Телефон:  {phone}

Пожалуйста, свяжитесь с клиентом в рабочее время.

—
Отправлено: {when}
Письмо сформировано автоматически, отвечать на него не нужно.
"""


def _send_order_mail(n: int, name: str, phone: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = f"Заказ на обратный звонок №{n}"
    msg["From"] = f"{MAIL_FROM_NAME} <{MAIL_FROM}>"
    msg["To"] = ", ".join(MAIL_TO)
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=MAIL_FROM.split("@")[-1] or "localhost")
    msg["X-Auto-Response-Suppress"] = "All"
    msg.set_content(MAIL_TEMPLATE.format(n=n, name=name, phone=phone,
                                         when=datetime.now().strftime("%d.%m.%Y %H:%M")))
    ctx = ssl.create_default_context()
    if SMTP_PORT == 465:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ctx) as s:
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)
    else:  # 587 STARTTLS
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as s:
            s.starttls(context=ctx)
            s.login(SMTP_USER, SMTP_PASS)
            s.send_message(msg)


@app.post("/api/callback")
async def callback(data: Callback, request: Request):
    _same_origin(request)
    ip = _client_ip(request)
    if data.website:                      # бот заполнил honeypot — делаем вид, что всё ок
        log.info("honeypot сработал, ip %s", ip)
        return {"ok": True}
    if callback_throttle.blocked(ip):
        raise HTTPException(429, "Слишком много заявок, попробуйте позже.")
    callback_throttle.hit(ip)

    n = next_order_number()
    log.info("Заявка №%d: %s / %s (ip %s)", n, data.name, data.phone, ip)
    if SMTP_HOST and SMTP_USER and SMTP_PASS and MAIL_TO:
        try:
            await asyncio.to_thread(_send_order_mail, n, data.name, data.phone)
        except Exception:
            log.exception("SMTP: письмо по заявке №%d не ушло — данные в логе выше", n)
    return {"ok": True, "number": n}


# ── файлы прайса ─────────────────────────────────────────────────────────────
PRICE_EXT = (".xlsx", ".ods")
SAFE_NAME_RE = re.compile(r"[^\w\s\-\.\(\)А-Яа-яЁё]", re.UNICODE)


def _price_files(directory: Path) -> list[Path]:
    out: list[Path] = []
    for ext in PRICE_EXT:
        out.extend(directory.glob(f"*{ext}"))
    return sorted(out, key=lambda p: p.stat().st_mtime, reverse=True)


def unique_name(directory: Path, filename: str) -> Path:
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = directory / filename
    n = 1
    while candidate.exists():
        candidate = directory / f"{stem} ({n}){suffix}"
        n += 1
    return candidate


def cleanup_old(directory: Path, keep: int = KEEP_VERSIONS) -> list[str]:
    removed = []
    for old in _price_files(directory)[keep:]:
        old.unlink()
        removed.append(old.name)
    return removed


def latest_price_file() -> Path | None:
    files = _price_files(INCOMING)
    return files[0] if files else None


def _zip_sane(path: Path) -> bool:
    """xlsx/ods — это zip; отсекаем zip-бомбы и пути с ../ до передачи парсеру."""
    try:
        with zipfile.ZipFile(path) as z:
            total = 0
            for i in z.infolist():
                if i.filename.startswith("/") or ".." in i.filename:
                    return False
                total += i.file_size
                if total > MAX_UNZIPPED_MB * 1024 * 1024:
                    return False
        return True
    except zipfile.BadZipFile:
        return False


# ── страницы /upload ─────────────────────────────────────────────────────────
_STYLE = """
 :root{--ink:#17191c;--paper:#f1f2f0;--line:#d7dad6;--spark:#ff5a1f;--navy:#150d5b;--muted:#5c6360}
 *{box-sizing:border-box}
 body{font-family:'Manrope',system-ui,sans-serif;background:var(--paper);color:var(--ink);max-width:600px;margin:0 auto;padding:0 20px}
 .plate{background:var(--navy);color:#fff;margin:0 -20px;padding:26px 20px 22px;text-align:center;position:relative}
 .plate .back{position:absolute;left:16px;top:50%;transform:translateY(-50%);color:#c9c8de;text-decoration:none;font-size:13px;white-space:nowrap}
 .plate .back:hover{color:#fff}
 @media (max-width:560px){.plate{padding-top:44px}.plate .back{top:14px;transform:none}}
 .plate b{font-size:20px;letter-spacing:.03em}
 .plate span{color:#c9c8de;font-size:13px;display:block;margin-top:4px}
 .card{background:#fff;border:1px solid var(--line);padding:26px;margin-top:26px}
 h1{font-size:20px;margin:0 0 14px}
 label{font-size:13px;font-weight:700;display:block;margin:12px 0 4px}
 input[type=text],input[type=password]{font-size:16px;padding:11px 13px;border:1px solid var(--line);width:100%;background:var(--paper);font-family:inherit}
 input:focus-visible{outline:3px solid var(--spark);border-color:var(--spark)}
 input[type=file]{margin:14px 0;display:block;width:100%}
 button{background:var(--spark);color:#fff;border:none;font-weight:700;padding:12px 22px;cursor:pointer;font-size:15px;margin-top:14px;font-family:inherit}
 button:hover{background:#e04a12}
 .msg{margin-top:12px;font-size:14px;white-space:pre-wrap;min-height:18px}
 .msg.err{color:#b3261e;font-weight:700;background:#fdecea;border:1px solid #f5c2bd;padding:10px 12px}
 .muted{color:var(--muted);font-size:13px}
 ul{font-size:13px;color:var(--muted);margin:10px 0 0 18px;padding:0}
 .out{display:flex;justify-content:space-between;align-items:center;margin-top:22px}
 .link,a.link{background:none;border:none;color:var(--muted);text-decoration:underline;cursor:pointer;font-size:13px;padding:0;margin:0;font-family:inherit}
"""

LOGIN_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>МЕТЭК Сочи — вход</title><style>{style}</style></head><body>
<div class="plate"><a class="back" href="/">← На сайт</a><b>МЕТЭК Сочи</b><span>служебный раздел — загрузка прайса</span></div>
<div class="card">
 <h1>Вход</h1>
 <form method="post" action="/upload/login" autocomplete="on">
  <label for="lg">Логин</label>
  <input type="text" id="lg" name="username" autocomplete="username" required autofocus maxlength="64">
  <label for="pw">Пароль</label>
  <input type="password" id="pw" name="password" autocomplete="current-password" required maxlength="128">
  <button type="submit">Войти</button>
  <p class="msg{err_cls}">{error}</p>
 </form>
 <p class="muted">Доступ только для сотрудников. Забыли пароль или потеряли телефон с кодами — обратитесь к администратору сайта.</p>
</div></body></html>"""

TOTP_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>МЕТЭК Сочи — подтверждение входа</title><style>{style}</style></head><body>
<div class="plate"><a class="back" href="/">← На сайт</a><b>МЕТЭК Сочи</b><span>подтверждение входа</span></div>
<div class="card">
 <h1>Введите код из приложения</h1>
 <p class="muted">Откройте Google Authenticator или Яндекс Ключ и введите 6-значный код. Он действует 30 секунд.</p>
 <form method="post" action="/upload/totp">
  <label for="tp">Код</label>
  <input type="text" id="tp" name="totp" inputmode="numeric" pattern="[0-9 ]*" autocomplete="one-time-code" required autofocus maxlength="7" placeholder="123 456">
  <button type="submit">Подтвердить</button>
  <p class="msg{err_cls}">{error}</p>
 </form>
 <form method="post" action="/upload/logout"><button class="link" type="submit">Отмена — вернуться ко входу</button></form>
</div></body></html>"""

UPLOAD_PAGE = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>МЕТЭК Сочи — загрузка прайса</title><style>{style}</style></head><body>
<div class="plate"><a class="back" href="/">← На сайт</a><b>МЕТЭК Сочи</b><span>загрузка прайса</span></div>
<div class="card">
 <h1>Загрузить новый прайс</h1>
 <p class="muted">Выберите таблицу с ценами (.xlsx или .ods) и нажмите «Загрузить». Колонка A — наименование, колонка B — цена, группы — строками без цифр.</p>
 <input type="file" id="f" accept=".xlsx,.ods">
 <button id="go">Загрузить прайс</button>
 <p class="msg" id="out" role="status"></p>
 <p class="muted">Хранятся 5 последних версий, старые удаляются автоматически. Одинаковые имена не перезаписываются — добавляется «(1)», «(2)». Цены на сайт публикуются из самого свежего файла.</p>
 <div id="hist"></div>
 <div class="out"><a class="link" href="/">На сайт</a>
 <button class="link" id="exit">Выйти</button></div>
</div>
<script nonce="{nonce}">
function esc(s){{return String(s).replace(/[&<>"']/g,function(c){{return{{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}}[c]}})}}
async function refresh(){{
  try{{
    const r = await fetch('/upload/list',{{credentials:'same-origin'}});
    if (r.status === 401) {{ location.reload(); return; }}
    const j = await r.json();
    document.getElementById('hist').innerHTML =
      j.files.length ? '<ul>' + j.files.map(f => '<li>' + esc(f) + '</li>').join('') + '</ul>'
                     : '<p class="muted">Файлов пока нет.</p>';
  }}catch(e){{}}
}}
document.getElementById('go').onclick = async () => {{
  const f = document.getElementById('f').files[0];
  const out = document.getElementById('out');
  out.className = 'msg';
  if (!f){{ out.textContent = 'Сначала выберите файл.'; out.className='msg err'; return; }}
  const fd = new FormData(); fd.append('file', f);
  out.textContent = 'Загружаем…';
  try {{
    const r = await fetch('/upload/file', {{method:'POST', body: fd, credentials:'same-origin'}});
    if (r.status === 401) {{ location.reload(); return; }}
    const j = await r.json();
    if (r.ok) out.textContent = j.message;
    else {{ out.textContent = (j.detail || ('Ошибка ' + r.status)); out.className='msg err'; }}
    refresh();
  }} catch(e){{ out.textContent = 'Сеть недоступна, попробуйте ещё раз.'; out.className='msg err'; }}
}};
document.getElementById('exit').onclick = async () => {{
  await fetch('/upload/logout', {{method:'POST', credentials:'same-origin'}}); location.reload();
}};
refresh();
</script></body></html>"""


def _html(page: str, nonce: str | None = None) -> HTMLResponse:
    csp = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
    if nonce:
        csp += f"; script-src 'nonce-{nonce}'; connect-src 'self'"
    return HTMLResponse(page, headers={"Content-Security-Policy": csp})


def _login_page(error: str = "", status: int = 200) -> HTMLResponse:
    resp = _html(LOGIN_PAGE.format(style=_STYLE, error=error, err_cls=" err" if error else ""))
    resp.status_code = status
    return resp


def _totp_page(error: str = "", status: int = 200) -> HTMLResponse:
    resp = _html(TOTP_PAGE.format(style=_STYLE, error=error, err_cls=" err" if error else ""))
    resp.status_code = status
    return resp


def _pending_valid(request: Request) -> str | None:
    tok = request.cookies.get(PENDING_COOKIE, "")
    with _sess_lock:
        exp = _pending.get(tok)
        if not exp or exp < time.time():
            _pending.pop(tok, None)
            return None
    return tok


@app.get("/upload", response_class=HTMLResponse)
async def upload_page(request: Request):
    if _session_valid(request):
        nonce = secrets.token_urlsafe(16)
        return _html(UPLOAD_PAGE.format(style=_STYLE, nonce=nonce), nonce)
    if ADMIN_TOTP_SECRET and _pending_valid(request):
        return _totp_page()
    return _login_page()


@app.post("/upload/login")
async def upload_login(request: Request, username: str = Form(...), password: str = Form(...)):
    """Шаг 1: логин + пароль. При включённом TOTP — выдаём короткий pending-cookie и экран кода."""
    _same_origin(request)
    ip = _client_ip(request)
    if login_throttle.blocked(ip) or login_throttle.blocked("user:" + username[:64]):
        return _login_page("Слишком много попыток. Подождите 15 минут.", 429)
    if not (ADMIN_USER and ADMIN_PASS_HASH):
        return _login_page("Вход не сконфигурирован (ADMIN_USER / ADMIN_PASS_HASH).", 503)

    user_ok = hmac.compare_digest(username.encode(), ADMIN_USER.encode())
    pass_ok = bcrypt.checkpw(password.encode()[:72], ADMIN_PASS_HASH.encode())
    if not (user_ok and pass_ok):
        login_throttle.hit(ip)
        login_throttle.hit("user:" + username[:64])
        log.warning("login failed (creds) from %s", ip)
        return _login_page("Неверный логин или пароль.", 401)

    if not ADMIN_TOTP_SECRET:
        resp = RedirectResponse("/upload", status_code=303)
        _new_session(resp, request)
        log.info("login ok (no totp) from %s", ip)
        return resp

    tok = secrets.token_urlsafe(32)
    now = time.time()
    with _sess_lock:
        for k in [k for k, e in _pending.items() if e < now]:
            _pending.pop(k, None)
        _pending[tok] = now + PENDING_TTL
    resp = RedirectResponse("/upload", status_code=303)
    resp.set_cookie(PENDING_COOKIE, tok, max_age=PENDING_TTL, httponly=True, samesite="strict",
                    secure=_is_https(request), path="/upload")
    return resp


@app.post("/upload/totp")
async def upload_totp(request: Request, totp: str = Form(...)):
    """Шаг 2: код из приложения. Только с валидным pending-cookie (пароль уже принят)."""
    _same_origin(request)
    ip = _client_ip(request)
    tok = _pending_valid(request)
    if not tok:
        return _login_page("Время на ввод кода вышло — войдите заново.", 401)
    if login_throttle.blocked(ip):
        return _totp_page("Слишком много попыток. Подождите 15 минут.", 429)
    if not _check_totp(totp):
        login_throttle.hit(ip)
        log.warning("login failed (totp) from %s", ip)
        return _totp_page("Неверный код. Проверьте время на телефоне и попробуйте ещё раз.", 401)

    with _sess_lock:
        _pending.pop(tok, None)
    resp = RedirectResponse("/upload", status_code=303)
    resp.delete_cookie(PENDING_COOKIE, path="/upload")
    _new_session(resp, request)
    log.info("login ok (totp) from %s", ip)
    return resp


@app.post("/upload/logout")
async def upload_logout(request: Request):
    _same_origin(request)
    tok = request.cookies.get(PENDING_COOKIE, "")
    with _sess_lock:
        _pending.pop(tok, None)
    # из формы (отмена на экране кода) — редирект на вход; из fetch — JSON
    wants_html = "text/html" in request.headers.get("accept", "")
    resp = RedirectResponse("/upload", status_code=303) if wants_html else JSONResponse({"ok": True})
    resp.delete_cookie(PENDING_COOKIE, path="/upload")
    _drop_session(request, resp)
    return resp


@app.get("/upload/list")
async def upload_list(request: Request):
    _require_session(request)
    files = _price_files(INCOMING)
    latest = latest_price_file()
    return {"files": [f.name + ("  — актуальный" if latest and f == latest else "") for f in files]}


@app.post("/upload/file")
async def upload_file(request: Request, file: UploadFile = File(...)):
    _same_origin(request)
    _require_session(request)
    raw_name = Path(file.filename or "price.xlsx").name
    if not raw_name.lower().endswith(PRICE_EXT):
        raise HTTPException(400, "Ожидается файл .xlsx или .ods")
    clean = SAFE_NAME_RE.sub("_", raw_name).strip() or "price.xlsx"

    # читаем кусками с жёстким лимитом — не держим гигабайты в памяти
    limit = MAX_UPLOAD_MB * 1024 * 1024
    chunks, size = [], 0
    while True:
        chunk = await file.read(256 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise HTTPException(413, f"Файл больше {MAX_UPLOAD_MB} МБ")
        chunks.append(chunk)
    blob = b"".join(chunks)
    if not blob.startswith(ZIP_MAGIC):
        raise HTTPException(400, "Файл не похож на таблицу xlsx/ods")

    dest = unique_name(INCOMING, clean)
    dest.write_bytes(blob)
    if not _zip_sane(dest):
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "Файл повреждён или подозрительно велик внутри. Цены на сайте не изменены.")

    try:
        data, warns = await asyncio.to_thread(parse_price_file, dest)
    except ImportFormatError as e:
        dest.unlink(missing_ok=True)
        log.warning("Импорт отклонён (%s): %s", raw_name, e)
        raise HTTPException(400, "Неверный формат — следите за форматированием: колонка A — наименование, "
                                 "колонка B — цена, группы строками без цифр. Цены на сайте не изменены.")

    # Sprint 1: публикация каталога в PostgreSQL — основная точка истины.
    # Одна транзакция: либо все новые товары, либо старые данные остаются целиком.
    def _commit_database():
        with Session(get_engine()) as db_session:
            with db_session.begin():
                replace_catalog(db_session, data)

    try:
        await asyncio.to_thread(_commit_database)
    except ValueError as e:
        dest.unlink(missing_ok=True)
        log.warning("Каталог не прошёл проверку: %s", e)
        raise HTTPException(400, "Некорректные данные каталога. Прайс не изменён.")
    except Exception:
        dest.unlink(missing_ok=True)
        log.exception("Ошибка сохранения прайса в PostgreSQL")
        raise HTTPException(503, "Не удалось обновить БД. Прайс не изменён.")

    # Совместимый JSON-снимок для старых интеграций, НЕ источник каталога.
    # БД уже обновлена: сбой снимка не отменяет успешный SQL-коммит.
    snapshot_warning = ""
    try:
        await asyncio.to_thread(publish, data, PRICES_JSON, BACKUPS)
    except Exception:
        log.exception("Каталог в PostgreSQL обновлён, но prices.json не записан")
        snapshot_warning = "\nВнимание: JSON-снимок не обновился, каталог в БД актуален."
    removed = cleanup_old(INCOMING)
    n_items = sum(len(g["items"]) for g in data["groups"])
    n_priced = sum(1 for g in data["groups"] for it in g["items"] if it["price"])
    log.info("Прайс опубликован из %s: %d поз., %d с ценой; удалено: %s; замечания: %s",
             dest.name, n_items, n_priced, removed or "нет", warns or "нет")
    warn_note = ("\nЗамечания: " + "; ".join(warns)) if warns else ""
    return JSONResponse({"message": f"Файл принят: {dest.name} ({len(blob)//1024} КБ).\n"
                                    f"Опубликовано на сайт: {len(data['groups'])} групп, {n_items} позиций "
                                    f"({n_priced} с ценой, остальные — «уточняйте у менеджера»).{warn_note}{snapshot_warning}"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    ico = SITE_DIR / "assets" / "favicon.ico"
    if ico.exists():
        return Response(ico.read_bytes(), media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})
    return Response(status_code=204)


@app.get("/healthz")
def healthz():
    # Проверяем живой SQL-коннект, а не только работающий uvicorn.
    try:
        with Session(get_engine()) as db_session:
            db_session.execute(text("SELECT 1"))
    except Exception:
        log.exception("Healthcheck: PostgreSQL недоступен")
        raise HTTPException(503, "Каталог: база данных недоступна")
    return {"ok": True, "database": "ok"}
