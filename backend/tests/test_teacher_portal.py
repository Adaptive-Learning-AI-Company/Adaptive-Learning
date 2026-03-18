from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, Player
from backend.student_tracking import (
    end_activity_session,
    mark_node_mastered,
    record_answer_evaluation,
    record_topic_session_start,
    start_activity_session,
    touch_activity_session,
    touch_current_node,
)
from backend.teacher_portal import build_student_progress_detail, create_teacher_request, get_teacher_dashboard_payload, respond_to_teacher_request


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _add_player(db, username: str, role: str) -> Player:
    now = datetime.utcnow()
    player = Player(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        role=role,
        grade_level=5,
        created_at=now,
        updated_at=now,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def test_teacher_request_acceptance_and_dashboard_summary():
    db = _make_session()
    try:
        student = _add_player(db, "student1", "Student")
        teacher = _add_player(db, "teacher1", "Teacher")

        link = create_teacher_request(db, student, "teacher1", request_note="Please coach me")
        db.commit()

        assert link.status == "PENDING"

        respond_to_teacher_request(db, teacher, link.id, "ACCEPTED", response_note="Approved")
        record_topic_session_start(db, student, "Math 5")
        touch_current_node(db, student, "Math 5", "Math->Fractions->Equivalent")
        record_answer_evaluation(
            db,
            player=student,
            topic_name="Math 5",
            node_id="Math->Fractions->Equivalent",
            is_correct=True,
            score_percent=100,
            problem="What is 1/2 equal to?",
            answer="2/4",
            feedback="[CORRECT] Great work.",
        )
        mark_node_mastered(db, student, "Math 5", "Math->Fractions->Equivalent")
        start_activity_session(db, student, "token-1")
        touch_activity_session(
            db,
            student,
            "token-1",
            topic_name="Math 5",
            node_id="Math->Fractions->Equivalent",
            increment_request=False,
            increment_chat_turn=True,
        )
        end_activity_session(db, student, "token-1")
        db.commit()
        db.refresh(link)

        dashboard = get_teacher_dashboard_payload(db, teacher)
        assert dashboard["pending_requests"] == []
        assert len(dashboard["accepted_students"]) == 1
        summary = dashboard["accepted_students"][0]
        assert summary["username"] == "student1"
        assert summary["current_topic"] == "Math 5"
        assert summary["current_node"] is None
        assert summary["average_score_percent"] == 100.0
        assert summary["correct_rate_percent"] == 100.0
        assert summary["total_answer_attempts"] == 1
        assert summary["total_chat_turns"] == 1
    finally:
        db.close()


def test_student_progress_detail_includes_topics_nodes_and_sessions():
    db = _make_session()
    try:
        student = _add_player(db, "student2", "Student")
        teacher = _add_player(db, "teacher2", "Teacher")

        link = create_teacher_request(db, student, "teacher2")
        respond_to_teacher_request(db, teacher, link.id, "ACCEPTED")
        record_topic_session_start(db, student, "Science 5")
        touch_current_node(db, student, "Science 5", "Science->Matter->States")
        record_answer_evaluation(
            db,
            player=student,
            topic_name="Science 5",
            node_id="Science->Matter->States",
            is_correct=False,
            score_percent=50,
            problem="Name the state of water in a cloud.",
            answer="solid",
            feedback="[INCORRECT] Clouds are mostly tiny liquid droplets.",
        )
        start_activity_session(db, student, "token-2")
        touch_activity_session(
            db,
            student,
            "token-2",
            topic_name="Science 5",
            node_id="Science->Matter->States",
            increment_request=False,
        )
        end_activity_session(db, student, "token-2")
        db.commit()
        db.refresh(link)

        detail = build_student_progress_detail(db, student, teacher_link=link)
        assert detail["teacher_link"]["status"] == "ACCEPTED"
        assert detail["student"]["username"] == "student2"
        assert len(detail["topics"]) == 1
        assert detail["topics"][0]["topic_name"] == "Science 5"
        assert detail["topics"][0]["average_score_percent"] == 50.0
        assert len(detail["nodes"]) == 1
        assert detail["nodes"][0]["node_id"] == "Science->Matter->States"
        assert detail["nodes"][0]["average_score_percent"] == 50.0
        assert len(detail["recent_sessions"]) == 1
        assert detail["recent_sessions"][0]["last_topic_name"] == "Science 5"
    finally:
        db.close()
