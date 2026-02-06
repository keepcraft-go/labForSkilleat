import random
from urllib.parse import urlparse, parse_qs
from datetime import datetime
from flask import Blueprint, redirect, render_template, request, session, url_for

from ..db import get_db
from ..services import analysis, scoring

quiz_bp = Blueprint("quiz", __name__)


@quiz_bp.get("/")
def index():
    db = get_db()
    rows = db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic").fetchall()
    topics = [row["topic"] for row in rows]
    return render_template("index.html", topics=topics)


@quiz_bp.post("/start")
def start():
    nickname = request.form.get("nickname", "").strip()
    topic = request.form.get("topic", "all").strip()
    difficulty = request.form.get("difficulty", "easy").strip()

    if not nickname:
        return redirect(url_for("quiz.index"))

    db = get_db()
    row = db.execute("SELECT id FROM users WHERE nickname = ?", (nickname,)).fetchone()
    if row:
        user_id = row["id"]
        session["nickname_exists"] = True
    else:
        now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")
        cursor = db.execute(
            "INSERT INTO users (nickname, created_at) VALUES (?, ?)",
            (nickname, now),
        )
        user_id = cursor.lastrowid
        db.commit()

    # 주제와 난이도로 문제 필터링
    if topic == "all" or not topic:
        qrows = db.execute(
            "SELECT id FROM questions WHERE difficulty = ?",
            (difficulty,)
        ).fetchall()
    else:
        qrows = db.execute(
            "SELECT id FROM questions WHERE topic = ? AND difficulty = ?",
            (topic, difficulty)
        ).fetchall()

    q_ids = [row["id"] for row in qrows]
    if not q_ids:
        rows = db.execute("SELECT DISTINCT topic FROM questions ORDER BY topic").fetchall()
        topics = [r["topic"] for r in rows]
        return render_template("index.html", topics=topics, error="선택한 조건에 맞는 문제가 없습니다.")

    random.shuffle(q_ids)
    q_ids = q_ids[:8]

    session["user_id"] = user_id
    session["nickname"] = nickname
    session["topic"] = topic
    session["difficulty"] = difficulty
    session["q_ids"] = q_ids
    session["answers"] = []
    session["q_index"] = 0
    session.modified = True
    return redirect(url_for("quiz.quiz"))


@quiz_bp.route("/quiz", methods=["GET", "POST"])
def quiz():
    if "q_ids" not in session:
        return redirect(url_for("quiz.index"))

    # POST: 답변 저장
    if request.method == "POST":
        answer = request.form.get("answer", "")
        answers = session.get("answers", [])
        answers.append(answer)
        session["answers"] = answers
        session["q_index"] = session.get("q_index", 0) + 1
        session.modified = True
        return redirect(url_for("quiz.quiz"))

    # GET: 문제 표시
    idx = session.get("q_index", 0)
    q_ids = session["q_ids"]

    if idx >= len(q_ids):
        return redirect(url_for("quiz.result"))

    db = get_db()
    question = db.execute("SELECT * FROM questions WHERE id = ?", (q_ids[idx],)).fetchone()

    return render_template(
        "quiz.html",
        question=question,
        index=idx + 1,
        total=len(q_ids),
        nickname_exists=session.pop("nickname_exists", False),
    )


@quiz_bp.route("/quit", methods=["GET"])
def quit_quiz():
    session.clear()
    return redirect(url_for("quiz.index"))


@quiz_bp.get("/result")
def result():
    if "q_ids" not in session:
        return redirect(url_for("quiz.index"))

    db = get_db()
    q_ids = session["q_ids"]
    questions = [
        dict(db.execute("SELECT * FROM questions WHERE id = ?", (qid,)).fetchone())
        for qid in q_ids
    ]
    answers = session.get("answers", [])

    score = scoring.calculate_score(questions, answers)
    weak_tags = analysis.find_weak_tags(questions, answers)

    user_id = session.get("user_id")
    nickname = session.get("nickname", "")
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M")

    db.execute(
        "INSERT INTO attempts (user_id, score, weak_tags, created_at) VALUES (?, ?, ?, ?)",
        (user_id, score, ",".join(weak_tags), now),
    )

    difficulty = session.get("difficulty", "")
    existing = db.execute(
        "SELECT best_score FROM hall_of_fame WHERE nickname = ?",
        (nickname,),
    ).fetchone()

    if existing is None:
        db.execute(
            "INSERT INTO hall_of_fame (nickname, best_score, updated_at, difficulty) VALUES (?, ?, ?, ?)",
            (nickname, score, now, difficulty),
        )
    elif score > existing["best_score"]:
        db.execute(
            "UPDATE hall_of_fame SET best_score = ?, updated_at = ?, difficulty = ? WHERE nickname = ?",
            (score, now, difficulty, nickname),
        )

    db.commit()

    videos = []
    for tag in weak_tags:
        row = db.execute(
            "SELECT youtube_url FROM concept_videos WHERE concept_tag = ?",
            (tag,),
        ).fetchone()
        if row:
            raw_url = row["youtube_url"]
            embed_url = _to_youtube_embed_url(raw_url)
            videos.append({"tag": tag, "url": raw_url, "embed_url": embed_url})

    session.clear()

    return render_template(
        "result.html",
        score=score,
        total=len(questions),
        nickname=nickname,
        weak_tags=weak_tags,
        videos=videos,
    )


def _to_youtube_embed_url(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        video_id = ""
        if "youtu.be" in host:
            video_id = parsed.path.lstrip("/")
        elif "youtube.com" in host:
            qs = parse_qs(parsed.query)
            video_id = (qs.get("v") or [""])[0]
        if not video_id:
            return ""
        return f"https://www.youtube.com/embed/{video_id}"
    except Exception:
        return ""
