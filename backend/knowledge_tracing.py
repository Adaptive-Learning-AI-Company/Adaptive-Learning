from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from .database import StudentNodeProgress, TopicProgress
from .knowledge_graph import _canonical_subject_key, _subject_topic_prefixes, get_graph
from .student_tracking import (
    ensure_node_progress,
    ensure_topic_progress,
    mark_node_mastered,
)


TEACH_ME_MODE = "teach_me"
KNOWLEDGE_TRACING_MODE = "knowledge_tracing"

FULL_MASTERY_LEVEL = 10
TENTATIVE_MASTERY_LEVEL = 6
TRACE_REVIEW_CADENCE = 3


def normalize_learning_mode(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"knowledge_tracing", "knowledge_trace", "tracing", "tracer"}:
        return KNOWLEDGE_TRACING_MODE
    return TEACH_ME_MODE


def is_knowledge_tracing_mode(value: str | None) -> bool:
    return normalize_learning_mode(value) == KNOWLEDGE_TRACING_MODE


def learning_mode_label(value: str | None) -> str:
    if is_knowledge_tracing_mode(value):
        return "Knowledge Tracing"
    return "Teach Me"


def canonical_subject_for_topic(topic_name: str | None) -> str:
    return _canonical_subject_key(topic_name or "Math")


def knowledge_tracing_topic_name(topic_name: str | None) -> str:
    return f"{canonical_subject_for_topic(topic_name)} [Knowledge Tracing]"


def resolve_topic_for_mode(topic_name: str, learning_mode: str | None) -> str:
    if is_knowledge_tracing_mode(learning_mode):
        return knowledge_tracing_topic_name(topic_name)
    return topic_name


def topic_label_for_mode(topic_name: str, learning_mode: str | None) -> str:
    if is_knowledge_tracing_mode(learning_mode):
        return canonical_subject_for_topic(topic_name) + " Knowledge Tracing"
    return topic_name


def _subject_progress_filters(topic_name: str) -> tuple[str, list]:
    subject_key = canonical_subject_for_topic(topic_name)
    filters = [TopicProgress.subject_key == subject_key]
    for prefix in _subject_topic_prefixes(subject_key):
        filters.append(TopicProgress.topic_name.ilike(f"{prefix}%"))
    return subject_key, filters


def _subject_node_filters(topic_name: str) -> tuple[str, list]:
    subject_key = canonical_subject_for_topic(topic_name)
    filters = [StudentNodeProgress.subject_key == subject_key]
    for prefix in _subject_topic_prefixes(subject_key):
        filters.append(StudentNodeProgress.topic_name.ilike(f"{prefix}%"))
    return subject_key, filters


def get_topic_progress(
    db: Session,
    player_id: int,
    topic_name: str,
    learning_mode: str = TEACH_ME_MODE,
) -> TopicProgress | None:
    return db.query(TopicProgress).filter(
        TopicProgress.player_id == player_id,
        TopicProgress.topic_name == topic_name,
        TopicProgress.learning_mode == normalize_learning_mode(learning_mode),
    ).first()


def get_subject_topic_rows(db: Session, player_id: int, topic_name: str) -> list[TopicProgress]:
    _subject_key, filters = _subject_progress_filters(topic_name)
    return db.query(TopicProgress).filter(
        TopicProgress.player_id == player_id,
        or_(*filters),
    ).all()


def get_subject_node_rows(db: Session, player_id: int, topic_name: str) -> list[StudentNodeProgress]:
    _subject_key, filters = _subject_node_filters(topic_name)
    return db.query(StudentNodeProgress).filter(
        StudentNodeProgress.player_id == player_id,
        or_(*filters),
    ).all()


def get_subject_node_mastery_map(db: Session, player_id: int, topic_name: str) -> dict[str, int]:
    mastery_map: dict[str, int] = {}

    for row in get_subject_node_rows(db, player_id, topic_name):
        level = max(0, min(FULL_MASTERY_LEVEL, int(row.mastery_level or 0)))
        if row.status == "COMPLETED":
            level = FULL_MASTERY_LEVEL
        mastery_map[row.node_id] = max(mastery_map.get(row.node_id, 0), level)

    for row in get_subject_topic_rows(db, player_id, topic_name):
        for node_id in list(row.completed_nodes) if row.completed_nodes else []:
            mastery_map[node_id] = FULL_MASTERY_LEVEL

    return mastery_map


def get_subject_full_mastery_node_ids(db: Session, player_id: int, topic_name: str) -> set[str]:
    mastery_map = get_subject_node_mastery_map(db, player_id, topic_name)
    return {node_id for node_id, level in mastery_map.items() if level >= FULL_MASTERY_LEVEL}


