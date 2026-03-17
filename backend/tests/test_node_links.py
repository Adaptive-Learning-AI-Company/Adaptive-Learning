from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base, NodeLink, Player
from backend.node_links import (
    REVIEW_APPROVED,
    REVIEW_PENDING,
    get_node_links_for_node,
    review_node_link,
    submit_node_link,
    sync_authoritative_node_links,
)


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def _add_player(db, username: str, role: str = "Student") -> Player:
    now = datetime.utcnow()
    player = Player(
        username=username,
        display_name=username,
        email=f"{username}@example.com",
        role=role,
        created_at=now,
        updated_at=now,
    )
    db.add(player)
    db.commit()
    db.refresh(player)
    return player


def test_node_link_submission_review_and_catalog_sync(monkeypatch):
    db = _make_session()
    try:
        student = _add_player(db, "student1")
        admin = _add_player(db, "admin1", role="Admin")

        monkeypatch.setattr(
            "backend.node_links.load_authoritative_node_link_catalog",
            lambda: [
                {
                    "external_key": "catalog-1",
                    "node_id": "OA->4OAA->4.OA.1",
                    "subject_key": "Math",
                    "title": "Official Lesson",
                    "url": "https://example.com/official-lesson",
                    "description": "Trusted lesson",
                    "provider": "example.com",
                    "link_type": "lesson",
                    "is_active": True,
                    "sort_order": 1,
                    "extra_metadata": {"audience": "student"},
                }
            ],
        )

        sync_authoritative_node_links(db)

        authoritative = db.query(NodeLink).filter(NodeLink.external_key == "catalog-1").first()
        assert authoritative is not None
        assert authoritative.review_status == REVIEW_APPROVED

        submitted = submit_node_link(
            db,
            submitted_by_player_id=student.id,
            node_id="OA->4OAA->4.OA.1",
            topic="Math 4",
            title="Helpful video",
            url="https://www.youtube.com/watch?v=abc123",
            description="A good explanation",
            provider=None,
            link_type="video",
            extra_metadata={"channel": "sample"},
        )
        db.commit()

        assert submitted.review_status == REVIEW_PENDING

        review_node_link(
            db,
            link_id=submitted.id,
            reviewed_by_player_id=admin.id,
            review_status=REVIEW_APPROVED,
            review_notes="Approved for use",
            is_active=True,
            sort_order=5,
        )
        db.commit()

        payload = get_node_links_for_node(db, "OA->4OAA->4.OA.1", viewer_player_id=admin.id, is_admin=True)

        assert len(payload["authoritative_links"]) == 1
        assert len(payload["approved_user_links"]) == 1
        assert payload["approved_user_links"][0]["review_status"] == REVIEW_APPROVED
        assert payload["approved_user_links"][0]["submitted_by_username"] == "student1"
    finally:
        db.close()
