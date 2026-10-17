"""密码派生、会话与登录节流；数据库不保存明文密码和会话 cookie。"""
import hashlib
import hmac
import secrets
import time
from http.cookies import SimpleCookie
from .config import SESSION_SECONDS, SECURE
from .database import connect


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1)
    return "scrypt$" + salt + "$" + digest.hex()


def check_password(password, stored):
    try:
        _, salt, _ = stored.split("$")
        return hmac.compare_digest(hash_password(password, salt), stored)
    except (ValueError, TypeError):
        return False


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def cookie(token, clear=False):
    value = f"word_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={0 if clear else SESSION_SECONDS}"
    return value + ("; Secure" if SECURE else "")


def get_session(environ):
    jar = SimpleCookie()
    try:
        jar.load(environ.get("HTTP_COOKIE", ""))
        token = jar["word_session"].value
    except (KeyError, ValueError):
        return None
    with connect() as db:
        row = db.execute("SELECT s.*,u.username,u.goal FROM sessions s JOIN users u ON u.id=s.user_id WHERE token_hash=? AND expires>?",
                         (token_hash(token), int(time.time()))).fetchone()
    return dict(row) if row else None


def login(username, password, ip):
    """同一账号或同一来源均限速；成功登录清理该账号失败计数。"""
    now = int(time.time())
    buckets = ["ip:" + ip, "user:" + username.lower()]
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("DELETE FROM login_attempts WHERE created<?", (now - 900,))
        for bucket in buckets:
            count = db.execute("SELECT COUNT(*) FROM login_attempts WHERE bucket=?", (bucket,)).fetchone()[0]
            if count >= (30 if bucket.startswith("ip:") else 10):
                return None, "尝试次数过多，请在 15 分钟后重试。", 429
        user = db.execute("SELECT * FROM users WHERE username=?", (username.lower(),)).fetchone()
        # 即使账号不存在也执行相同的密码派生，减少账号枚举信息。
        dummy = "scrypt$" + "0" * 32 + "$" + "0" * 128
        valid = check_password(password, user["password_hash"] if user else dummy)
        if not user or not valid:
            db.executemany("INSERT INTO login_attempts VALUES(?,?)", [(b, now) for b in buckets])
            return None, "账号或密码不正确。", 401
        db.execute("DELETE FROM login_attempts WHERE bucket=?", (buckets[1],))
        db.execute("DELETE FROM sessions WHERE expires<=?", (now,))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        db.execute("INSERT INTO sessions VALUES(?,?,?,?)", (token_hash(token), user["id"], csrf, now + SESSION_SECONDS))
    return {"token": token, "csrf": csrf, "username": user["username"], "goal": user["goal"]}, "", 200
