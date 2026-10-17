"""针对真实数据边界和多设备写入的回归检查；只操作临时数据库。"""
import io
import json
import os
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TEST_DIR = tempfile.TemporaryDirectory(prefix="wordgarden-tests-")
os.environ["WORD_DATA_DIR"] = TEST_DIR.name
os.environ["WORD_ORIGIN"] = "https://words.example.com"

from backend.database import initialize, connect
from backend.auth import hash_password, check_password
from backend.web import application
from backend.learning import CARDS, record_review, get_stats, get_progress


def call(path, method="GET", body=None, token="", csrf="", origin="https://words.example.com"):
    """通过 WSGI 边界请求，不跳过鉴权与输入校验。"""
    encoded = json.dumps(body).encode() if body is not None else b""
    environ = {"PATH_INFO": path, "REQUEST_METHOD": method, "wsgi.input": io.BytesIO(encoded),
               "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(encoded)),
               "HTTP_ORIGIN": origin, "HTTP_COOKIE": token, "HTTP_X_CSRF_TOKEN": csrf,
               "REMOTE_ADDR": "127.0.0.1"}
    result = {}

    def start_response(status, headers):
        result["status"] = int(status.split()[0])
        result["headers"] = dict(headers)

    raw = b"".join(application(environ, start_response))
    result["body"] = json.loads(raw) if raw and result["headers"]["Content-Type"].startswith("application/json") else raw
    return result


