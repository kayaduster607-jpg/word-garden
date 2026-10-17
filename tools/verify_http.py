"""在临时数据库上启动真实 Waitress，核验两个浏览器会话、重启持久化和在线备份。"""
import http.cookiejar
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "http://localhost:8766"


def browser():
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(client, path, body=None, csrf=""):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Origin": BASE, "X-CSRF-Token": csrf}
    if data:
        headers["Content-Type"] = "application/json"
    with client.open(urllib.request.Request(BASE + path, data=data, headers=headers), timeout=5) as response:
        raw = response.read()
        return json.loads(raw) if response.headers["Content-Type"].startswith("application/json") else raw


def start_server():
    process = subprocess.Popen([sys.executable, "serve.py", "--port", "8766"], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError(process.stderr.read().decode(errors="replace"))
        try:
            request(browser(), "/api/health")
            return process
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.1)
    process.terminate()
    raise RuntimeError("HTTP test server did not become ready")


def stop_server(process):
    process.terminate()
    process.wait(timeout=10)
    process.stderr.close()


def main():
    with tempfile.TemporaryDirectory(prefix="wordgarden-http-") as storage:
        os.environ["WORD_DATA_DIR"] = storage
        os.environ["WORD_ORIGIN"] = BASE
        from backend.database import initialize, connect
        from backend.auth import hash_password
        initialize()
        with connect() as db:
            db.execute("INSERT INTO users(username,password_hash) VALUES('http-test',?)", (hash_password("only-for-local-test"),))
        first, second = browser(), browser()
        process = start_server()
        try:
            assert b"Word Garden" in request(first, "/")
            for path in ("/app.js", "/typing.js", "/styles.css", "/assets/ginkgo.webp"):
                assert len(request(first, path)) > 100
            login1 = request(first, "/api/login", {"username": "http-test", "password": "only-for-local-test"})
            # 真实 HTTP 登录后必须能保存会话，而不是发出浏览器无法回传的 Secure Cookie。
            cookies = next(handler.cookiejar for handler in first.handlers if isinstance(handler, urllib.request.HTTPCookieProcessor))
            assert any(cookie.name == "word_session" and not cookie.secure for cookie in cookies)
            request(second, "/api/login", {"username": "http-test", "password": "only-for-local-test"})
            card = request(first, "/api/catalog")["cards"][0]
            event = {"cardId": card["id"], "rating": "good", "mode": "dictation", "eventId": "real-http-event-123456"}
            request(first, "/api/review", event, login1["csrf"])
            assert request(first, "/api/review", event, login1["csrf"])["duplicate"]
            assert request(second, "/api/state")["stats"]["reviews"] == 1
        finally:
            stop_server(process)
        # 重启服务后，账号会话和学习记录应继续有效。
        process = start_server()
        try:
            assert request(second, "/api/state")["stats"]["today"] == 1
            backup = Path(storage) / "verified-backup.sqlite3"
            subprocess.run([sys.executable, "manage.py", "backup", str(backup)], cwd=ROOT, check=True, capture_output=True)
            with closing(sqlite3.connect(backup)) as db:
                assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1
            exported = request(second, "/api/export")
            assert len(exported["events"]) == 1
            print("PASS: real HTTP login, two-device sync, duplicate retry, restart persistence, export and backup integrity")
        finally:
            stop_server(process)


if __name__ == "__main__":
    main()
