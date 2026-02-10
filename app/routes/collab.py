import os
import smtplib
from email.message import EmailMessage
from datetime import date, timedelta
from flask import Blueprint, render_template, request, jsonify
from dotenv import load_dotenv

from ..db import get_db

collab_bp = Blueprint("collab", __name__)
load_dotenv()


@collab_bp.get("/collab")
def collab_page():
    return render_template("collab.html")


@collab_bp.post("/api/contact")
def collab_contact():
    data = request.get_json(silent=True) or {}
    required = ["fullName", "company", "email", "audience", "topic", "desiredDate", "details"]
    missing = [k for k in required if not str(data.get(k, "")).strip()]
    if missing:
        return jsonify({"message": "필수 항목이 누락되었습니다."}), 400

    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_secure = os.getenv("SMTP_SECURE", "false").lower() == "true"
    mail_from = os.getenv("MAIL_FROM")
    mail_to = os.getenv("MAIL_TO", "contact@skilleat.com")

    if not all([smtp_host, smtp_user, smtp_pass, mail_from]):
        return jsonify({"message": "메일 설정이 누락되었습니다."}), 500

    topic = data["topic"]
    if topic == "기타" and data.get("topicOther"):
        topic = f"기타: {data.get('topicOther')}"
    subject = f"[협업 문의] {data['fullName']} - {topic}"
    body = (
        f"이름: {data['fullName']}\n"
        f"회사/기관: {data['company']}\n"
        f"이메일: {data['email']}\n"
        f"연락처: {data.get('phone','') or '-'}\n"
        f"대상: {data['audience']}\n"
        f"주제: {topic}\n"
        f"희망 일정: {data['desiredDate']}\n\n"
        "문의 내용:\n"
        f"{data['details']}\n"
    )

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = mail_to
    msg.set_content(body)

    try:
        if smtp_secure:
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(msg)
    except Exception:
        return jsonify({"message": "메일 전송 실패"}), 500

    return jsonify({"ok": True})


@collab_bp.get("/api/schedule")
def collab_schedule():
    db = get_db()
    rows = db.execute(
        "SELECT title, start_date, end_date FROM schedules ORDER BY start_date ASC"
    ).fetchall()

    events = []
    for row in rows:
        start = date.fromisoformat(row["start_date"])
        end = date.fromisoformat(row["end_date"]) + timedelta(days=1)
        events.append({
            "title": row["title"],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "allDay": True
        })
    return jsonify(events)
