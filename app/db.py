import os
import sqlite3
from flask import g

BASE_DIR = os.path.dirname(__file__)
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
DB_PATH = os.path.join(INSTANCE_DIR, "app.db")


def get_db():
    if "db" not in g:
        os.makedirs(INSTANCE_DIR, exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        g.db = conn
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    schema = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT UNIQUE NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS questions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        question TEXT NOT NULL,
        choice_a TEXT NOT NULL,
        choice_b TEXT NOT NULL,
        choice_c TEXT NOT NULL,
        choice_d TEXT NOT NULL,
        correct TEXT NOT NULL,
        concept_tag TEXT NOT NULL,
        difficulty TEXT NOT NULL DEFAULT 'medium'
    );

    CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        weak_tags TEXT NOT NULL,
        duration_seconds INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS hall_of_fame (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT UNIQUE NOT NULL,
        best_score INTEGER NOT NULL,
        best_duration_seconds INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        difficulty TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS concept_videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        concept_tag TEXT NOT NULL,
        youtube_url TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS schedules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        note TEXT,
        include_weekends INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );
    """
    db.executescript(schema)
    # Add missing columns if needed (for existing DBs)
    cols = [row["name"] for row in db.execute("PRAGMA table_info(hall_of_fame)").fetchall()]
    if "difficulty" not in cols:
        db.execute("ALTER TABLE hall_of_fame ADD COLUMN difficulty TEXT NOT NULL DEFAULT ''")
    if "best_duration_seconds" not in cols:
        db.execute("ALTER TABLE hall_of_fame ADD COLUMN best_duration_seconds INTEGER NOT NULL DEFAULT 0")
    cols = [row["name"] for row in db.execute("PRAGMA table_info(attempts)").fetchall()]
    if "duration_seconds" not in cols:
        db.execute("ALTER TABLE attempts ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 0")
    cols = [row["name"] for row in db.execute("PRAGMA table_info(schedules)").fetchall()]
    if "include_weekends" not in cols:
        db.execute("ALTER TABLE schedules ADD COLUMN include_weekends INTEGER NOT NULL DEFAULT 0")
    db.commit()
