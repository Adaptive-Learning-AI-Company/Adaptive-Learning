from __future__ import annotations

from datetime import datetime
import hashlib
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from .config import load_local_env, load_repo_json_file

load_local_env()

NODE_LINKS_CONFIG_FILENAME = "knowledge_graph_links.json"

SOURCE_AUTHORITATIVE = "authoritative"
SOURCE_USER = "user"
REVIEW_APPROVED = "approved"
REVIEW_PENDING = "pending"
REVIEW_REJECTED = "rejected"

VALID_LINK_TYPES = {"article", "general", "interactive", "lesson", "reference", "video"}
VALID_REVIEW_STATUSES = {REVIEW_APPROVED, REVIEW_PENDING, REVIEW_REJECTED}


def _normalize_subject_key(topic_name: str | None) -> str | None:
    if not topic_name:
        return None

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
    return subject_map.get(normalized, token)


def _normalize_link_type(link_type: str | None) -> str:
    normalized = (link_type or "general").strip().lower()
    if normalized in VALID_LINK_TYPES:
        return normalized
    return "general"


def normalize_review_status(review_status: str | None) -> str:
    normalized = (review_status or REVIEW_PENDING).strip().lower()
    if normalized in VALID_REVIEW_STATUSES:
        return normalized
    raise HTTPException(status_code=400, detail="Invalid review status.")


def normalize_node_link_url(url: str) -> str:
    cleaned = (url or "").strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=400, detail="Links must use a valid http or https URL.")
    return cleaned


