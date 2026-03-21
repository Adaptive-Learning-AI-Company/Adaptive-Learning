from __future__ import annotations

from datetime import datetime
import os

from sqlalchemy.orm import Session

from .database import Player, StudentActivitySession, StudentNodeProgress, TopicProgress


DEFAULT_LEARNING_MODE = "teach_me"


MAX_ACTIVITY_GAP_SECONDS = int(os.getenv("TRACKING_ACTIVITY_GAP_CAP_SECONDS", "300"))
MAX_NODE_GAP_SECONDS = int(os.getenv("TRACKING_NODE_GAP_CAP_SECONDS", "600"))


def _utcnow() -> datetime:
    return datetime.utcnow()


def _clamp_positive_seconds(delta_seconds: float, cap_seconds: int) -> int:
    if delta_seconds <= 0:
        return 0
    return int(min(delta_seconds, float(max(cap_seconds, 1))))


def _topic_metadata(topic_name: str | None) -> tuple[str | None, int | None]:
    if not topic_name:
        return None, None

    token = topic_name.strip().split(" ")[0].replace("-", "_")
    normalized = token.lower()
    subject_map = {
        "math": "Math",
        "science": "Science",
        "history": "Social_Studies",
        "social_studies": "Social_Studies",
        "socialstudies": "Social_Studies",
        "english": "ELA",
        "ela": "ELA",
    }
    subject_key = subject_map.get(normalized, token)

    level_value = None
    digits = "".join(ch for ch in topic_name if ch.isdigit())
    if digits:
        try:
            level_value = int(digits)
        except ValueError:
            level_value = None

    return subject_key, level_value


