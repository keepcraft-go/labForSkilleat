import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

from app.db import get_db, init_db
from app.main import create_app

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
QUESTIONS_PATH = os.path.join(BASE_DIR, "data", "seed_questions.json")
VIDEOS_PATH = os.path.join(BASE_DIR, "data", "seed_videos.json")


def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def seed_questions(db):
    count = db.execute("SELECT COUNT(*) AS count FROM questions").fetchone()["count"]
    if count > 0:
        return

    questions = load_json(QUESTIONS_PATH)
    for q in questions:
        db.execute(
            """
            INSERT INTO questions (topic, question, choice_a, choice_b, choice_c, choice_d, correct, concept_tag, difficulty)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                q["topic"],
                q["question"],
                q["choice_a"],
                q["choice_b"],
                q["choice_c"],
                q["choice_d"],
                q["correct"],
                q["concept_tag"],
                q.get("difficulty", "medium"),
            ),
        )


def seed_videos(db):
    count = db.execute("SELECT COUNT(*) AS count FROM concept_videos").fetchone()["count"]
    if count > 0:
        return

    videos = load_json(VIDEOS_PATH)
    for v in videos:
        db.execute(
            "INSERT INTO concept_videos (concept_tag, youtube_url) VALUES (?, ?)",
            (v["concept_tag"], v["youtube_url"]),
        )


def main():
    app = create_app()
    with app.app_context():
        init_db()
        db = get_db()
        seed_questions(db)
        seed_videos(db)
        db.commit()


if __name__ == "__main__":
    main()
