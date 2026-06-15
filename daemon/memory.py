import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "database.db"

def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                role TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notebook (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                topic TEXT NOT NULL,
                notes TEXT NOT NULL
            )
        """)
        conn.commit()

def save_message(role: str, content: str) -> None:
    if role not in {"user", "assistant", "system"}:
        raise ValueError("Invalid message role.")
    if not content.strip():
        raise ValueError("Cannot save empty message.")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO history (role, content) VALUES (?, ?)",
            (role, content)
        )
        conn.commit()

def save_note(topic: str, notes: str) -> None:
    if not topic.strip() or not notes.strip():
        raise ValueError("Topic and notes are required.")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notebook (topic, notes) VALUES (?, ?)",
            (topic, notes)
        )
        conn.commit()
