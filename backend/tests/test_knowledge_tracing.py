from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, Player, StudentNodeProgress
from backend.knowledge_graph import get_graph
from backend.knowledge_tracing import (
    KNOWLEDGE_TRACING_MODE,
    apply_tracing_result,
    knowledge_tracing_topic_name,
    refresh_tracing_topic_mastery,
    select_next_teach_me_node,
)
from backend.student_tracking import record_answer_evaluation, record_topic_session_start, touch_current_node


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _add_player(db, username: str = "trace-student") -> Player:
    now = datetime.utcnow()
    player = Player(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        role="Student",
        grade_level=5,
        created_at=now,
        updated_at=now,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def _first_concept_with_prereq(topic_name: str) -> tuple[str, str]:
    kg = get_graph(topic_name)
    for node_id in sorted(kg.graph.nodes()):
        if kg.graph.nodes[node_id].get("type") != "concept":
            continue
        prereqs = kg.get_prerequisites(node_id)
        if prereqs:
            return node_id, prereqs[0]
    raise AssertionError("Expected at least one concept with prerequisites in the graph")


def test_tracing_correct_answer_lifts_prerequisite_mastery():
    db = _make_session()
    try:
        player = _add_player(db)
        topic_name = knowledge_tracing_topic_name("Math")
        node_id, prereq_id = _first_concept_with_prereq(topic_name)

        record_topic_session_start(db, player, topic_name, learning_mode=KNOWLEDGE_TRACING_MODE)
        touch_current_node(db, player, topic_name, node_id, learning_mode=KNOWLEDGE_TRACING_MODE)
        record_answer_evaluation(
            db,
            player=player,
            topic_name=topic_name,
            node_id=node_id,
            is_correct=True,
            score_percent=100,
            problem="Solve the checkpoint.",
            answer="Correct",
            feedback="[CORRECT] Nice work.",
            learning_mode=KNOWLEDGE_TRACING_MODE,
        )
        result = apply_tracing_result(
            db,
            player_id=player.id,
            topic_name=topic_name,
            node_id=node_id,
            target_grade=5,
            is_correct=True,
            score_percent=100,
        )
        db.commit()

        prereq_progress = db.query(StudentNodeProgress).filter(
            StudentNodeProgress.player_id == player.id,
            StudentNodeProgress.topic_name == topic_name,
            StudentNodeProgress.node_id == prereq_id,
            StudentNodeProgress.learning_mode == KNOWLEDGE_TRACING_MODE,
        ).first()

        assert result["node_level"] >= 3
        assert prereq_progress is not None
        assert int(prereq_progress.mastery_level or 0) >= 6
    finally:
        db.close()


def test_teach_me_selector_skips_tracing_mastered_node():
    db = _make_session()
    try:
        player = _add_player(db, username="trace-skipper")
        teach_me_topic = "Math 5"
        tracing_topic = knowledge_tracing_topic_name("Math")

        first_candidate = select_next_teach_me_node(db, player.id, teach_me_topic, target_grade=5)
        assert first_candidate is not None

        record_topic_session_start(db, player, tracing_topic, learning_mode=KNOWLEDGE_TRACING_MODE)
        touch_current_node(db, player, tracing_topic, first_candidate.id, learning_mode=KNOWLEDGE_TRACING_MODE)
        for _ in range(4):
            record_answer_evaluation(
                db,
                player=player,
                topic_name=tracing_topic,
                node_id=first_candidate.id,
                is_correct=True,
                score_percent=100,
                problem="Checkpoint",
                answer="Correct",
                feedback="[CORRECT] Great job.",
                learning_mode=KNOWLEDGE_TRACING_MODE,
            )
            apply_tracing_result(
                db,
                player_id=player.id,
                topic_name=tracing_topic,
                node_id=first_candidate.id,
                target_grade=5,
                is_correct=True,
                score_percent=100,
            )
        refresh_tracing_topic_mastery(db, player.id, tracing_topic, target_grade=5)
        db.commit()

        next_candidate = select_next_teach_me_node(db, player.id, teach_me_topic, target_grade=5)
        assert next_candidate is not None
        assert next_candidate.id != first_candidate.id
    finally:
        db.close()