def _ensure_topic_progress(
    db: Session,
    player_id: int,
    topic_name: str,
    now: datetime | None = None,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> TopicProgress:
    now = now or _utcnow()
    progress = db.query(TopicProgress).filter(
        TopicProgress.player_id == player_id,
        TopicProgress.topic_name == topic_name,
        TopicProgress.learning_mode == (learning_mode or DEFAULT_LEARNING_MODE),
    ).first()
    if progress:
        return progress

    subject_key, book_level = _topic_metadata(topic_name)
    progress = TopicProgress(
        player_id=player_id,
        topic_name=topic_name,
        learning_mode=learning_mode or DEFAULT_LEARNING_MODE,
        subject_key=subject_key,
        book_level=book_level,
        content_grade_level=book_level,
        mastery_level=0,
        mastery_score=0,
        status="NOT_STARTED",
        created_at=now,
        updated_at=now,
        last_interaction_at=now,
    )
    db.add(progress)
    db.flush()
    return progress


def _ensure_node_progress(
    db: Session,
    player_id: int,
    topic_name: str,
    node_id: str,
    now: datetime | None = None,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> StudentNodeProgress:
    now = now or _utcnow()
    progress = db.query(StudentNodeProgress).filter(
        StudentNodeProgress.player_id == player_id,
        StudentNodeProgress.topic_name == topic_name,
        StudentNodeProgress.node_id == node_id,
        StudentNodeProgress.learning_mode == (learning_mode or DEFAULT_LEARNING_MODE),
    ).first()
    if progress:
        return progress

    subject_key, book_level = _topic_metadata(topic_name)
    progress = StudentNodeProgress(
        player_id=player_id,
        topic_name=topic_name,
        node_id=node_id,
        learning_mode=learning_mode or DEFAULT_LEARNING_MODE,
        subject_key=subject_key,
        book_level=book_level,
        mastery_level=0,
        status="NOT_STARTED",
        created_at=now,
        updated_at=now,
        first_seen_at=now,
        last_seen_at=now,
    )
    db.add(progress)
    db.flush()
    return progress


def ensure_topic_progress(
    db: Session,
    player_id: int,
    topic_name: str,
    learning_mode: str = DEFAULT_LEARNING_MODE,
    now: datetime | None = None,
) -> TopicProgress:
    return _ensure_topic_progress(
        db,
        player_id=player_id,
        topic_name=topic_name,
        now=now,
        learning_mode=learning_mode,
    )


def ensure_node_progress(
    db: Session,
    player_id: int,
    topic_name: str,
    node_id: str,
    learning_mode: str = DEFAULT_LEARNING_MODE,
    now: datetime | None = None,
) -> StudentNodeProgress:
    return _ensure_node_progress(
        db,
        player_id=player_id,
        topic_name=topic_name,
        node_id=node_id,
        now=now,
        learning_mode=learning_mode,
    )


def _credit_node_learning_time(
    topic_progress: TopicProgress | None,
    node_progress: StudentNodeProgress | None,
    now: datetime,
) -> int:
    if not topic_progress:
        return 0

    started_at = topic_progress.current_node_started_at or topic_progress.last_interaction_at
    if not started_at:
        return 0

    credited_seconds = _clamp_positive_seconds((now - started_at).total_seconds(), MAX_NODE_GAP_SECONDS)
    if credited_seconds <= 0:
        return 0

    topic_progress.total_learning_seconds = int(topic_progress.total_learning_seconds or 0) + credited_seconds
    if node_progress is not None:
        node_progress.total_learning_seconds = int(node_progress.total_learning_seconds or 0) + credited_seconds
    return credited_seconds


def _get_activity_session(
    db: Session,
    player_id: int,
    token_jti: str | None,
) -> StudentActivitySession | None:
    if not token_jti:
        return None
    return db.query(StudentActivitySession).filter(
        StudentActivitySession.player_id == player_id,
        StudentActivitySession.token_jti == token_jti,
    ).first()


def start_activity_session(db: Session, player: Player, token_jti: str | None) -> StudentActivitySession | None:
    if not token_jti:
        return None

    now = _utcnow()
    activity_session = _get_activity_session(db, player.id, token_jti)
    if activity_session:
        activity_session.started_at = activity_session.started_at or now
        activity_session.last_seen_at = now
        activity_session.ended_at = None
        activity_session.updated_at = now
        return activity_session

    activity_session = StudentActivitySession(
        player_id=player.id,
        token_jti=token_jti,
        started_at=now,
        last_seen_at=now,
        total_active_seconds=0,
        request_count=1,
        chat_turn_count=0,
        created_at=now,
        updated_at=now,
    )
    db.add(activity_session)
    db.flush()
    return activity_session


def touch_activity_session(
    db: Session,
    player: Player,
    token_jti: str | None,
    topic_name: str | None = None,
    node_id: str | None = None,
    increment_request: bool = True,
    increment_chat_turn: bool = False,
) -> StudentActivitySession | None:
    if not token_jti:
        return None

    now = _utcnow()
    activity_session = _get_activity_session(db, player.id, token_jti)
    if activity_session is None:
        activity_session = start_activity_session(db, player, token_jti)
        if activity_session is None:
            return None
        if not increment_request:
            activity_session.request_count = max(int(activity_session.request_count or 1) - 1, 0)

    if activity_session.last_seen_at:
        credited_seconds = _clamp_positive_seconds(
            (now - activity_session.last_seen_at).total_seconds(),
            MAX_ACTIVITY_GAP_SECONDS,
        )
        activity_session.total_active_seconds = int(activity_session.total_active_seconds or 0) + credited_seconds

    activity_session.last_seen_at = now
    activity_session.updated_at = now
    activity_session.ended_at = None
    if increment_request:
        activity_session.request_count = int(activity_session.request_count or 0) + 1
    if increment_chat_turn:
        activity_session.chat_turn_count = int(activity_session.chat_turn_count or 0) + 1
    if topic_name:
        activity_session.last_topic_name = topic_name
    if node_id:
        activity_session.last_node_id = node_id
    return activity_session


def end_activity_session(db: Session, player: Player, token_jti: str | None) -> StudentActivitySession | None:
    activity_session = _get_activity_session(db, player.id, token_jti)
    if activity_session is None:
        return None

    now = _utcnow()
    if activity_session.last_seen_at:
        credited_seconds = _clamp_positive_seconds(
            (now - activity_session.last_seen_at).total_seconds(),
            MAX_ACTIVITY_GAP_SECONDS,
        )
        activity_session.total_active_seconds = int(activity_session.total_active_seconds or 0) + credited_seconds
    activity_session.last_seen_at = now
    activity_session.ended_at = now
    activity_session.updated_at = now
    return activity_session


def record_topic_session_start(
    db: Session,
    player: Player,
    topic_name: str,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> TopicProgress:
    now = _utcnow()
    topic_progress = _ensure_topic_progress(db, player.id, topic_name, now, learning_mode=learning_mode)
    topic_progress.session_count = int(topic_progress.session_count or 0) + 1
    topic_progress.last_interaction_at = now
    topic_progress.updated_at = now
    if topic_progress.status == "NOT_STARTED":
        topic_progress.status = "IN_PROGRESS"
    return topic_progress


def touch_current_node(
    db: Session,
    player: Player,
    topic_name: str,
    node_id: str,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> StudentNodeProgress:
    now = _utcnow()
    topic_progress = _ensure_topic_progress(db, player.id, topic_name, now, learning_mode=learning_mode)

    previous_node_progress = None
    if topic_progress.current_node and topic_progress.current_node != node_id:
        previous_node_progress = _ensure_node_progress(
            db,
            player.id,
            topic_name,
            topic_progress.current_node,
            now,
            learning_mode=learning_mode,
        )
        _credit_node_learning_time(topic_progress, previous_node_progress, now)

    node_progress = _ensure_node_progress(
        db,
        player.id,
        topic_name,
        node_id,
        now,
        learning_mode=learning_mode,
    )
    if topic_progress.current_node == node_id:
        _credit_node_learning_time(topic_progress, node_progress, now)
    node_progress.first_seen_at = node_progress.first_seen_at or now
    node_progress.last_seen_at = now
    node_progress.updated_at = now
    if node_progress.status == "NOT_STARTED":
        node_progress.status = "IN_PROGRESS"

    topic_progress.current_node = node_id
    topic_progress.current_node_started_at = now
    topic_progress.last_interaction_at = now
    topic_progress.updated_at = now
    if topic_progress.status == "NOT_STARTED":
        topic_progress.status = "IN_PROGRESS"

    return node_progress


def record_answer_evaluation(
    db: Session,
    player: Player,
    topic_name: str,
    node_id: str | None,
    is_correct: bool,
    score_percent: int | None,
    problem: str | None,
    answer: str | None,
    feedback: str | None,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> tuple[TopicProgress, StudentNodeProgress]:
    now = _utcnow()
    topic_progress = _ensure_topic_progress(db, player.id, topic_name, now, learning_mode=learning_mode)

    resolved_node_id = node_id or topic_progress.current_node or topic_name
    node_progress = _ensure_node_progress(
        db,
        player.id,
        topic_name,
        resolved_node_id,
        now,
        learning_mode=learning_mode,
    )

    if topic_progress.current_node != resolved_node_id:
        touch_current_node(db, player, topic_name, resolved_node_id, learning_mode=learning_mode)
        topic_progress = _ensure_topic_progress(db, player.id, topic_name, now, learning_mode=learning_mode)
        node_progress = _ensure_node_progress(
            db,
            player.id,
            topic_name,
            resolved_node_id,
            now,
            learning_mode=learning_mode,
        )

    _credit_node_learning_time(topic_progress, node_progress, now)

    score_value = 100 if is_correct and score_percent is None else 0 if (not is_correct and score_percent is None) else int(score_percent or 0)
    score_value = max(0, min(score_value, 100))

    topic_progress.answer_attempt_count = int(topic_progress.answer_attempt_count or 0) + 1
    topic_progress.cumulative_score_percent = int(topic_progress.cumulative_score_percent or 0) + score_value
    topic_progress.first_answered_at = topic_progress.first_answered_at or now
    topic_progress.last_answered_at = now
    topic_progress.last_interaction_at = now
    topic_progress.updated_at = now
    topic_progress.status = "IN_PROGRESS" if topic_progress.status != "COMPLETED" else topic_progress.status

    node_progress.attempt_count = int(node_progress.attempt_count or 0) + 1
    node_progress.cumulative_score_percent = int(node_progress.cumulative_score_percent or 0) + score_value
    node_progress.last_score_percent = score_value
    node_progress.last_problem = problem
    node_progress.last_answer = answer
    node_progress.last_feedback = feedback
    node_progress.first_seen_at = node_progress.first_seen_at or now
    node_progress.last_seen_at = now
    node_progress.updated_at = now
    if node_progress.status != "COMPLETED":
        node_progress.status = "IN_PROGRESS"

    if is_correct:
        topic_progress.correct_answer_count = int(topic_progress.correct_answer_count or 0) + 1
        node_progress.correct_count = int(node_progress.correct_count or 0) + 1
    else:
        topic_progress.incorrect_answer_count = int(topic_progress.incorrect_answer_count or 0) + 1
        node_progress.incorrect_count = int(node_progress.incorrect_count or 0) + 1
        current_mistakes = list(topic_progress.mistakes) if topic_progress.mistakes else []
        current_mistakes.append(resolved_node_id)
        topic_progress.mistakes = current_mistakes

    topic_progress.current_node_started_at = now
    return topic_progress, node_progress


def mark_node_mastered(
    db: Session,
    player: Player,
    topic_name: str,
    node_id: str | None,
    learning_mode: str = DEFAULT_LEARNING_MODE,
) -> tuple[TopicProgress, StudentNodeProgress] | tuple[None, None]:
    if not node_id:
        return None, None

    now = _utcnow()
    topic_progress = _ensure_topic_progress(db, player.id, topic_name, now, learning_mode=learning_mode)
    node_progress = _ensure_node_progress(
        db,
        player.id,
        topic_name,
        node_id,
        now,
        learning_mode=learning_mode,
    )

    _credit_node_learning_time(topic_progress, node_progress, now)

    node_progress.mastery_level = 10
    node_progress.status = "COMPLETED"
    node_progress.completed_at = node_progress.completed_at or now
    node_progress.last_seen_at = now
    node_progress.updated_at = now

    completed_nodes = list(topic_progress.completed_nodes) if topic_progress.completed_nodes else []
    if node_id not in completed_nodes:
        completed_nodes.append(node_id)
        topic_progress.completed_nodes = completed_nodes

    if topic_progress.current_node == node_id:
        topic_progress.current_node = None
        topic_progress.current_node_started_at = None
    topic_progress.last_interaction_at = now
    topic_progress.updated_at = now
    if topic_progress.status == "NOT_STARTED":
        topic_progress.status = "IN_PROGRESS"
    return topic_progress, node_progress
