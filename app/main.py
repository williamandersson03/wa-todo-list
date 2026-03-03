from __future__ import annotations

import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.db import get_db, init_db
from app.parser import parse_multiline
from app.security import LoginRateLimiter, hash_password, new_token, verify_password

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = FastAPI(title="WA TODO")
base_dir = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(base_dir / "templates"))
app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
settings = get_settings()
local_tz = ZoneInfo(settings.app_timezone)
rate_limiter = LoginRateLimiter(settings.login_rate_limit_attempts, settings.login_rate_limit_window_seconds)


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_local_timestamp(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
        dt = dt.replace(tzinfo=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")




def normalize_todo_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", value.strip())
    if not cleaned:
        return "Untitled task"
    return cleaned[:1].upper() + cleaned[1:]


def set_session_cookie(response: HTMLResponse | RedirectResponse, sid: str) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        sid,
        httponly=True,
        samesite=settings.session_same_site,
        secure=settings.session_secure_cookie,
        max_age=settings.session_max_age_seconds,
        path="/",
    )


def get_or_create_session(request: Request, conn: sqlite3.Connection) -> tuple[sqlite3.Row, str]:
    sid = request.cookies.get(settings.session_cookie_name)
    session = None
    if sid:
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()

    if not session:
        sid = new_token(24)
        conn.execute(
            "INSERT INTO sessions (id, csrf_token, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
            (sid, new_token(24), utc_now_iso(), utc_now_iso()),
        )
        conn.commit()
        session = conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()

    conn.execute("UPDATE sessions SET last_seen_at = ? WHERE id = ?", (utc_now_iso(), sid))
    conn.commit()
    return session, sid


def require_csrf(session: sqlite3.Row, csrf_token: str) -> None:
    if not csrf_token or csrf_token != session["csrf_token"]:
        raise ValueError("Invalid CSRF token")


def current_user(session: sqlite3.Row, conn: sqlite3.Connection) -> sqlite3.Row | None:
    if not session["user_id"]:
        return None
    return conn.execute("SELECT id, email FROM users WHERE id = ?", (session["user_id"],)).fetchone()


def render(request: Request, template_name: str, context: dict, conn: sqlite3.Connection, status_code: int = 200):
    session, sid = get_or_create_session(request, conn)
    response = templates.TemplateResponse(
        template_name,
        {
            "request": request,
            **context,
            "csrf_token": session["csrf_token"],
            "is_authenticated": bool(session["user_id"]),
            "format_local_timestamp": format_local_timestamp,
        },
        status_code=status_code,
    )
    set_session_cookie(response, sid)
    return response


def redirect(url: str, request: Request, conn: sqlite3.Connection, status_code: int = status.HTTP_303_SEE_OTHER):
    _session, sid = get_or_create_session(request, conn)
    response = RedirectResponse(url=url, status_code=status_code)
    set_session_cookie(response, sid)
    return response


def auth_user(request: Request, conn: sqlite3.Connection) -> tuple[sqlite3.Row, sqlite3.Row]:
    session, _ = get_or_create_session(request, conn)
    user = current_user(session, conn)
    if not user:
        raise PermissionError
    return user, session


def get_client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "unknown"))


