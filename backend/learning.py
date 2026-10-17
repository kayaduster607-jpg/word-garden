"""可解释的间隔复习：遗忘 10 分钟、模糊 1 天、记住逐步拉长；不是考试评分。"""
import json
import time
from datetime import datetime, timedelta, timezone
from .config import ROOT
from .database import connect

CATALOG = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))
CARDS = {card["id"]: card for card in CATALOG["cards"]}
SHANGHAI = timezone(timedelta(hours=8))


def day_at(timestamp):
    return datetime.fromtimestamp(timestamp, SHANGHAI).date().isoformat()


def get_progress(user_id):
    with connect() as db:
        rows = db.execute("SELECT * FROM progress WHERE user_id=?", (user_id,)).fetchall()
    return {r["card_id"]: {k: r[k] for k in r.keys() if k != "user_id"} for r in rows}


def get_stats(user_id):
    now = int(time.time())
    today = day_at(now)
    with connect() as db:
        daily = [dict(r) for r in db.execute("SELECT day,COUNT(*) AS reviews,COUNT(DISTINCT card_id) AS cards,SUM(CASE WHEN rating='again' THEN 1 ELSE 0 END) AS mistakes FROM events WHERE user_id=? GROUP BY day ORDER BY day DESC LIMIT 366", (user_id,))]
    days = {d["day"] for d in daily}
    cursor = datetime.fromtimestamp(now, SHANGHAI).date()
    if today not in days:
        cursor -= timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    p = get_progress(user_id)
    current = next((r for r in daily if r["day"] == today), {})
    return {"today": current.get("cards", 0), "reviews": current.get("reviews", 0),
            "due": sum(r["due"] <= now for r in p.values()),
            "mastered": sum(r["repetitions"] >= 3 and r["interval_days"] >= 7 for r in p.values()),
            "learned": len(p), "streak": streak, "daily": daily,
            "total": len(CARDS), "serverTime": now}


def record_review(user_id, payload):
    """事件 UUID 保证网络重试只计一次；短事务串行处理每个卡片的更新。"""
    card_id, rating = payload.get("cardId"), payload.get("rating")
    event_id, mode = payload.get("eventId", ""), payload.get("mode", "recall")
    if card_id not in CARDS or rating not in ("again", "hard", "good"):
        raise ValueError("无效的卡片或评分。")
    if not isinstance(event_id, str) or not 16 <= len(event_id) <= 100 or mode not in ("recall", "copy", "dictation"):
        raise ValueError("无效的练习事件。")
    now = int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT card_id,rating,mode FROM events WHERE user_id=? AND id=?", (user_id, event_id)).fetchone()
        if prior:
            if (prior["card_id"], prior["rating"], prior["mode"]) != (card_id, rating, mode):
                raise ValueError("重复事件内容不一致。")
            return {"duplicate": True}
        row = db.execute("SELECT * FROM progress WHERE user_id=? AND card_id=?", (user_id, card_id)).fetchone()
        repetitions = row["repetitions"] if row else 0
        interval = row["interval_days"] if row else 0
        lapses = row["lapses"] if row else 0
        if rating == "again":
            repetitions, interval, due, lapses = 0, 0, now + 600, lapses + 1
        elif rating == "hard":
            interval, due = 1, now + 86400
        else:
            repetitions += 1
            interval = 1 if repetitions == 1 else 3 if repetitions == 2 else max(7, min(180, interval * 2))
            due = now + interval * 86400
        db.execute("INSERT INTO progress VALUES(?,?,?,?,?,?,?) ON CONFLICT(user_id,card_id) DO UPDATE SET repetitions=excluded.repetitions,interval_days=excluded.interval_days,due=excluded.due,lapses=excluded.lapses,updated=excluded.updated",
                   (user_id, card_id, repetitions, interval, due, lapses, now))
        db.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)", (event_id, user_id, card_id, rating, mode, now, day_at(now)))
    return {"duplicate": False, "due": due}
