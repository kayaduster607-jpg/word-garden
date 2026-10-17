"""每次请求独立连接；SQLite 事务保证两台设备同时提交时不会覆盖整份进度。"""
import sqlite3
from contextlib import contextmanager
from .config import DATA_DIR, DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
 id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, goal INTEGER NOT NULL DEFAULT 20
);
CREATE TABLE IF NOT EXISTS sessions (
 token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 csrf TEXT NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS progress (
 user_id INTEGER NOT NULL REFERENCES users(id), card_id TEXT NOT NULL,
 repetitions INTEGER NOT NULL DEFAULT 0, interval_days INTEGER NOT NULL DEFAULT 0,
 due INTEGER NOT NULL, lapses INTEGER NOT NULL DEFAULT 0,
 updated INTEGER NOT NULL, PRIMARY KEY(user_id, card_id)
);
CREATE TABLE IF NOT EXISTS events (
 id TEXT NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
 card_id TEXT NOT NULL, rating TEXT NOT NULL, mode TEXT NOT NULL,
 created INTEGER NOT NULL, day TEXT NOT NULL,
 PRIMARY KEY(user_id, id)
);
CREATE INDEX IF NOT EXISTS events_user_day ON events(user_id, day);
CREATE TABLE IF NOT EXISTS login_attempts (
 bucket TEXT NOT NULL, created INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS attempts_bucket ON login_attempts(bucket, created);
"""


@contextmanager
def connect():
    """连接超时允许短暂等待另一个设备完成写入。"""
    db = sqlite3.connect(DB_PATH, timeout=10)
    try:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        # sqlite3 自带的 with 只提交/回滚，不会关闭连接，因此在外层显式关闭。
        with db:
            yield db
    finally:
        db.close()


def initialize():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript(SCHEMA)
