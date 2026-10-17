"""集中配置；只读取进程变量，绝不读取 .env 文件。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("WORD_DATA_DIR", str(ROOT / "storage")))
DB_PATH = DATA_DIR / "wordgarden.sqlite3"
PUBLIC_DIR = ROOT / "public"
ORIGIN = os.environ.get("WORD_ORIGIN", "http://localhost:8765").rstrip("/")
SECURE = ORIGIN.startswith("https://")
SESSION_SECONDS = 60 * 60 * 24 * 14