def _infer_provider(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or "external"


def _normalize_extra_metadata(value) -> dict:
    return value if isinstance(value, dict) else {}


def _authoritative_external_key(node_id: str, url: str) -> str:
    digest = hashlib.sha256(f"{node_id}|{url}".encode("utf-8")).hexdigest()[:24]
    return f"authoritative:{digest}"


def load_authoritative_node_link_catalog() -> list[dict]:
    raw_links = load_repo_json_file(NODE_LINKS_CONFIG_FILENAME).get("links", [])
    if not isinstance(raw_links, list):
        return []

    normalized_links: list[dict] = []
    for raw_link in raw_links:
        if not isinstance(raw_link, dict):
            continue

        node_id = str(raw_link.get("node_id", "")).strip()
        title = str(raw_link.get("title", "")).strip()
        url = str(raw_link.get("url", "")).strip()
        if not node_id or not title or not url:
            continue

        try:
            normalized_url = normalize_node_link_url(url)
        except HTTPException:
            continue

        normalized_links.append(
            {
                "external_key": str(raw_link.get("external_key", "")).strip() or _authoritative_external_key(node_id, normalized_url),
                "node_id": node_id,
                "subject_key": str(raw_link.get("subject_key", "")).strip() or _normalize_subject_key(raw_link.get("topic")),
                "title": title,
                "url": normalized_url,
                "description": str(raw_link.get("description", "")).strip() or None,
                "provider": str(raw_link.get("provider", "")).strip() or _infer_provider(normalized_url),
                "link_type": _normalize_link_type(raw_link.get("link_type")),
                "is_active": bool(raw_link.get("is_active", True)),
                "sort_order": int(raw_link.get("sort_order", 0) or 0),
                "extra_metadata": _normalize_extra_metadata(raw_link.get("extra_metadata")),
            }
        )
    return normalized_links


def serialize_node_link(link) -> dict:
    return {
        "id": link.id,
        "node_id": link.node_id,
        "subject_key": link.subject_key,
        "title": link.title,
        "url": link.url,
        "description": link.description,
        "provider": link.provider,
        "link_type": link.link_type,
        "source_kind": link.source_kind,
        "review_status": link.review_status,
        "review_notes": link.review_notes,
        "is_active": bool(link.is_active),
        "sort_order": link.sort_order or 0,
        "extra_metadata": dict(link.extra_metadata or {}),
        "submitted_by_username": link.submitted_by.username if getattr(link, "submitted_by", None) else None,
        "reviewed_by_username": link.reviewed_by.username if getattr(link, "reviewed_by", None) else None,
        "reviewed_at": link.reviewed_at,
        "created_at": link.created_at,
        "updated_at": link.updated_at,
    }


def sync_authoritative_node_links(db):
    from .database import NodeLink

    now = datetime.utcnow()
    catalog = load_authoritative_node_link_catalog()
    seen_external_keys: set[str] = set()

    for entry in catalog:
        existing = db.query(NodeLink).filter(NodeLink.external_key == entry["external_key"]).first()
        if not existing:
            existing = NodeLink(
                external_key=entry["external_key"],
                source_kind=SOURCE_AUTHORITATIVE,
                review_status=REVIEW_APPROVED,
                created_at=now,
            )
            db.add(existing)

        existing.node_id = entry["node_id"]
        existing.subject_key = entry["subject_key"]
        existing.title = entry["title"]
        existing.url = entry["url"]
        existing.description = entry["description"]
        existing.provider = entry["provider"]
        existing.link_type = entry["link_type"]
        existing.source_kind = SOURCE_AUTHORITATIVE
        existing.review_status = REVIEW_APPROVED
        existing.review_notes = None
        existing.is_active = entry["is_active"]
        existing.sort_order = entry["sort_order"]
        existing.extra_metadata = entry["extra_metadata"]
        existing.submitted_by_player_id = None
        existing.reviewed_by_player_id = None
        existing.reviewed_at = None
        existing.updated_at = now
        seen_external_keys.add(entry["external_key"])

    if seen_external_keys:
        stale_links = db.query(NodeLink).filter(
            NodeLink.source_kind == SOURCE_AUTHORITATIVE,
            NodeLink.external_key.isnot(None),
            NodeLink.external_key.notin_(seen_external_keys),
        ).all()
        for stale_link in stale_links:
            stale_link.is_active = False
            stale_link.updated_at = now

    db.commit()


def get_node_link_count_map(db, node_ids: list[str], include_pending: bool = False) -> dict[str, dict[str, int]]:
    from .database import NodeLink

    normalized_ids = [node_id for node_id in node_ids if node_id]
    if not normalized_ids:
        return {}

    rows = db.query(
        NodeLink.node_id,
        NodeLink.source_kind,
        NodeLink.review_status,
        func.count(NodeLink.id),
    ).filter(
        NodeLink.node_id.in_(normalized_ids),
        NodeLink.is_active.is_(True),
    ).group_by(
        NodeLink.node_id,
        NodeLink.source_kind,
        NodeLink.review_status,
    ).all()

    counts = {
        node_id: {
            "authoritative_link_count": 0,
            "approved_user_link_count": 0,
            "pending_user_link_count": 0,
        }
        for node_id in normalized_ids
    }

    for node_id, source_kind, review_status, count in rows:
        node_counts = counts.setdefault(
            node_id,
            {
                "authoritative_link_count": 0,
                "approved_user_link_count": 0,
                "pending_user_link_count": 0,
            },
        )
        if review_status == REVIEW_APPROVED and source_kind == SOURCE_AUTHORITATIVE:
            node_counts["authoritative_link_count"] = int(count)
        elif review_status == REVIEW_APPROVED and source_kind == SOURCE_USER:
            node_counts["approved_user_link_count"] = int(count)
        elif include_pending and review_status == REVIEW_PENDING and source_kind == SOURCE_USER:
            node_counts["pending_user_link_count"] = int(count)

    return counts


def get_node_links_for_node(db, node_id: str, viewer_player_id: int | None = None, is_admin: bool = False) -> dict:
    from .database import NodeLink

    base_query = db.query(NodeLink).options(
        joinedload(NodeLink.submitted_by),
        joinedload(NodeLink.reviewed_by),
    ).filter(
        NodeLink.node_id == node_id,
        NodeLink.is_active.is_(True),
    )

    authoritative_links = base_query.filter(
        NodeLink.source_kind == SOURCE_AUTHORITATIVE,
        NodeLink.review_status == REVIEW_APPROVED,
    ).order_by(NodeLink.sort_order.asc(), NodeLink.created_at.asc()).all()

    approved_user_links = base_query.filter(
        NodeLink.source_kind == SOURCE_USER,
        NodeLink.review_status == REVIEW_APPROVED,
    ).order_by(NodeLink.sort_order.asc(), NodeLink.created_at.desc()).all()

    pending_query = base_query.filter(
        NodeLink.source_kind == SOURCE_USER,
        NodeLink.review_status == REVIEW_PENDING,
    ).order_by(NodeLink.created_at.desc())
    if not is_admin and viewer_player_id is not None:
        pending_query = pending_query.filter(NodeLink.submitted_by_player_id == viewer_player_id)
    elif not is_admin:
        pending_query = pending_query.filter(NodeLink.id == -1)

    pending_user_links = pending_query.all()

    return {
        "authoritative_links": [serialize_node_link(link) for link in authoritative_links],
        "approved_user_links": [serialize_node_link(link) for link in approved_user_links],
        "pending_user_links": [serialize_node_link(link) for link in pending_user_links],
        "is_admin": is_admin,
    }


def submit_node_link(
    db,
    *,
    submitted_by_player_id: int,
    node_id: str,
    topic: str | None,
    title: str,
    url: str,
    description: str | None,
    provider: str | None,
    link_type: str | None,
    extra_metadata: dict | None = None,
):
    from .database import NodeLink

    cleaned_node_id = (node_id or "").strip()
    cleaned_title = (title or "").strip()
    if not cleaned_node_id or not cleaned_title:
        raise HTTPException(status_code=400, detail="Node ID and link title are required.")

    normalized_url = normalize_node_link_url(url)
    duplicate = db.query(NodeLink).filter(
        NodeLink.node_id == cleaned_node_id,
        NodeLink.url == normalized_url,
        NodeLink.is_active.is_(True),
        NodeLink.review_status.in_([REVIEW_PENDING, REVIEW_APPROVED]),
    ).first()
    if duplicate:
        raise HTTPException(status_code=400, detail="This node already has that link.")

    now = datetime.utcnow()
    link = NodeLink(
        node_id=cleaned_node_id,
        subject_key=_normalize_subject_key(topic),
        title=cleaned_title,
        url=normalized_url,
        description=(description or "").strip() or None,
        provider=(provider or "").strip() or _infer_provider(normalized_url),
        link_type=_normalize_link_type(link_type),
        source_kind=SOURCE_USER,
        review_status=REVIEW_PENDING,
        is_active=True,
        sort_order=0,
        extra_metadata=_normalize_extra_metadata(extra_metadata),
        submitted_by_player_id=submitted_by_player_id,
        created_at=now,
        updated_at=now,
    )
    db.add(link)
    db.flush()
    return link


def review_node_link(
    db,
    *,
    link_id: int,
    reviewed_by_player_id: int,
    review_status: str,
    review_notes: str | None = None,
    is_active: bool | None = None,
    sort_order: int | None = None,
):
    from .database import NodeLink

    link = db.query(NodeLink).filter(NodeLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Node link not found.")

    link.review_status = normalize_review_status(review_status)
    link.review_notes = (review_notes or "").strip() or None
    link.reviewed_by_player_id = reviewed_by_player_id
    link.reviewed_at = datetime.utcnow()
    link.updated_at = link.reviewed_at
    if is_active is not None:
        link.is_active = bool(is_active)
    if sort_order is not None:
        link.sort_order = int(sort_order)
    db.flush()
    return link


def list_reviewable_node_links(db, review_status: str | None = None, node_id: str | None = None) -> list[dict]:
    from .database import NodeLink

    query = db.query(NodeLink).options(
        joinedload(NodeLink.submitted_by),
        joinedload(NodeLink.reviewed_by),
    ).filter(NodeLink.source_kind == SOURCE_USER)
    if review_status:
        query = query.filter(NodeLink.review_status == normalize_review_status(review_status))
    if node_id:
        query = query.filter(NodeLink.node_id == node_id)

    links = query.order_by(NodeLink.created_at.desc(), NodeLink.id.desc()).all()
    return [serialize_node_link(link) for link in links]
