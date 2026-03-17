from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.access_grants import (
    ACCESS_SOURCE_MANUAL,
    ACCESS_SOURCE_PROMO,
    create_manual_access_grant,
    create_promo_code,
    redeem_promo_code,
    revoke_access_grant,
    revoke_promo_code,
)
from backend.billing import PLAN_HOSTED_MONTHLY, get_billing_state
from backend.database import Base, Player


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


def test_assigned_promo_code_redeems_only_for_matching_user(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "true")
    db = _make_session()
    try:
        owner = _add_player(db, "owner")
        other = _add_player(db, "other")
        expires_at = datetime.utcnow() + timedelta(days=7)
        promo_code, raw_code = create_promo_code(
            db,
            plan_code=PLAN_HOSTED_MONTHLY,
            assigned_player_id=owner.id,
            created_by_player_id=owner.id,
            expires_at=expires_at,
        )
        db.commit()

        with pytest.raises(HTTPException) as excinfo:
            redeem_promo_code(db, other, raw_code)
        assert excinfo.value.status_code == 403

        redeemed_promo, grant, created = redeem_promo_code(db, owner, raw_code)
        db.commit()

        state = get_billing_state(db, owner)
        assert redeemed_promo.id == promo_code.id
        assert created is True
        assert grant.source_type == ACCESS_SOURCE_PROMO
        assert state["allowed"] is True
        assert state["access_source_type"] == ACCESS_SOURCE_PROMO
        assert state["effective_plan_code"] == PLAN_HOSTED_MONTHLY
    finally:
        db.close()


def test_revoked_promo_code_stops_access_even_if_grant_row_remains(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "true")
    db = _make_session()
    try:
        player = _add_player(db, "student")
        promo_code, raw_code = create_promo_code(
            db,
            plan_code=PLAN_HOSTED_MONTHLY,
            expires_at=datetime.utcnow() + timedelta(days=14),
        )
        db.commit()

        _, grant, _ = redeem_promo_code(db, player, raw_code)
        db.commit()

        active_state = get_billing_state(db, player)
        assert active_state["allowed"] is True

        revoke_promo_code(db, promo_code.id, reason="ended", revoke_linked_grants=False)
        db.commit()
        db.refresh(grant)

        revoked_state = get_billing_state(db, player)
        assert grant.revoked_at is None
        assert revoked_state["active_access_grant"] is None
        assert revoked_state["allowed"] is False
    finally:
        db.close()


def test_manual_access_grant_can_be_non_expiring_and_revoked(monkeypatch):
    monkeypatch.setenv("BILLING_ENFORCED", "true")
    db = _make_session()
    try:
        admin = _add_player(db, "admin", role="Admin")
        player = _add_player(db, "evaluator")

        grant = create_manual_access_grant(
            db,
            player_id=player.id,
            plan_code=PLAN_HOSTED_MONTHLY,
            created_by_player_id=admin.id,
            notes="VC evaluation",
        )
        db.commit()

        active_state = get_billing_state(db, player)
        assert grant.source_type == ACCESS_SOURCE_MANUAL
        assert grant.expires_at is None
        assert active_state["allowed"] is True
        assert active_state["access_source_type"] == ACCESS_SOURCE_MANUAL

        revoke_access_grant(db, grant.id, reason="review complete")
        db.commit()

        revoked_state = get_billing_state(db, player)
        assert revoked_state["allowed"] is False
        assert revoked_state["active_access_grant"] is None
    finally:
        db.close()