def _concept_node_ids(topic_name: str, target_grade: int | None = None, include_challenge: bool = False) -> list[str]:
    kg = get_graph(topic_name)
    if not kg or not kg.graph.nodes:
        return []

    max_grade = None
    if target_grade is not None:
        max_grade = target_grade + (1 if include_challenge else 0)

    concept_ids: list[str] = []
    for node_id, data in kg.graph.nodes(data=True):
        if data.get("type") != "concept":
            continue
        if max_grade is not None and int(data.get("grade_level", 0) or 0) > max_grade:
            continue
        concept_ids.append(node_id)

    concept_ids.sort(key=lambda node_id: (
        int(kg.graph.nodes[node_id].get("grade_level", 0) or 0),
        node_id,
    ))
    return concept_ids


def _prereqs_satisfied(kg, node_id: str, mastery_map: dict[str, int], threshold: int) -> bool:
    for prereq in kg.get_prerequisites(node_id):
        if mastery_map.get(prereq, 0) < threshold:
            return False
    return True


def select_next_teach_me_node(
    db: Session,
    player_id: int,
    topic_name: str,
    target_grade: int | None,
    current_node_id: str | None = None,
):
    kg = get_graph(topic_name)
    if not kg or not kg.graph.nodes:
        return None

    mastered = get_subject_full_mastery_node_ids(db, player_id, topic_name)
    if current_node_id and current_node_id not in mastered:
        current_node = kg.get_node(current_node_id)
        if current_node is not None:
            return current_node

    candidates = kg.get_next_learnable_nodes(sorted(mastered), target_grade=target_grade)
    for candidate in candidates:
        if candidate.id not in mastered:
            return candidate
    return None


def select_next_tracing_node(
    db: Session,
    player_id: int,
    topic_name: str,
    target_grade: int | None,
    current_node_id: str | None = None,
):
    kg = get_graph(topic_name)
    if not kg or not kg.graph.nodes:
        return None

    mastery_map = get_subject_node_mastery_map(db, player_id, topic_name)
    if current_node_id and mastery_map.get(current_node_id, 0) < FULL_MASTERY_LEVEL:
        current_node = kg.get_node(current_node_id)
        if current_node is not None:
            return current_node

    node_rows = get_subject_node_rows(db, player_id, topic_name)
    attempt_map: dict[str, int] = {}
    last_seen_map: dict[str, datetime] = {}
    for row in node_rows:
        attempt_map[row.node_id] = max(attempt_map.get(row.node_id, 0), int(row.attempt_count or 0))
        if row.last_seen_at and (
            row.node_id not in last_seen_map or row.last_seen_at > last_seen_map[row.node_id]
        ):
            last_seen_map[row.node_id] = row.last_seen_at

    topic_progress = get_topic_progress(db, player_id, topic_name, KNOWLEDGE_TRACING_MODE)
    review_turn = False
    if topic_progress is not None:
        review_turn = int(topic_progress.answer_attempt_count or 0) > 0 and (
            int(topic_progress.answer_attempt_count or 0) % TRACE_REVIEW_CADENCE == 0
        )

    def sort_key(node_id: str, prefer_review: bool) -> tuple:
        level = mastery_map.get(node_id, 0)
        node_grade = int(kg.graph.nodes[node_id].get("grade_level", 0) or 0)
        grade_distance = abs(node_grade - (target_grade if target_grade is not None else node_grade))
        attempt_count = int(attempt_map.get(node_id, 0))
        last_seen = last_seen_map.get(node_id)
        last_seen_rank = 0
        if last_seen is not None:
            last_seen_rank = int(last_seen.timestamp())
        if prefer_review:
            return (level, grade_distance, last_seen_rank, attempt_count, node_id)
        return (grade_distance, level, attempt_count, node_grade, node_id)

    fresh_candidates: list[str] = []
    review_candidates: list[str] = []
    for node_id in _concept_node_ids(topic_name, target_grade=target_grade, include_challenge=True):
        level = mastery_map.get(node_id, 0)
        if level >= FULL_MASTERY_LEVEL:
            continue
        if not _prereqs_satisfied(kg, node_id, mastery_map, TENTATIVE_MASTERY_LEVEL):
            continue
        if level <= 0:
            fresh_candidates.append(node_id)
        else:
            review_candidates.append(node_id)

    if review_turn and review_candidates:
        review_candidates.sort(key=lambda node_id: sort_key(node_id, True))
        return kg.get_node(review_candidates[0])

    if fresh_candidates:
        fresh_candidates.sort(key=lambda node_id: sort_key(node_id, False))
        return kg.get_node(fresh_candidates[0])

    if review_candidates:
        review_candidates.sort(key=lambda node_id: sort_key(node_id, True))
        return kg.get_node(review_candidates[0])

    return None


def _required_subject_concepts(topic_name: str, target_grade: int | None) -> list[str]:
    concept_ids = _concept_node_ids(topic_name, target_grade=target_grade, include_challenge=False)
    if concept_ids:
        return concept_ids
    return _concept_node_ids(topic_name)


