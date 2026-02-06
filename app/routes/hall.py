from flask import Blueprint, render_template
from ..db import get_db

hall_bp = Blueprint("hall", __name__)


@hall_bp.get("/")
def hall():
    db = get_db()
    rows = db.execute(
        "SELECT nickname, best_score, updated_at, difficulty FROM hall_of_fame ORDER BY best_score DESC, updated_at ASC LIMIT 20"
    ).fetchall()
    return render_template("hall.html", rows=rows)
