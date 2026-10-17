"""本机管理账号和数据库备份；密码通过隐藏输入读取，避免出现在命令历史。"""
import argparse
import getpass
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from backend.auth import hash_password
from backend.database import initialize, connect


def read_password():
    password = getpass.getpass("Password (12-128 characters): ")
    if not 12 <= len(password) <= 128:
        raise ValueError("Password must contain 12-128 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise ValueError("Passwords do not match.")
    return hash_password(password)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create-user", "reset-password", "list-users", "backup"])
    parser.add_argument("value", nargs="?")
    args = parser.parse_args()
    initialize()
    if args.command == "backup":
        target = Path(args.value or "storage/backup.sqlite3")
        if target.exists():
            raise ValueError("Backup target exists. Choose a new filename.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with connect() as source, closing(sqlite3.connect(target)) as destination:
            with destination:
                source.backup(destination)
        print(f"Backup created: {target}")
        return
    with connect() as db:
        if args.command == "list-users":
            for row in db.execute("SELECT username,goal FROM users"):
                print(row["username"], row["goal"])
            return
        username = (args.value or "").lower()
        if not re.fullmatch(r"[a-z0-9_-]{3,32}", username):
            raise ValueError("Username: 3-32 letters, digits, underscore or dash.")
        if args.command == "create-user":
            if db.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone():
                raise ValueError("Username already exists.")
            db.execute("INSERT INTO users(username,password_hash) VALUES(?,?)", (username, read_password()))
        else:
            user = db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()
            if not user:
                raise ValueError("User not found.")
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (read_password(), user["id"]))
            db.execute("DELETE FROM sessions WHERE user_id=?", (user["id"],))
        print("Account updated.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, sqlite3.IntegrityError) as exc:
        raise SystemExit(str(exc))
