from flask import Blueprint, render_template
from ..db import get_db

hall_bp = Blueprint("hall", __name__)


@hall_bp.get("/")
def hall():
    db = get_db()
    def fetch_rows(diff):
        return db.execute(
            """
            SELECT nickname, best_score, updated_at, difficulty
            FROM hall_of_fame
            WHERE difficulty = ?
            ORDER BY best_score DESC, best_duration_seconds ASC, updated_at DESC
            LIMIT 20
            """,
            (diff,),
        ).fetchall()

    return render_template(
        "hall.html",
        rows_easy=fetch_rows("easy"),
        rows_medium=fetch_rows("medium"),
        rows_hard=fetch_rows("hard"),
    )
