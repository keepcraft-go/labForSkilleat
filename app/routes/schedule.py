import os
import calendar
from datetime import date, datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, session, abort

from ..db import get_db

schedule_bp = Blueprint("schedule", __name__)


def _month_range(year: int, month: int):
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    return start, end


def _build_calendar(year: int, month: int, events):
    cal = calendar.Calendar(firstweekday=calendar.SUNDAY)
    weeks = cal.monthdayscalendar(year, month)
    event_map = {}

    for ev in events:
        start = ev["start_date"]
        end = ev["end_date"]
        include_weekends = ev.get("include_weekends", False)
        valid_days = []
        cur = start
        while cur <= end:
            if include_weekends or cur.weekday() < 5:
                valid_days.append(cur)
            cur += timedelta(days=1)

        if not valid_days:
            continue

        for i, day in enumerate(valid_days):
            if day not in event_map:
                event_map[day] = []
            if len(valid_days) == 1:
                segment = "single"
            elif i == 0:
                segment = "start"
            elif i == len(valid_days) - 1:
                segment = "end"
            else:
                segment = "middle"
            event_map[day].append({
                "title": ev["title"],
                "segment": segment
            })

    calendar_weeks = []
    for week in weeks:
        row = []
        for day in week:
            if day == 0:
                row.append(None)
            else:
                current = date(year, month, day)
                row.append({
                    "day": day,
                    "date": current,
                    "events": event_map.get(current, [])
                })
        calendar_weeks.append(row)
    return calendar_weeks


def _is_admin():
    return session.get("is_admin", False)


@schedule_bp.get("/schedule")
def schedule():
    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    start, end = _month_range(year, month)
    db = get_db()
    rows = db.execute(
        """
        SELECT id, title, start_date, end_date, note, include_weekends
        FROM schedules
        WHERE NOT (end_date < ? OR start_date > ?)
        ORDER BY start_date ASC
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    events = []
    for row in rows:
        events.append({
            "id": row["id"],
            "title": row["title"],
            "start_date": date.fromisoformat(row["start_date"]),
            "end_date": date.fromisoformat(row["end_date"]),
            "note": row["note"] or "",
            "include_weekends": bool(row["include_weekends"])
        })

    cal_weeks = _build_calendar(year, month, events)

    prev_month = (month - 1) or 12
    prev_year = year - 1 if month == 1 else year
    next_month = (month + 1) if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    return render_template(
        "schedule.html",
        calendar_weeks=cal_weeks,
        year=year,
        month=month,
        prev_year=prev_year,
        prev_month=prev_month,
        next_year=next_year,
        next_month=next_month,
        is_admin=_is_admin(),
    )


@schedule_bp.get("/schedule/admin")
def schedule_admin():
    if not _is_admin():
        return render_template("schedule_admin.html", is_admin=False)

    db = get_db()
    rows = db.execute(
        """
        SELECT id, title, start_date, end_date, note, include_weekends
        FROM schedules
        ORDER BY start_date DESC
        """
    ).fetchall()
    return render_template(
        "schedule_admin.html",
        is_admin=True,
        schedules=rows,
        edit_item=None,
    )


@schedule_bp.post("/schedule/admin/login")
def schedule_login():
    password = request.form.get("password", "")
    if password and password == os.getenv("ADMIN_PASSWORD"):
        session["is_admin"] = True
    return redirect(url_for("schedule.schedule_admin"))


@schedule_bp.post("/schedule/admin/logout")
def schedule_logout():
    session.pop("is_admin", None)
    return redirect(url_for("schedule.schedule"))


@schedule_bp.post("/schedule/admin/create")
def schedule_create():
    if not _is_admin():
        abort(403)

    title = request.form.get("title", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    note = request.form.get("note", "").strip()
    include_weekends = bool(request.form.get("include_weekends"))

    if not title or not start_date:
        return redirect(url_for("schedule.schedule"))

    if not end_date:
        end_date = start_date

    try:
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
    except ValueError:
        return redirect(url_for("schedule.schedule"))

    if end_dt < start_dt:
        return redirect(url_for("schedule.schedule_admin"))

    if (start_dt.weekday() >= 5 or end_dt.weekday() >= 5) and start_dt == end_dt:
        include_weekends = True

    db = get_db()
    db.execute(
        "INSERT INTO schedules (title, start_date, end_date, note, include_weekends, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (title, start_dt.isoformat(), end_dt.isoformat(), note, int(include_weekends), datetime.now().strftime("%Y-%m-%d %H:%M")),
    )
    db.commit()
    return redirect(url_for("schedule.schedule_admin"))


@schedule_bp.get("/schedule/admin/edit/<int:schedule_id>")
def schedule_edit(schedule_id: int):
    if not _is_admin():
        abort(403)

    db = get_db()
    rows = db.execute(
        """
        SELECT id, title, start_date, end_date, note, include_weekends
        FROM schedules
        ORDER BY start_date DESC
        """
    ).fetchall()
    item = db.execute(
        "SELECT id, title, start_date, end_date, note, include_weekends FROM schedules WHERE id = ?",
        (schedule_id,),
    ).fetchone()
    if item is None:
        return redirect(url_for("schedule.schedule_admin"))

    return render_template(
        "schedule_admin.html",
        is_admin=True,
        schedules=rows,
        edit_item=item,
    )


@schedule_bp.post("/schedule/admin/update/<int:schedule_id>")
def schedule_update(schedule_id: int):
    if not _is_admin():
        abort(403)

    title = request.form.get("title", "").strip()
    start_date = request.form.get("start_date", "").strip()
    end_date = request.form.get("end_date", "").strip()
    note = request.form.get("note", "").strip()
    include_weekends = bool(request.form.get("include_weekends"))

    if not title or not start_date:
        return redirect(url_for("schedule.schedule_admin"))

    if not end_date:
        end_date = start_date

    try:
        start_dt = date.fromisoformat(start_date)
        end_dt = date.fromisoformat(end_date)
    except ValueError:
        return redirect(url_for("schedule.schedule_admin"))

    if end_dt < start_dt:
        return redirect(url_for("schedule.schedule_admin"))

    if (start_dt.weekday() >= 5 or end_dt.weekday() >= 5) and start_dt == end_dt:
        include_weekends = True

    db = get_db()
    db.execute(
        """
        UPDATE schedules
        SET title = ?, start_date = ?, end_date = ?, note = ?, include_weekends = ?
        WHERE id = ?
        """,
        (title, start_dt.isoformat(), end_dt.isoformat(), note, int(include_weekends), schedule_id),
    )
    db.commit()
    return redirect(url_for("schedule.schedule_admin"))


@schedule_bp.post("/schedule/admin/delete/<int:schedule_id>")
def schedule_delete(schedule_id: int):
    if not _is_admin():
        abort(403)
    db = get_db()
    db.execute("DELETE FROM schedules WHERE id = ?", (schedule_id,))
    db.commit()
    return redirect(url_for("schedule.schedule_admin"))