def refresh_tracing_topic_mastery(
    db: Session,
    player_id: int,
    topic_name: str,
    target_grade: int | None,
) -> dict[str, int]:
    topic_progress = ensure_topic_progress(
        db,
        player_id=player_id,
        topic_name=topic_name,
        learning_mode=KNOWLEDGE_TRACING_MODE,
    )
    mastery_map = get_subject_node_mastery_map(db, player_id, topic_name)
    required_concepts = _required_subject_concepts(topic_name, target_grade)
    levels = [max(0, min(FULL_MASTERY_LEVEL, mastery_map.get(node_id, 0))) for node_id in required_concepts]

    if not levels:
        subject_level = 0
        subject_score = 0
    else:
        average_level = float(sum(levels)) / float(len(levels))
        subject_level = max(0, min(FULL_MASTERY_LEVEL, int(round(average_level))))
        subject_score = max(0, min(100, int(round(average_level * 10.0))))

    topic_progress.mastery_level = subject_level
    topic_progress.mastery_score = subject_score
    if target_grade is not None:
        topic_progress.content_grade_level = target_grade
    if subject_level >= FULL_MASTERY_LEVEL and levels and all(level >= FULL_MASTERY_LEVEL for level in levels):
        topic_progress.status = "COMPLETED"
        topic_progress.completed_at = topic_progress.completed_at or datetime.utcnow()
    elif int(topic_progress.answer_attempt_count or 0) > 0 or topic_progress.current_node:
        topic_progress.status = "IN_PROGRESS"

    return {
        "subject_level": subject_level,
        "subject_score": subject_score,
    }


def _propagate_tentative_prerequisites(
    db: Session,
    player_id: int,
    topic_name: str,
    node_id: str,
    mastery_map: dict[str, int],
) -> None:
    kg = get_graph(topic_name)
    current_node = kg.get_node(node_id)
    if current_node is None:
        return

    stack = list(kg.get_prerequisites(node_id))
    seen: set[str] = set()
    now = datetime.utcnow()

    while stack:
        prereq_id = stack.pop()
        if prereq_id in seen:
            continue
        seen.add(prereq_id)

        prereq_node = kg.get_node(prereq_id)
        if prereq_node is None or prereq_node.grade_level > current_node.grade_level:
            continue

        if mastery_map.get(prereq_id, 0) < TENTATIVE_MASTERY_LEVEL:
            prereq_progress = ensure_node_progress(
                db,
                player_id=player_id,
                topic_name=topic_name,
                node_id=prereq_id,
                learning_mode=KNOWLEDGE_TRACING_MODE,
                now=now,
            )
            prereq_progress.mastery_level = max(int(prereq_progress.mastery_level or 0), TENTATIVE_MASTERY_LEVEL)
            prereq_progress.status = "IN_PROGRESS" if prereq_progress.status == "NOT_STARTED" else prereq_progress.status
            prereq_progress.last_seen_at = prereq_progress.last_seen_at or now
            prereq_progress.updated_at = now
            mastery_map[prereq_id] = prereq_progress.mastery_level

        for ancestor_id in kg.get_prerequisites(prereq_id):
            if ancestor_id not in seen:
                stack.append(ancestor_id)


def apply_tracing_result(
    db: Session,
    player_id: int,
    topic_name: str,
    node_id: str,
    target_grade: int | None,
    is_correct: bool,
    score_percent: int | None,
) -> dict[str, int]:
    score_value = max(0, min(100, int(score_percent or 0)))
    topic_progress = ensure_topic_progress(
        db,
        player_id=player_id,
        topic_name=topic_name,
        learning_mode=KNOWLEDGE_TRACING_MODE,
    )
    node_progress = ensure_node_progress(
        db,
        player_id=player_id,
        topic_name=topic_name,
        node_id=node_id,
        learning_mode=KNOWLEDGE_TRACING_MODE,
    )
    previous_level = max(0, min(FULL_MASTERY_LEVEL, int(node_progress.mastery_level or 0)))

    if previous_level < FULL_MASTERY_LEVEL:
        if is_correct:
            if score_value >= 90:
                delta = 3
            elif score_value >= 75:
                delta = 2
            else:
                delta = 1
        else:
            delta = -2 if score_value < 40 else -1
        node_progress.mastery_level = max(0, min(FULL_MASTERY_LEVEL, previous_level + delta))

    if int(node_progress.mastery_level or 0) >= FULL_MASTERY_LEVEL:
        mark_node_mastered(
            db,
            player=topic_progress.player,
            topic_name=topic_name,
            node_id=node_id,
            learning_mode=KNOWLEDGE_TRACING_MODE,
        )
        node_progress.mastery_level = FULL_MASTERY_LEVEL
    else:
        node_progress.status = "IN_PROGRESS" if node_progress.status != "COMPLETED" else node_progress.status

    mastery_map = get_subject_node_mastery_map(db, player_id, topic_name)
    mastery_map[node_id] = max(mastery_map.get(node_id, 0), int(node_progress.mastery_level or 0))

    if is_correct and score_value >= 75:
        _propagate_tentative_prerequisites(db, player_id, topic_name, node_id, mastery_map)

    topic_progress.content_grade_level = target_grade
    refreshed = refresh_tracing_topic_mastery(db, player_id, topic_name, target_grade)
    refreshed["node_level"] = max(0, min(FULL_MASTERY_LEVEL, int(node_progress.mastery_level or 0)))
    return refreshed