class ServiceTests(unittest.TestCase):
    def setUp(self):
        initialize()
        with connect() as db:
            for table in ("sessions", "events", "progress", "login_attempts", "users"):
                db.execute(f"DELETE FROM {table}")
            db.execute("INSERT INTO users(id,username,password_hash) VALUES(1,'learner',?)", (hash_password("temporary-test-password"),))
            db.execute("INSERT INTO users(id,username,password_hash) VALUES(2,'another',?)", (hash_password("another-test-password"),))

    def login(self, username="learner", password="temporary-test-password"):
        result = call("/api/login", "POST", {"username": username, "password": password})
        self.assertEqual(result["status"], 200, result)
        cookie = result["headers"]["Set-Cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        return cookie.split(";")[0], result["body"]["csrf"]

    def test_password_and_session_security(self):
        first = hash_password("a long test password")
        self.assertNotEqual(first, hash_password("a long test password"))
        self.assertTrue(check_password("a long test password", first))
        self.assertFalse(check_password("wrong", first))
        self.assertEqual(call("/api/state")["status"], 401)
        cookie, _ = self.login()
        self.assertEqual(call("/api/me", token=cookie)["body"]["username"], "learner")
        self.assertEqual(call("/api/login", "POST", {"username": "learner", "password": "wrong"})["status"], 401)

    def test_origin_csrf_and_input_validation(self):
        cookie, csrf = self.login()
        self.assertEqual(call("/api/settings", "POST", {"goal": 30}, token=cookie)["status"], 403)
        self.assertEqual(call("/api/settings", "POST", {"goal": 30}, token=cookie, csrf=csrf, origin="https://attacker.invalid")["status"], 403)
        self.assertEqual(call("/api/settings", "POST", {"goal": True}, token=cookie, csrf=csrf)["status"], 400)
        self.assertEqual(call("/api/settings", "POST", {"goal": 30}, token=cookie, csrf=csrf)["status"], 200)
        self.assertEqual(call("/api/me", token=cookie)["body"]["goal"], 30)
        self.assertEqual(call("/api/login", "POST", {"username": [], "password": 1})["status"], 400)

    def test_two_device_sync_idempotency_and_user_isolation(self):
        first_cookie, first_csrf = self.login()
        second_cookie, _ = self.login()
        other_cookie, _ = self.login("another", "another-test-password")
        event = {"cardId": next(iter(CARDS)), "rating": "good", "mode": "dictation", "eventId": "test-two-devices-123456"}
        self.assertEqual(call("/api/review", "POST", event, first_cookie, first_csrf)["status"], 200)
        retry = call("/api/review", "POST", event, first_cookie, first_csrf)
        self.assertTrue(retry["body"]["duplicate"])
        state = call("/api/state", token=second_cookie)["body"]
        self.assertEqual(state["stats"]["today"], 1)
        self.assertEqual(state["stats"]["reviews"], 1)
        self.assertIn(event["cardId"], state["progress"])
        self.assertEqual(call("/api/state", token=other_cookie)["body"]["progress"], {})

    def test_concurrent_events_do_not_lose_progress(self):
        card = next(iter(CARDS))
        with ThreadPoolExecutor(max_workers=4) as pool:
            events = [{"cardId": card, "rating": "good", "mode": "dictation", "eventId": f"concurrent-event-{n:03}"} for n in range(8)]
            list(pool.map(lambda event: record_review(1, event), events))
        self.assertEqual(get_progress(1)[card]["repetitions"], 8)
        self.assertEqual(get_stats(1)["reviews"], 8)
        self.assertEqual(get_stats(1)["today"], 1)

    def test_helped_answer_due_in_ten_minutes_and_no_false_mastery(self):
        card = next(iter(CARDS))
        now = time.time()
        record_review(1, {"cardId": card, "rating": "again", "mode": "dictation", "eventId": "helped-event-12345678"})
        item = get_progress(1)[card]
        self.assertTrue(now + 598 <= item["due"] <= now + 602)
        self.assertEqual(item["repetitions"], 0)
        self.assertEqual(get_stats(1)["mastered"], 0)
        self.assertEqual(get_stats(1)["daily"][0]["mistakes"], 1)

    def test_logout_and_password_change_revoke_sessions(self):
        first, csrf = self.login()
        second, _ = self.login()
        result = call("/api/password", "POST", {"oldPassword": "temporary-test-password", "newPassword": "changed-test-password"}, first, csrf)
        self.assertEqual(result["status"], 200)
        self.assertEqual(call("/api/state", token=second)["status"], 401)
        token, csrf = self.login(password="changed-test-password")
        self.assertEqual(call("/api/logout", "POST", {}, token, csrf)["status"], 200)
        self.assertEqual(call("/api/state", token=token)["status"], 401)

    def test_bad_login_limit_and_no_user_enumeration(self):
        for _ in range(10):
            self.assertEqual(call("/api/login", "POST", {"username": "missing-user", "password": "wrong"})["status"], 401)
        self.assertEqual(call("/api/login", "POST", {"username": "missing-user", "password": "wrong"})["status"], 429)

    def test_static_files_are_public_but_database_and_source_are_not(self):
        self.assertEqual(call("/")["status"], 200)
        self.assertEqual(call("/app.js")["headers"]["Content-Type"], "text/javascript")
        for path in ("/../backend/config.py", "/data/catalog.json", "/storage/wordgarden.sqlite3", "/docs/source-material.md"):
            self.assertEqual(call(path)["status"], 404, path)

    def test_material_and_translation_integrity(self):
        self.assertEqual(len(CARDS), 683)
        self.assertEqual(sum(card["kind"] == "sentence" for card in CARDS.values()), 243)
        root = Path(__file__).resolve().parents[1]
        translations = json.loads((root / "data" / "sentence-translations.json").read_text(encoding="utf-8"))
        self.assertEqual(len(translations), 175)
        for card_id, row in translations.items():
            self.assertEqual(CARDS[card_id]["en"], row["en"])
            self.assertEqual(CARDS[card_id]["zh"], row["zh"])
        self.assertFalse(any(card["zh"].startswith(("语境提示", "句型提示")) for card in CARDS.values() if card["kind"] == "sentence"))
        self.assertFalse(any("\ufffd" in card["en"] or not card["answer"].strip() for card in CARDS.values()))
        self.assertFalse(any("pass down forward" in card["answer"] for card in CARDS.values()))

    def test_every_vocabulary_card_has_a_sense_specific_grammar_label(self):
        vocabulary = [card for card in CARDS.values() if card["kind"] != "sentence"]
        self.assertEqual(len(vocabulary), 440)
        for card in vocabulary:
            self.assertTrue(card["pos"], card["en"])
            self.assertTrue(card["posLabel"], card["en"])
            self.assertTrue(card["promptMeaning"], card["en"])
            if card["kind"] == "word":
                self.assertIn(card["pos"], ("n.", "v.", "adj.", "adv."), card["en"])
                self.assertTrue(card["promptContext"], card["en"])
        root = Path(__file__).resolve().parents[1]
        metadata = json.loads((root / "public" / "assets" / "grammar.json").read_text(encoding="utf-8"))
        for card in CARDS.values():
            self.assertEqual(metadata[card["id"]]["pos"], card["pos"])
            self.assertEqual(metadata[card["id"]]["promptMeaning"], card["promptMeaning"])


if __name__ == "__main__":
    unittest.main()
