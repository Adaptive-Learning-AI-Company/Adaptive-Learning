from __future__ import annotations

from datetime import datetime
import hashlib
import os
import secrets

from fastapi import HTTPException

from .config import load_local_env

load_local_env()

ACCESS_SOURCE_MANUAL = "manual"
ACCESS_SOURCE_PROMO = "promo"

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _utcnow() -> datetime:
    return datetime.utcnow()


def normalize_access_code(raw_code: str | None) -> str:
    if raw_code is None:
        return ""
    return "".join(character for character in raw_code.strip().upper() if character.isalnum())


def hash_access_code(raw_code: str) -> str:
    normalized = normalize_access_code(raw_code)
    if not normalized:
        raise HTTPException(status_code=400, detail="Access code is required.")

    secret = os.getenv("PROMO_CODE_HASH_SECRET") or os.getenv("SECRET_KEY") or "dev_promo_secret_change_me"
    return hashlib.sha256(f"{secret}:{normalized}".encode("utf-8")).hexdigest()


def access_code_prefix(raw_code: str) -> str:
    normalized = normalize_access_code(raw_code)
    return normalized[:8]


def generate_access_code(prefix: str = "AT") -> str:
    chunks = [
        "".join(secrets.choice(_CODE_ALPHABET) for _ in range(4))
        for _ in range(3)
    ]
    safe_prefix = normalize_access_code(prefix)[:4] or "AT"
    return "-".join([safe_prefix] + chunks)


def _validate_plan_code(plan_code: str):
    from .billing import get_plan_definition

    if not plan_code or not get_plan_definition(plan_code):
        raise HTTPException(status_code=400, detail="Unknown access plan code.")


def _grant_is_active(grant, current_time: datetime) -> bool:
    if grant is None or grant.revoked_at is not None:
        return False
    if grant.starts_at and grant.starts_at > current_time:
        return False
    if grant.expires_at and grant.expires_at <= current_time:
        return False
    return True


def _promo_is_active(promo_code, current_time: datetime) -> bool:
    if promo_code is None or promo_code.revoked_at is not None:
        return False
    if promo_code.starts_at and promo_code.starts_at > current_time:
        return False
    if promo_code.expires_at and promo_code.expires_at <= current_time:
        return False
    return True


def get_active_access_grant(db, player_id: int, now: datetime | None = None):
    from .database import AccessGrant, PromoCode

    current_time = now or _utcnow()
    grants = db.query(AccessGrant).filter(AccessGrant.player_id == player_id).all()
    active_grants = []

    for grant in grants:
        if not _grant_is_active(grant, current_time):
            continue
        if grant.source_type == ACCESS_SOURCE_PROMO and grant.source_id:
            promo_code = db.query(PromoCode).filter(PromoCode.id == grant.source_id).first()
            if not _promo_is_active(promo_code, current_time):
                continue
        active_grants.append(grant)

    if not active_grants:
        return None

    def _rank(grant) -> tuple[int, datetime, datetime]:
        expires_at = grant.expires_at or datetime.max
        created_at = grant.created_at or datetime.min
        return (1 if grant.expires_at is None else 0, expires_at, created_at)

    return max(active_grants, key=_rank)


def get_access_source_label(grant) -> str | None:
    if grant is None:
        return None
    if grant.source_type == ACCESS_SOURCE_PROMO:
        return "Promo code access"
    if grant.source_type == ACCESS_SOURCE_MANUAL:
        return "Manual access grant"
    return grant.source_type.replace("_", " ").title()


def serialize_access_grant(grant) -> dict:
    player = getattr(grant, "player", None)
    created_by = getattr(grant, "created_by", None)
    return {
        "id": grant.id,
        "username": player.username if player else None,
        "plan_code": grant.plan_code,
        "source_type": grant.source_type,
        "source_id": grant.source_id,
        "starts_at": grant.starts_at,
        "expires_at": grant.expires_at,
        "revoked_at": grant.revoked_at,
        "revocation_reason": grant.revocation_reason,
        "notes": grant.notes,
        "created_at": grant.created_at,
        "updated_at": grant.updated_at,
        "created_by_username": created_by.username if created_by else None,
    }


