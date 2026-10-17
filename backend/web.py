"""WSGI 请求边界：明确路由、同源与 CSRF 校验、限制请求体、静态路径白名单。"""
import hmac
import json
import logging
import mimetypes
import time
from pathlib import Path
from . import auth, learning
from .config import ORIGIN, PUBLIC_DIR
from .database import connect

SECURITY_HEADERS = [
    ("X-Content-Type-Options", "nosniff"),
    ("Referrer-Policy", "same-origin"),
    ("X-Frame-Options", "DENY"),
    ("Content-Security-Policy", "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"),
]


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def read_json(environ):
    if not environ.get("CONTENT_TYPE", "").startswith("application/json"):
        raise ApiError(415, "请求需要使用 JSON。")
    try:
        size = int(environ.get("CONTENT_LENGTH", "0") or 0)
    except ValueError:
        raise ApiError(400, "无效请求长度。")
    if not 0 < size <= 16384:
        raise ApiError(413, "请求内容过大或为空。")
    try:
        data = json.loads(environ["wsgi.input"].read(size))
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, UnicodeDecodeError):
        raise ApiError(400, "请求格式不正确。")


def require_session(environ):
    session = auth.get_session(environ)
    if not session:
        raise ApiError(401, "请先登录，学习进度会保存在你的账号中。")
    return session


def require_write(environ, session=None):
    """浏览器写入必须来自部署域名；登录也校验 Origin 防登录 CSRF。"""
    if environ.get("HTTP_ORIGIN") != ORIGIN:
        raise ApiError(403, "请求来源不匹配，请用配置的正式地址访问。")
    if session and not hmac.compare_digest(environ.get("HTTP_X_CSRF_TOKEN", ""), session["csrf"]):
        raise ApiError(403, "会话校验失败，请刷新后重试。")


def route_api(environ):
    path, method = environ["PATH_INFO"], environ["REQUEST_METHOD"]
    if path == "/api/health" and method == "GET":
        with connect() as db:
            db.execute("SELECT 1").fetchone()
        return {"status": "ok"}, []
    if path == "/api/catalog" and method == "GET":
        return learning.CATALOG, []
    if path == "/api/login" and method == "POST":
        require_write(environ)
        body = read_json(environ)
        username, password = body.get("username"), body.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or len(username) > 32 or len(password) > 256:
            raise ApiError(400, "账号或密码格式不正确。")
        # Nginx 必须覆盖 X-Real-IP；生产容器端口仅绑定在宿主机回环地址。
        ip = environ.get("HTTP_X_REAL_IP") or environ.get("REMOTE_ADDR", "unknown")
        result, error, status = auth.login(username.strip(), password, ip)
        if not result:
            raise ApiError(status, error)
        return {k: v for k, v in result.items() if k != "token"}, [("Set-Cookie", auth.cookie(result["token"]))]
    session = require_session(environ)
    if method == "POST":
        require_write(environ, session)
    if path == "/api/me" and method == "GET":
        return {"username": session["username"], "goal": session["goal"], "csrf": session["csrf"]}, []
    if path == "/api/state" and method == "GET":
        return {"progress": learning.get_progress(session["user_id"]), "stats": learning.get_stats(session["user_id"])}, []
    if path == "/api/review" and method == "POST":
        try:
            result = learning.record_review(session["user_id"], read_json(environ))
            return result, []
        except ValueError as exc:
            raise ApiError(400, str(exc))
    if path == "/api/settings" and method == "POST":
        goal = read_json(environ).get("goal")
        if type(goal) is not int or not 5 <= goal <= 200:
            raise ApiError(400, "每日目标请设为 5 至 200。")
        with connect() as db:
            db.execute("UPDATE users SET goal=? WHERE id=?", (goal, session["user_id"]))
        return {"goal": goal}, []
    if path == "/api/password" and method == "POST":
        body = read_json(environ)
        old, new = body.get("oldPassword"), body.get("newPassword")
        if not isinstance(old, str) or not isinstance(new, str) or not 12 <= len(new) <= 128 or len(old) > 256:
            raise ApiError(400, "新密码需要 12 至 128 个字符。")
        with connect() as db:
            user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
            if not auth.check_password(old, user["password_hash"]):
                raise ApiError(400, "当前密码不正确。")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (auth.hash_password(new), user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        return {"ok": True}, [("Set-Cookie", auth.cookie("", clear=True))]
    if path == "/api/logout" and method == "POST":
        with connect() as db:
            db.execute("DELETE FROM sessions WHERE token_hash=?", (session["token_hash"],))
        return {"ok": True}, [("Set-Cookie", auth.cookie("", clear=True))]
    if path == "/api/export" and method == "GET":
        with connect() as db:
            events = [dict(r) for r in db.execute("SELECT id,card_id,rating,mode,created,day FROM events WHERE user_id=? ORDER BY created", (session["user_id"],))]
        return {"version": 1, "username": session["username"], "exportedAt": int(time.time()),
                "progress": learning.get_progress(session["user_id"]), "events": events}, [("Content-Disposition", 'attachment; filename="wordgarden-progress.json"')]
    raise ApiError(404, "没有这个接口。")


def static_response(path):
    """只公开 public；源码、数据库和文档不能通过 URL 读取。"""
    relative = "index.html" if path == "/" else path.lstrip("/")
    target = (PUBLIC_DIR / relative).resolve()
    if not target.is_relative_to(PUBLIC_DIR.resolve()) or not target.is_file():
        raise ApiError(404, "页面不存在。")
    content_type = {".js": "text/javascript", ".css": "text/css", ".html": "text/html"}.get(target.suffix)
    content_type = content_type or mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return target.read_bytes(), [("Content-Type", content_type), ("Cache-Control", "no-cache")]


def application(environ, start_response):
    status, headers = 200, []
    try:
        if environ["PATH_INFO"].startswith("/api/"):
            data, headers = route_api(environ)
            payload = json.dumps(data, ensure_ascii=False).encode()
            headers += [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
        elif environ["REQUEST_METHOD"] in ("GET", "HEAD"):
            payload, headers = static_response(environ["PATH_INFO"])
        else:
            raise ApiError(405, "请求方法不支持。")
    except ApiError as exc:
        status, payload = exc.status, json.dumps({"error": exc.message}, ensure_ascii=False).encode()
        headers = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
    except Exception:
        logging.exception("Request failed")
        status, payload = 500, b'{"error":"Server error. Please retry."}'
        headers = [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
    from http import HTTPStatus
    start_response(f"{status} {HTTPStatus(status).phrase}", headers + SECURITY_HEADERS + [("Content-Length", str(len(payload)))])
    return [b"" if environ["REQUEST_METHOD"] == "HEAD" else payload]