@app.get("/", response_class=HTMLResponse)
def landing(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    session, _ = get_or_create_session(request, conn)
    if session["user_id"]:
        return redirect("/app", request, conn)
    return render(request, "landing.html", {"title": "Welcome"}, conn)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    return render(request, "login.html", {"title": "Login", "error": None}, conn)


@app.post("/login")
def login_action(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    session, _ = get_or_create_session(request, conn)
    try:
        require_csrf(session, csrf_token)
    except ValueError:
        return render(request, "login.html", {"title": "Login", "error": "Invalid security token."}, conn, status_code=400)

    normalized_email = email.strip().lower()
    limiter_key = f"{get_client_ip(request)}:{normalized_email}"
    if rate_limiter.is_blocked(limiter_key):
        return render(request, "login.html", {"title": "Login", "error": "Too many failed attempts. Try again later."}, conn, status_code=429)

    user = conn.execute("SELECT * FROM users WHERE email = ?", (normalized_email,)).fetchone()
    if not user or not verify_password(user["password_hash"], password):
        rate_limiter.add_failure(limiter_key)
        return render(request, "login.html", {"title": "Login", "error": "Invalid email or password."}, conn, status_code=400)

    rate_limiter.clear(limiter_key)
    conn.execute("UPDATE sessions SET user_id = ? WHERE id = ?", (user["id"], session["id"]))
    conn.commit()
    return redirect("/app", request, conn)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    return render(request, "register.html", {"title": "Register", "error": None}, conn)


@app.post("/register")
def register_action(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    session, _ = get_or_create_session(request, conn)
    try:
        require_csrf(session, csrf_token)
    except ValueError:
        return render(request, "register.html", {"title": "Register", "error": "Invalid security token."}, conn, status_code=400)

    normalized_email = email.strip().lower()
    if not EMAIL_RE.match(normalized_email):
        return render(request, "register.html", {"title": "Register", "error": "Please provide a valid email."}, conn, status_code=400)
    if len(password) < 10:
        return render(request, "register.html", {"title": "Register", "error": "Password must be at least 10 characters."}, conn, status_code=400)

    try:
        conn.execute("INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)", (normalized_email, hash_password(password), utc_now_iso()))
        conn.commit()
    except sqlite3.IntegrityError:
        return render(request, "register.html", {"title": "Register", "error": "Email is already registered."}, conn, status_code=400)

    user = conn.execute("SELECT id FROM users WHERE email = ?", (normalized_email,)).fetchone()
    conn.execute("UPDATE sessions SET user_id = ? WHERE id = ?", (user["id"], session["id"]))
    conn.commit()
    return redirect("/app", request, conn)


@app.post("/logout")
def logout_action(request: Request, csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    session, _ = get_or_create_session(request, conn)
    try:
        require_csrf(session, csrf_token)
    except ValueError:
        return render(request, "landing.html", {"title": "Welcome", "error": "Invalid security token."}, conn, status_code=400)
    conn.execute("UPDATE sessions SET user_id = NULL WHERE id = ?", (session["id"],))
    conn.commit()
    return redirect("/", request, conn)


@app.get("/app", response_class=HTMLResponse)
def app_page(request: Request, conn: sqlite3.Connection = Depends(get_db)):
    try:
        user, _session = auth_user(request, conn)
    except PermissionError:
        return redirect("/login", request, conn)

    rows = conn.execute(
        "SELECT id, category_key, text, created_at, completed_at FROM todos WHERE user_id = ? ORDER BY datetime(created_at) DESC, id DESC",
        (user["id"],),
    ).fetchall()
    grouped = defaultdict(list)
    latest = {}
    for row in rows:
        grouped[row["category_key"]].append(row)
        latest.setdefault(row["category_key"], row["created_at"])
    categories = sorted(grouped.keys(), key=lambda key: latest[key], reverse=True)
    return render(
        request,
        "app.html",
        {
            "title": "My TODOs",
            "hero_subtitle": "A simple way to track your work",
            "category_help": "Use P###, K###, M###### or §Category to group tasks automatically.",
            "user": user,
            "categories": categories,
            "todos": grouped,
            "error": request.query_params.get("error"),
        },
        conn,
    )


@app.post("/todo/add")
def todo_add(request: Request, content: str = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    try:
        user, session = auth_user(request, conn)
        require_csrf(session, csrf_token)
    except (PermissionError, ValueError):
        return redirect("/login", request, conn)

    for item in parse_multiline(content, settings.category_max_length):
        conn.execute(
            "INSERT INTO todos (user_id, category_key, category_type, text, created_at) VALUES (?, ?, ?, ?, ?)",
            (user["id"], item.category_key, item.category_type, item.text[: settings.todo_max_length], utc_now_iso()),
        )
    conn.commit()
    return redirect("/app", request, conn)


@app.post("/todo/toggle")
def todo_toggle(request: Request, todo_id: int = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    try:
        user, session = auth_user(request, conn)
        require_csrf(session, csrf_token)
    except (PermissionError, ValueError):
        return redirect("/login", request, conn)

    todo = conn.execute("SELECT id, user_id, completed_at FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if not todo or todo["user_id"] != user["id"]:
        return redirect("/app?error=Item+not+found", request, conn)

    completed_at = None if todo["completed_at"] else utc_now_iso()
    conn.execute("UPDATE todos SET completed_at = ? WHERE id = ?", (completed_at, todo_id))
    conn.commit()
    return redirect("/app", request, conn)


@app.post("/todo/delete")
def todo_delete(request: Request, todo_id: int = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    try:
        user, session = auth_user(request, conn)
        require_csrf(session, csrf_token)
    except (PermissionError, ValueError):
        return redirect("/login", request, conn)

    todo = conn.execute("SELECT id, user_id, completed_at FROM todos WHERE id = ?", (todo_id,)).fetchone()
    if not todo or todo["user_id"] != user["id"]:
        return redirect("/app?error=Item+not+found", request, conn)
    if not todo["completed_at"]:
        return redirect("/app?error=Only+completed+items+can+be+deleted", request, conn)

    conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    conn.commit()
    return redirect("/app", request, conn)


@app.post("/todo/clear_done")
def clear_done(request: Request, category_key: str = Form(...), csrf_token: str = Form(...), conn: sqlite3.Connection = Depends(get_db)):
    try:
        user, session = auth_user(request, conn)
        require_csrf(session, csrf_token)
    except (PermissionError, ValueError):
        return redirect("/login", request, conn)

    conn.execute("DELETE FROM todos WHERE user_id = ? AND category_key = ? AND completed_at IS NOT NULL", (user["id"], category_key))
    conn.commit()
    return redirect("/app", request, conn)


@app.post("/todo/add_to_category")
def todo_add_to_category(
    request: Request,
    category_key: str = Form(...),
    text: str = Form(...),
    csrf_token: str = Form(...),
    conn: sqlite3.Connection = Depends(get_db),
):
    try:
        user, session = auth_user(request, conn)
        require_csrf(session, csrf_token)
    except (PermissionError, ValueError):
        return redirect("/login", request, conn)

    clean_category = category_key.strip()[: settings.category_max_length]
    if not clean_category:
        return redirect("/app?error=Category+is+required", request, conn)

    normalized_text = normalize_todo_text(text)[: settings.todo_max_length]

    existing = conn.execute(
        "SELECT category_type FROM todos WHERE user_id = ? AND category_key = ? ORDER BY datetime(created_at) DESC LIMIT 1",
        (user["id"], clean_category),
    ).fetchone()
    category_type = existing["category_type"] if existing else ("GENERAL" if clean_category == "GENERAL" else "CUSTOM")

    conn.execute(
        "INSERT INTO todos (user_id, category_key, category_type, text, created_at) VALUES (?, ?, ?, ?, ?)",
        (user["id"], clean_category, category_type, normalized_text, utc_now_iso()),
    )
    conn.commit()
    return redirect("/app", request, conn)
