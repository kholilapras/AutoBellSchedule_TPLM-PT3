import os
import sqlite3
from utils import DB_FILE, HARI_ID

def connect_db():
    db_dir = os.path.dirname(DB_FILE) or "."
    os.makedirs(db_dir, exist_ok=True)

    old_path = os.path.abspath("bell_scheduler.db")
    if os.path.exists(old_path) and os.path.abspath(DB_FILE) != old_path and not os.path.exists(DB_FILE):
        try:
            os.replace(old_path, DB_FILE)
        except Exception:
            pass

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            time_str TEXT NOT NULL,
            days TEXT NOT NULL,
            sound_path TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );
    """)
    try:
        conn.execute("ALTER TABLE schedules ADD COLUMN active INTEGER NOT NULL DEFAULT 1;")
        conn.commit()
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
    except sqlite3.OperationalError:
        pass
    return conn

def parse_days_csv(s: str):
    s = (s or "").strip()
    return [int(x) for x in s.split(",") if x.strip().isdigit()] if s else []

def days_to_label(csv_text: str):
    idxs = parse_days_csv(csv_text)
    if len(idxs) == 7:
        return "Setiap hari"
    if not idxs:
        return "-"
    return ", ".join(HARI_ID[i] for i in idxs)
