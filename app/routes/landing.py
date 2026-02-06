from flask import Blueprint, render_template
import markdown
from ..db import get_db
from ..services.news import get_tech_news

landing_bp = Blueprint("landing", __name__)

@landing_bp.get("/")
def landing():
    # 상위 10명의 랭킹 가져오기
    db = get_db()
    top_users = db.execute(
        "SELECT nickname, best_score, updated_at, difficulty FROM hall_of_fame ORDER BY best_score DESC, updated_at ASC LIMIT 10"
    ).fetchall()
    
    return render_template("landing.html", top_users=top_users)

@landing_bp.get("/news")
def news():
    news_items = get_tech_news()
    return render_template("news.html", news_items=news_items)

@landing_bp.get("/news/<news_id>")
def news_detail(news_id):
    """뉴스 상세 페이지"""
    news_items = get_tech_news()
    
    # news_id로 해당 뉴스 찾기
    selected_news = None
    for item in news_items:
        if str(item.get("id")) == str(news_id):
            selected_news = item
            break
    
    if selected_news is None:
        return render_template("404.html"), 404
    
    # 마크다운을 HTML로 변환 (상세 마크다운 우선)
    detail_text = selected_news.get("detail_markdown") or selected_news.get("description")
    if detail_text:
        selected_news["description_html"] = markdown.markdown(
            detail_text,
            extensions=['tables', 'fenced_code']
        )
    
    return render_template("news_detail.html", news=selected_news)