def serialize_promo_code(promo_code) -> dict:
    assigned_player = getattr(promo_code, "assigned_player", None)
    created_by = getattr(promo_code, "created_by", None)
    return {
        "id": promo_code.id,
        "code_prefix": promo_code.code_prefix,
        "assigned_username": assigned_player.username if assigned_player else None,
        "plan_code": promo_code.plan_code,
        "starts_at": promo_code.starts_at,
        "expires_at": promo_code.expires_at,
        "max_redemptions": promo_code.max_redemptions,
        "redemption_count": promo_code.redemption_count,
        "revoked_at": promo_code.revoked_at,
        "revocation_reason": promo_code.revocation_reason,
        "notes": promo_code.notes,
        "created_at": promo_code.created_at,
        "updated_at": promo_code.updated_at,
        "created_by_username": created_by.username if created_by else None,
    }


def create_promo_code(
    db,
    plan_code: str,
    assigned_player_id: int | None = None,
    created_by_player_id: int | None = None,
    starts_at: datetime | None = None,
    expires_at: datetime | None = None,
    max_redemptions: int = 1,
    raw_code: str | None = None,
    notes: str | None = None,
    extra_metadata: dict | None = None,
):
    from .database import PromoCode

    _validate_plan_code(plan_code)
    if max_redemptions < 1:
        raise HTTPException(status_code=400, detail="max_redemptions must be at least 1.")
    if starts_at and expires_at and starts_at >= expires_at:
        raise HTTPException(status_code=400, detail="expires_at must be after starts_at.")

    candidate_code = raw_code.strip().upper() if raw_code else None
    attempts = 0
    while True:
        attempts += 1
        if attempts > 25:
            raise HTTPException(status_code=500, detail="Could not generate a unique access code.")

        candidate_code = candidate_code or generate_access_code()
        code_hash = hash_access_code(candidate_code)
        existing = db.query(PromoCode).filter(PromoCode.code_hash == code_hash).first()
        if not existing:
            break
        if raw_code:
            raise HTTPException(status_code=400, detail="That access code already exists.")
        candidate_code = None

    current_time = _utcnow()
    promo_code = PromoCode(
        code_hash=code_hash,
        code_prefix=access_code_prefix(candidate_code),
        assigned_player_id=assigned_player_id,
        plan_code=plan_code,
        starts_at=starts_at,
        expires_at=expires_at,
        max_redemptions=max_redemptions,
        redemption_count=0,
        created_by_player_id=created_by_player_id,
        notes=notes,
        extra_metadata=dict(extra_metadata or {}),
        created_at=current_time,
        updated_at=current_time,
    )
    db.add(promo_code)
    db.flush()
    return promo_code, candidate_code


def create_manual_access_grant(
    db,
    player_id: int,
    plan_code: str,
    created_by_player_id: int | None = None,
    starts_at: datetime | None = None,
    expires_at: datetime | None = None,
    notes: str | None = None,
    extra_metadata: dict | None = None,
    source_type: str = ACCESS_SOURCE_MANUAL,
    source_id: int | None = None,
):
    from .database import AccessGrant

    _validate_plan_code(plan_code)
    if starts_at and expires_at and starts_at >= expires_at:
        raise HTTPException(status_code=400, detail="expires_at must be after starts_at.")

    current_time = _utcnow()
    grant = AccessGrant(
        player_id=player_id,
        source_type=source_type,
        source_id=source_id,
        plan_code=plan_code,
        starts_at=starts_at,
        expires_at=expires_at,
        created_by_player_id=created_by_player_id,
        notes=notes,
        extra_metadata=dict(extra_metadata or {}),
        created_at=current_time,
        updated_at=current_time,
    )
    db.add(grant)
    db.flush()
    return grant


