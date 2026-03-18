from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy.orm import Session

from .database import Player, StudentActivitySession, StudentNodeProgress, TeacherStudentLink, TopicProgress
from .knowledge_graph import get_all_subjects_stats, get_subject_completion_stats


STATUS_PENDING = "PENDING"
STATUS_ACCEPTED = "ACCEPTED"
STATUS_REJECTED = "REJECTED"
STATUS_REVOKED = "REVOKED"
ACTIVE_LINK_STATUSES = {STATUS_PENDING, STATUS_ACCEPTED}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def serialize_teacher_link(link: TeacherStudentLink) -> dict:
    return {
        "id": link.id,
        "teacher_username": link.teacher.username if link.teacher else None,
        "student_username": link.student.username if link.student else None,
        "status": link.status,
        "request_note": link.request_note,
        "response_note": link.response_note,
        "requested_at": link.requested_at,
        "responded_at": link.responded_at,
        "accepted_at": link.accepted_at,
        "revoked_at": link.revoked_at,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def _topic_average_score(progress: TopicProgress) -> float:
    attempts = int(progress.answer_attempt_count or 0)
    if attempts <= 0:
        return 0.0
    return round(float(progress.cumulative_score_percent or 0) / float(attempts), 1)


def _node_average_score(progress: StudentNodeProgress) -> float:
    attempts = int(progress.attempt_count or 0)
    if attempts <= 0:
        return 0.0
    return round(float(progress.cumulative_score_percent or 0) / float(attempts), 1)


def _student_subject_completion(db: Session, player_id: int) -> dict[str, float]:
    result: dict[str, float] = {}
    for subject_key in ["Math", "Science", "Social_Studies", "ELA"]:
        done, total = get_subject_completion_stats(player_id, db, subject_key)
        result[subject_key] = round((float(done) / float(total)) * 100.0, 1) if total > 0 else 0.0
    return result


def _latest_topic_progress(topic_progress_rows: list[TopicProgress]) -> TopicProgress | None:
    if not topic_progress_rows:
        return None
    return sorted(
        topic_progress_rows,
        key=lambda row: row.last_interaction_at or row.updated_at or row.created_at or datetime.min,
        reverse=True,
    )[0]


def build_student_summary(
    db: Session,
    student: Player,
    accepted_at: datetime | None = None,
) -> dict:
    topic_progress_rows = db.query(TopicProgress).filter(TopicProgress.player_id == student.id).all()
    activity_rows = db.query(StudentActivitySession).filter(StudentActivitySession.player_id == student.id).all()

    latest_topic = _latest_topic_progress(topic_progress_rows)
    done_grade, total_grade = get_all_subjects_stats(student.id, db)
    grade_completion = round((float(done_grade) / float(total_grade)) * 100.0, 1) if total_grade > 0 else 0.0

    total_attempts = sum(int(row.answer_attempt_count or 0) for row in topic_progress_rows)
    total_correct = sum(int(row.correct_answer_count or 0) for row in topic_progress_rows)
    total_incorrect = sum(int(row.incorrect_answer_count or 0) for row in topic_progress_rows)
    total_score = sum(int(row.cumulative_score_percent or 0) for row in topic_progress_rows)
    total_learning_seconds = sum(int(row.total_learning_seconds or 0) for row in topic_progress_rows)
    topic_session_count = sum(int(row.session_count or 0) for row in topic_progress_rows)
    average_score = round(float(total_score) / float(total_attempts), 1) if total_attempts > 0 else 0.0
    correct_rate = round((float(total_correct) / float(total_attempts)) * 100.0, 1) if total_attempts > 0 else 0.0

    total_login_seconds = sum(int(row.total_active_seconds or 0) for row in activity_rows)
    total_request_count = sum(int(row.request_count or 0) for row in activity_rows)
    total_chat_turns = sum(int(row.chat_turn_count or 0) for row in activity_rows)
    last_seen_at = None
    for row in activity_rows:
        candidate = row.last_seen_at or row.ended_at or row.started_at
        if candidate and (last_seen_at is None or candidate > last_seen_at):
            last_seen_at = candidate

    return {
        "username": student.username,
        "display_name": student.display_name or student.username,
        "grade_level": int(student.grade_level or 0),
        "last_login_at": student.last_login_at,
        "last_seen_at": last_seen_at,
        "current_topic": latest_topic.topic_name if latest_topic else None,
        "current_node": latest_topic.current_node if latest_topic else None,
        "grade_completion": grade_completion,
        "subject_completion": _student_subject_completion(db, student.id),
        "total_answer_attempts": total_attempts,
        "correct_answer_count": total_correct,
        "incorrect_answer_count": total_incorrect,
        "average_score_percent": average_score,
        "correct_rate_percent": correct_rate,
        "total_learning_seconds": total_learning_seconds,
        "total_login_seconds": total_login_seconds,
        "total_request_count": total_request_count,
        "total_chat_turns": total_chat_turns,
        "session_count": len(activity_rows),
        "active_topic_count": len(topic_progress_rows),
        "linked_at": accepted_at,
    }


def build_student_progress_detail(
    db: Session,
    student: Player,
    teacher_link: TeacherStudentLink | None = None,
) -> dict:
    topic_rows = db.query(TopicProgress).filter(
        TopicProgress.player_id == student.id
    ).order_by(
        TopicProgress.last_interaction_at.desc(),
        TopicProgress.updated_at.desc(),
    ).all()
    node_rows = db.query(StudentNodeProgress).filter(
        StudentNodeProgress.player_id == student.id
    ).order_by(
        StudentNodeProgress.last_seen_at.desc(),
        StudentNodeProgress.updated_at.desc(),
    ).limit(120).all()
    activity_rows = db.query(StudentActivitySession).filter(
        StudentActivitySession.player_id == student.id
    ).order_by(
        StudentActivitySession.started_at.desc()
    ).limit(30).all()

    summary = build_student_summary(db, student, accepted_at=teacher_link.accepted_at if teacher_link else None)

    topics = []
    for row in topic_rows:
        topics.append(
            {
                "topic_name": row.topic_name,
                "subject_key": row.subject_key,
                "book_level": row.book_level,
                "status": row.status,
                "mastery_score": int(row.mastery_score or 0),
                "current_node": row.current_node,
                "completed_nodes_count": len(list(row.completed_nodes) if row.completed_nodes else []),
                "answer_attempt_count": int(row.answer_attempt_count or 0),
                "correct_answer_count": int(row.correct_answer_count or 0),
                "incorrect_answer_count": int(row.incorrect_answer_count or 0),
                "average_score_percent": _topic_average_score(row),
                "total_learning_seconds": int(row.total_learning_seconds or 0),
                "session_count": int(row.session_count or 0),
                "last_interaction_at": row.last_interaction_at,
                "last_answered_at": row.last_answered_at,
                "completed_at": row.completed_at,
            }
        )

    nodes = []
    for row in node_rows:
        nodes.append(
            {
                "topic_name": row.topic_name,
                "node_id": row.node_id,
                "subject_key": row.subject_key,
                "book_level": row.book_level,
                "status": row.status,
                "attempt_count": int(row.attempt_count or 0),
                "correct_count": int(row.correct_count or 0),
                "incorrect_count": int(row.incorrect_count or 0),
                "average_score_percent": _node_average_score(row),
                "total_learning_seconds": int(row.total_learning_seconds or 0),
                "last_score_percent": row.last_score_percent,
                "last_problem": row.last_problem,
                "last_answer": row.last_answer,
                "last_feedback": row.last_feedback,
                "first_seen_at": row.first_seen_at,
                "last_seen_at": row.last_seen_at,
                "completed_at": row.completed_at,
            }
        )

    recent_sessions = []
    for row in activity_rows:
        recent_sessions.append(
            {
                "started_at": row.started_at,
                "last_seen_at": row.last_seen_at,
                "ended_at": row.ended_at,
                "total_active_seconds": int(row.total_active_seconds or 0),
                "request_count": int(row.request_count or 0),
                "chat_turn_count": int(row.chat_turn_count or 0),
                "last_topic_name": row.last_topic_name,
                "last_node_id": row.last_node_id,
            }
        )

    return {
        "teacher_link": serialize_teacher_link(teacher_link) if teacher_link else None,
        "student": summary,
        "topics": topics,
        "nodes": nodes,
        "recent_sessions": recent_sessions,
    }


def create_teacher_request(
    db: Session,
    student: Player,
    teacher_username: str,
    request_note: str | None = None,
) -> TeacherStudentLink:
    if (student.role or "").strip() != "Student":
        raise HTTPException(status_code=403, detail="Only student accounts can request a teacher.")

    cleaned_teacher_username = teacher_username.strip()
    if not cleaned_teacher_username:
        raise HTTPException(status_code=400, detail="Teacher username is required.")
    if cleaned_teacher_username == student.username:
        raise HTTPException(status_code=400, detail="A student cannot link to themself as a teacher.")

    teacher = db.query(Player).filter(Player.username == cleaned_teacher_username).first()
    if teacher is None:
        raise HTTPException(status_code=404, detail="Teacher account not found.")
    if (teacher.role or "").strip() != "Teacher" and (teacher.role or "").strip() != "Admin":
        raise HTTPException(status_code=400, detail="That account is not eligible to be linked as a teacher.")

    link = db.query(TeacherStudentLink).filter(
        TeacherStudentLink.teacher_id == teacher.id,
        TeacherStudentLink.student_id == student.id,
    ).first()
    now = _utcnow()
    note = _clean_optional_text(request_note)

    if link is None:
        link = TeacherStudentLink(
            teacher_id=teacher.id,
            student_id=student.id,
            status=STATUS_PENDING,
            request_note=note,
            requested_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(link)
        db.flush()
        return link

    if link.status == STATUS_PENDING and link.revoked_at is None:
        raise HTTPException(status_code=400, detail="Teacher approval is already pending.")
    if link.status == STATUS_ACCEPTED and link.revoked_at is None:
        raise HTTPException(status_code=400, detail="This teacher is already linked to the student.")

    link.status = STATUS_PENDING
    link.request_note = note
    link.response_note = None
    link.requested_at = now
    link.responded_at = None
    link.accepted_at = None
    link.revoked_at = None
    link.updated_at = now
    return link


def list_teacher_links_for_user(db: Session, user: Player) -> list[TeacherStudentLink]:
    query = db.query(TeacherStudentLink)
    if (user.role or "").strip() == "Teacher":
        query = query.filter(TeacherStudentLink.teacher_id == user.id)
    else:
        query = query.filter(TeacherStudentLink.student_id == user.id)

    return query.order_by(
        TeacherStudentLink.status.asc(),
        TeacherStudentLink.requested_at.desc(),
        TeacherStudentLink.updated_at.desc(),
    ).all()


def respond_to_teacher_request(
    db: Session,
    teacher: Player,
    link_id: int,
    action: str,
    response_note: str | None = None,
) -> TeacherStudentLink:
    cleaned_action = (action or "").strip().upper()
    if cleaned_action not in {STATUS_ACCEPTED, STATUS_REJECTED, STATUS_REVOKED}:
        raise HTTPException(status_code=400, detail="Action must be ACCEPTED, REJECTED, or REVOKED.")

    link = db.query(TeacherStudentLink).filter(TeacherStudentLink.id == link_id).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Teacher link request not found.")
    if link.teacher_id != teacher.id and (teacher.role or "").strip() != "Admin":
        raise HTTPException(status_code=403, detail="Only the requested teacher can respond to this request.")

    now = _utcnow()
    link.status = cleaned_action
    link.response_note = _clean_optional_text(response_note)
    link.responded_at = now
    link.updated_at = now
    if cleaned_action == STATUS_ACCEPTED:
        link.accepted_at = now
        link.revoked_at = None
    elif cleaned_action == STATUS_REVOKED:
        link.revoked_at = now
    else:
        link.accepted_at = None
    return link


def get_teacher_dashboard_payload(db: Session, teacher: Player) -> dict:
    pending_links = db.query(TeacherStudentLink).filter(
        TeacherStudentLink.teacher_id == teacher.id,
        TeacherStudentLink.status == STATUS_PENDING,
        TeacherStudentLink.revoked_at.is_(None),
    ).order_by(TeacherStudentLink.requested_at.desc()).all()

    accepted_links = db.query(TeacherStudentLink).filter(
        TeacherStudentLink.teacher_id == teacher.id,
        TeacherStudentLink.status == STATUS_ACCEPTED,
        TeacherStudentLink.revoked_at.is_(None),
    ).order_by(TeacherStudentLink.accepted_at.desc(), TeacherStudentLink.updated_at.desc()).all()

    accepted_students = [
        build_student_summary(db, link.student, accepted_at=link.accepted_at)
        for link in accepted_links
        if link.student is not None
    ]

    return {
        "pending_requests": [serialize_teacher_link(link) for link in pending_links],
        "accepted_students": accepted_students,
    }


def get_accepted_teacher_link(
    db: Session,
    teacher: Player,
    student: Player,
) -> TeacherStudentLink | None:
    return db.query(TeacherStudentLink).filter(
        TeacherStudentLink.teacher_id == teacher.id,
        TeacherStudentLink.student_id == student.id,
        TeacherStudentLink.status == STATUS_ACCEPTED,
        TeacherStudentLink.revoked_at.is_(None),
    ).first()


def assert_teacher_can_view_student(
    db: Session,
    teacher: Player,
    student: Player,
) -> TeacherStudentLink | None:
    if (teacher.role or "").strip() == "Admin":
        return None
    if (teacher.role or "").strip() != "Teacher":
        raise HTTPException(status_code=403, detail="Teacher access is required.")

    link = get_accepted_teacher_link(db, teacher, student)
    if link is None:
        raise HTTPException(status_code=403, detail="Teacher approval is required before viewing student progress.")
    return link