def redeem_promo_code(db, player, raw_code: str):
    from .database import AccessGrant, PromoCode, PromoRedemption

    code_hash = hash_access_code(raw_code)
    promo_code = db.query(PromoCode).filter(PromoCode.code_hash == code_hash).first()
    if not promo_code:
        raise HTTPException(status_code=404, detail="Access code not found.")

    current_time = _utcnow()
    if promo_code.assigned_player_id and promo_code.assigned_player_id != player.id:
        raise HTTPException(status_code=403, detail="This access code is assigned to another user.")
    if promo_code.revoked_at is not None:
        raise HTTPException(status_code=400, detail="This access code has been revoked.")
    if promo_code.starts_at and promo_code.starts_at > current_time:
        raise HTTPException(status_code=400, detail="This access code is not active yet.")
    if promo_code.expires_at and promo_code.expires_at <= current_time:
        raise HTTPException(status_code=400, detail="This access code has expired.")
    if promo_code.max_redemptions is not None and promo_code.redemption_count >= promo_code.max_redemptions:
        raise HTTPException(status_code=400, detail="This access code has reached its redemption limit.")

    existing_redemption = db.query(PromoRedemption).filter(
        PromoRedemption.promo_code_id == promo_code.id,
        PromoRedemption.player_id == player.id,
    ).first()
    if existing_redemption:
        existing_grant = None
        if existing_redemption.access_grant_id:
            existing_grant = db.query(AccessGrant).filter(
                AccessGrant.id == existing_redemption.access_grant_id
            ).first()
        if existing_grant and _grant_is_active(existing_grant, current_time):
            return promo_code, existing_grant, False
        raise HTTPException(status_code=400, detail="This access code has already been redeemed for this user.")

    grant = create_manual_access_grant(
        db,
        player_id=player.id,
        plan_code=promo_code.plan_code,
        created_by_player_id=promo_code.created_by_player_id,
        starts_at=promo_code.starts_at or current_time,
        expires_at=promo_code.expires_at,
        notes=promo_code.notes,
        extra_metadata=promo_code.extra_metadata,
        source_type=ACCESS_SOURCE_PROMO,
        source_id=promo_code.id,
    )
    redemption = PromoRedemption(
        promo_code_id=promo_code.id,
        player_id=player.id,
        access_grant_id=grant.id,
        redeemed_at=current_time,
    )
    db.add(redemption)
    promo_code.redemption_count = int(promo_code.redemption_count or 0) + 1
    promo_code.updated_at = current_time
    db.flush()
    return promo_code, grant, True


def revoke_access_grant(db, grant_id: int, reason: str | None = None):
    from .database import AccessGrant

    grant = db.query(AccessGrant).filter(AccessGrant.id == grant_id).first()
    if not grant:
        raise HTTPException(status_code=404, detail="Access grant not found.")

    current_time = _utcnow()
    grant.revoked_at = current_time
    grant.revocation_reason = reason
    grant.updated_at = current_time
    db.flush()
    return grant


def revoke_promo_code(db, promo_code_id: int, reason: str | None = None, revoke_linked_grants: bool = True):
    from .database import AccessGrant, PromoCode

    promo_code = db.query(PromoCode).filter(PromoCode.id == promo_code_id).first()
    if not promo_code:
        raise HTTPException(status_code=404, detail="Access code not found.")

    current_time = _utcnow()
    promo_code.revoked_at = current_time
    promo_code.revocation_reason = reason
    promo_code.updated_at = current_time

    if revoke_linked_grants:
        linked_grants = db.query(AccessGrant).filter(
            AccessGrant.source_type == ACCESS_SOURCE_PROMO,
            AccessGrant.source_id == promo_code.id,
            AccessGrant.revoked_at.is_(None),
        ).all()
        for grant in linked_grants:
            grant.revoked_at = current_time
            grant.revocation_reason = reason or "Promo code revoked"
            grant.updated_at = current_time

    db.flush()
    return promo_code


def list_access_grants(db, player_id: int | None = None, include_revoked: bool = False):
    from .database import AccessGrant

    query = db.query(AccessGrant).order_by(AccessGrant.created_at.desc(), AccessGrant.id.desc())
    if player_id is not None:
        query = query.filter(AccessGrant.player_id == player_id)
    if not include_revoked:
        query = query.filter(AccessGrant.revoked_at.is_(None))
    return query.all()


def list_promo_codes(db, assigned_player_id: int | None = None, include_revoked: bool = False):
    from .database import PromoCode

    query = db.query(PromoCode).order_by(PromoCode.created_at.desc(), PromoCode.id.desc())
    if assigned_player_id is not None:
        query = query.filter(PromoCode.assigned_player_id == assigned_player_id)
    if not include_revoked:
        query = query.filter(PromoCode.revoked_at.is_(None))
    return query.all()
