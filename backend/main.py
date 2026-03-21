from fastapi import FastAPI, HTTPException, Depends, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from sqlalchemy import or_
from sqlalchemy.orm import Session
from contextlib import asynccontextmanager
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from .models import InitRequest, ChatRequest, ChatResponse, BookSelectRequest, BookSelectResponse, InitSessionRequest, InitSessionResponse, ResumeShelfRequest, ResumeShelfResponse, PlayerStatsRequest, GraphDataRequest, GraphDataResponse, GraphNode, SetCurrentNodeRequest, RegisterRequest, LoginRequest, LogoutRequest, PasswordResetRequest, ProfileRequest, UpdateProfileRequest, ProfileResponse, TeacherLinkRequest, TeacherLinkListRequest, TeacherLinkActionRequest, TeacherLinkRevokeRequest, TeacherStudentProgressRequest, TeacherLinkSummary, TeacherLinkListResponse, TeacherDashboardResponse, TeacherStudentProgressResponse, TeacherStudentSummary, StudentTopicProgressSummary, StudentNodeProgressSummary, StudentActivitySessionSummary, HostedModelConfigRequest, UpdateHostedModelConfigRequest, HostedModelOptionSummary, HostedModelConfigResponse, BillingStatusRequest, BillingCheckoutRequest, BillingPortalRequest, BillingStatusResponse, BillingCheckoutResponse, BillingPortalResponse, RedeemAccessCodeRequest, RedeemAccessCodeResponse, CreatePromoCodeRequest, CreatePromoCodeResponse, GrantAccessRequest, RevokeAccessGrantRequest, RevokePromoCodeRequest, ListAccessGrantsRequest, ListPromoCodesRequest, AccessGrantSummary, PromoCodeSummary, AccessGrantListResponse, PromoCodeListResponse, NodeLinksRequest, NodeLinksResponse, SubmitNodeLinkRequest, SubmitNodeLinkResponse, ReviewNodeLinkRequest, PendingNodeLinksRequest, PendingNodeLinksResponse, NodeLinkSummary
from .graph import create_graph
from .database import init_db, get_db, Player, TopicProgress, AuthSession, apply_player_defaults
from .config import load_local_env, normalize_avatar_id, normalize_account_status
from .profile_security import encrypt_profile_secret, mask_secret
from .billing import build_billing_status, build_hosted_model_config, create_checkout_session as create_billing_checkout_session, create_billing_portal_session, handle_stripe_webhook, assert_tutoring_access, increment_tutor_turn_usage, set_hosted_models
from .access_grants import create_manual_access_grant, create_promo_code, list_access_grants, list_promo_codes, redeem_promo_code, revoke_access_grant, revoke_promo_code, serialize_access_grant, serialize_promo_code
from .node_links import get_node_link_count_map, get_node_links_for_node, list_reviewable_node_links, review_node_link, serialize_node_link, submit_node_link
from .knowledge_tracing import (
    KNOWLEDGE_TRACING_MODE,
    TEACH_ME_MODE,
    canonical_subject_for_topic,
    get_subject_full_mastery_node_ids,
    get_topic_progress as get_mode_topic_progress,
    is_knowledge_tracing_mode,
    learning_mode_label,
    normalize_learning_mode,
    resolve_topic_for_mode,
    select_next_teach_me_node,
    select_next_tracing_node,
    topic_label_for_mode,
)
from .student_tracking import end_activity_session, record_topic_session_start, start_activity_session, touch_activity_session, touch_current_node
from .teacher_portal import assert_teacher_can_view_student, build_student_progress_detail, create_teacher_request, get_teacher_dashboard_payload, list_teacher_links_for_user, respond_to_teacher_request, revoke_teacher_link, serialize_teacher_link
import uuid
import json
from fastapi.responses import HTMLResponse
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi.security import OAuth2PasswordBearer
import smtplib
import ssl
import os
import html
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

try:
    from passlib.context import CryptContext
except ImportError:
    import bcrypt

    class CryptContext:  # type: ignore[override]
        def __init__(self, schemes=None, deprecated="auto"):
            self.schemes = schemes or ["bcrypt"]
            self.deprecated = deprecated

        def verify(self, plain_password, hashed_password):
            if not plain_password or not hashed_password:
                return False
            return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

        def hash(self, password):
            return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

load_local_env()

# Auth Setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# IMPORTANT: In production, this must be set via environment variable.
# We default to a placeholder for local dev but advise handling this carefully.
SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key_change_me") 
ALGORITHM = "HS256"
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SELF_SERVICE_ROLES = {"Student", "Teacher"}
ADMIN_ROLE = "Admin"


def _cors_allowed_origins() -> list[str]:
    configured = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if configured:
        return [origin.strip() for origin in configured.split(",") if origin.strip()]
    return [
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "https://adaptivetutor.ai",
        "https://www.adaptivetutor.ai",
    ]

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_reset_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def _is_valid_email(value: str) -> bool:
    trimmed = value.strip()
    if "@" not in trimmed:
        return False
    local_part, _, domain = trimmed.partition("@")
    return bool(local_part and domain and "." in domain)


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _topic_metadata_from_name(topic_name: str | None) -> tuple[str | None, int | None]:
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

    level_match = re.search(r"(\d+)", topic_name)
    level_value = int(level_match.group(1)) if level_match else None
    return subject_key, level_value


def _apply_topic_progress_metadata(progress: TopicProgress, topic_name: str):
    subject_key, level_value = _topic_metadata_from_name(topic_name)
    if subject_key:
        progress.subject_key = subject_key
    if level_value is not None:
        progress.book_level = level_value
        progress.content_grade_level = level_value


def _resolved_learning_mode(mode_value: str | None) -> str:
    return normalize_learning_mode(mode_value)


def _resolved_topic_name(topic_name: str, learning_mode: str) -> str:
    return resolve_topic_for_mode(topic_name, learning_mode)


def _session_target_grade(
    player: Player,
    requested_topic: str,
    learning_mode: str,
    session_grade_level: int | None = None,
) -> int:
    if session_grade_level is not None:
        return int(session_grade_level)

    if is_knowledge_tracing_mode(learning_mode):
        return int(player.grade_level or 0)

    topic_grade_match = re.search(r"\d+", requested_topic or "")
    if topic_grade_match:
        try:
            return int(topic_grade_match.group())
        except ValueError:
            return int(player.grade_level or 0)
    return int(player.grade_level or 0)


def _build_navigation_snapshot(
    db: Session,
    player: Player,
    topic_name: str,
    learning_mode: str,
    target_grade: int | None,
) -> dict:
    from .knowledge_graph import get_graph

    snapshot: dict = {"current_action": "IDLE", "learning_mode": learning_mode}
    progress = get_mode_topic_progress(db, player.id, topic_name, learning_mode)
    if not progress:
        return snapshot

    snapshot["mastery"] = progress.mastery_score
    snapshot["mastery_level"] = int(progress.mastery_level or 0)
    snapshot["topic_label"] = topic_label_for_mode(topic_name, learning_mode)

    kg = get_graph(topic_name)
    if progress.current_node:
        current_node = kg.get_node(progress.current_node)
        if current_node:
            snapshot["current_node_label"] = current_node.label

    completed_nodes = list(progress.completed_nodes) if progress.completed_nodes else []
    if completed_nodes:
        previous_node = kg.get_node(completed_nodes[-1])
        if previous_node:
            snapshot["prev_node_label"] = previous_node.label

    next_node = None
    if is_knowledge_tracing_mode(learning_mode):
        next_node = select_next_tracing_node(
            db,
            player_id=player.id,
            topic_name=topic_name,
            target_grade=target_grade,
            current_node_id=progress.current_node,
        )
    else:
        next_node = select_next_teach_me_node(
            db,
            player_id=player.id,
            topic_name=topic_name,
            target_grade=target_grade,
            current_node_id=progress.current_node,
        )

    if next_node:
        snapshot["next_node_label"] = next_node.label

    return snapshot


def _build_profile_response(player: Player) -> ProfileResponse:
    return ProfileResponse(
        username=player.username,
        display_name=player.display_name,
        email=player.email,
        avatar_id=normalize_avatar_id(player.avatar_id),
        has_personal_openai_key=bool(player.openai_api_key_encrypted),
        openai_key_hint=mask_secret(player.openai_api_key_encrypted),
        account_status=normalize_account_status(player.account_status),
        curriculum_region=player.curriculum_region,
        preferred_model=player.preferred_model,
        school_name=player.school_name,
        district_name=player.district_name,
        classroom_id=player.classroom_id,
        roster_id=player.roster_id,
        guardian_name=player.guardian_name,
        guardian_email=player.guardian_email,
        created_at=player.created_at,
        updated_at=player.updated_at,
        last_login_at=player.last_login_at,
        email_verified_at=player.email_verified_at,
        password_changed_at=player.password_changed_at,
        last_password_reset_requested_at=player.last_password_reset_requested_at,
        openai_api_key_updated_at=player.openai_api_key_updated_at,
    )


def _get_player_by_username(db: Session, username: str) -> Player:
    player = db.query(Player).filter(Player.username == username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")
    return player


def _ensure_player_runtime_defaults(db: Session, player: Player) -> None:
    if player is None:
        return
    if apply_player_defaults(player):
        player.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(player)


def _resolve_expiration(expires_at: datetime | None, duration_days: int | None) -> datetime | None:
    if expires_at is not None:
        return expires_at
    if duration_days is None:
        return None
    if duration_days < 1:
        raise HTTPException(status_code=400, detail="duration_days must be at least 1.")
    return datetime.utcnow() + timedelta(days=duration_days)


def _ensure_current_user_matches(current_user: Player, username: str):
    if current_user.username != username:
        raise HTTPException(status_code=403, detail="Profile access denied")


def _admin_usernames() -> set[str]:
    return {
        username.strip()
        for username in os.getenv("ADMIN_USERNAMES", "").split(",")
        if username.strip()
    }


def _is_admin_user(player: Player | None) -> bool:
    if not player:
        return False
    return (player.role or "").strip() == ADMIN_ROLE or player.username in _admin_usernames()


def _is_teacher_like_user(player: Player | None) -> bool:
    if not player:
        return False
    return (player.role or "").strip() == "Teacher" or _is_admin_user(player)


def _effective_learning_role(player: Player | None) -> str:
    return "Teacher" if _is_teacher_like_user(player) else "Student"


def _ensure_admin_user(player: Player):
    if not _is_admin_user(player):
        raise HTTPException(status_code=403, detail="Administrator access required")


def _ensure_teacher_or_admin_user(player: Player):
    if not _is_teacher_like_user(player):
        raise HTTPException(status_code=403, detail="Teacher access required")


def _normalize_user_role(role: str | None, allow_admin: bool = False) -> str:
    normalized = (role or "Student").strip().lower()
    role_map = {"student": "Student", "teacher": "Teacher", "admin": "Admin"}
    resolved = role_map.get(normalized, "Student")
    if resolved == ADMIN_ROLE and not allow_admin:
        raise HTTPException(status_code=403, detail="Administrator role cannot be self-assigned.")
    return resolved if resolved in SELF_SERVICE_ROLES or resolved == ADMIN_ROLE else "Student"


def _record_auth_session(
    db: Session,
    player: Player,
    token_jti: str,
    expires_at: datetime,
    http_request: Request | None = None,
):
    if not token_jti:
        return

    auth_session = AuthSession(
        player_id=player.id,
        token_jti=token_jti,
        user_agent=http_request.headers.get("user-agent") if http_request else None,
        ip_address=http_request.client.host if http_request and http_request.client else None,
        created_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
        expires_at=expires_at,
    )
    db.add(auth_session)


def _update_auth_session_last_seen(db: Session, current_user: Player):
    token_jti = getattr(current_user, "_token_jti", None)

    if token_jti:
        auth_session = db.query(AuthSession).filter(AuthSession.token_jti == token_jti).first()
        if auth_session:
            auth_session.last_seen_at = datetime.utcnow()

    touch_activity_session(
        db,
        current_user,
        token_jti=token_jti,
        increment_request=True,
    )


def _extract_usage_metrics(message) -> tuple[int | None, int | None]:
    if message is None:
        return None, None

    usage = getattr(message, "usage_metadata", None) or {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")

    response_metadata = getattr(message, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage", {})
    if input_tokens is None:
        input_tokens = token_usage.get("prompt_tokens")
    if output_tokens is None:
        output_tokens = token_usage.get("completion_tokens")

    return input_tokens, output_tokens

# Real Email Sender (IONOS SMTP)
# Real Email Sender (IONOS SMTP)
def send_email_reset_link(to_email: str, link: str):
    smtp_server = os.getenv("EMAIL_HOST", "smtp.ionos.com")
    smtp_port_str = os.getenv("EMAIL_PORT", "587")
    sender_email = os.getenv("EMAIL_USER", "admin@adaptivetutor.ai")
    password = os.getenv("EMAIL_PASSWORD")
    
    # Check if critical vars are present
    if not smtp_server or not sender_email or not password:
        print("[SMTP] EMAIL_HOST/USER/PASSWORD not set. Falling back to Mock.")
        send_email_mock(to_email, link)
        return

    smtp_port = int(smtp_port_str)
    
    if not password:
        print("[SMTP] No EMAIL_PASSWORD set. Falling back to Mock.")
        send_email_mock(to_email, link)
        return

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = "Password Reset Request - Adaptive Tutor"
        message["From"] = sender_email
        message["To"] = to_email

        text = f"""\
Hi,

You requested a password reset for Adaptive Tutor.
Please click the link below to set a new password:

{link}

If you did not request this, please ignore this email.
"""
        html = f"""\
<html>
  <body>
    <p>Hi,</p>
    <p>You requested a password reset for <b>Adaptive Tutor</b>.</p>
    <p>Please click the link below to set a new password:</p>
    <p><a href="{link}">Reset Password</a></p>
    <br>
    <p>If you did not request this, please ignore this email.</p>
  </body>
</html>
"""

        part1 = MIMEText(text, "plain")
        part2 = MIMEText(html, "html")
        message.attach(part1)
        message.attach(part2)

        context = ssl.create_default_context()
        print(f"[SMTP] Connecting to {smtp_server}:{smtp_port}...")
        
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(context=context)
            server.login(sender_email, password)
            server.sendmail(sender_email, to_email, message.as_string())
            
        print(f"[SMTP] Email sent successfully to {to_email}")

    except Exception as e:
        print(f"[SMTP] Error sending email: {e}")
        # Build robustness: fall back to printing link so user isn't stuck during testing
        send_email_mock(to_email, link)

# Mock Email Sender (Fallback)
def send_email_mock(email: str, link: str):
    print(f"\n[MOCK EMAIL SERVICE] To: {email}")
    print(f"Subject: Password Reset Request")
    print(f"Body: Click here to reset your password: {link}\n")

# Global graph instance
graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global graph
    init_db()
    checkpointer = MemorySaver()
    builder = create_graph()
    graph = builder.compile(checkpointer=checkpointer)
    print("Graph compiled with MemorySaver.")
    yield
    print("Shutting down.")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth Configuration
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
ACCESS_TOKEN_EXPIRE_MINUTES = 60 # Extended to 60 as requested

async def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    token_jti = payload.get("jti")
    user = db.query(Player).filter(Player.username == username).first()
    if user is None:
        raise credentials_exception
    if token_jti:
        auth_session = db.query(AuthSession).filter(AuthSession.token_jti == token_jti).first()
        if (
            auth_session is None
            or auth_session.player_id != user.id
            or auth_session.revoked_at is not None
            or (auth_session.expires_at and auth_session.expires_at < datetime.utcnow())
        ):
            raise credentials_exception
    user._token_jti = token_jti
    return user

@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "ok", "message": "Adaptive Learning Backend is running"}

@app.get("/get_users", response_model=List[str])
async def get_users_list(db: Session = Depends(get_db)):
    from .database import get_all_users
    return get_all_users()

@app.post("/get_player_stats")
async def get_player_stats(request: PlayerStatsRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    from .knowledge_graph import get_all_subjects_stats, get_subject_completion_stats

    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        return {"stats": {}}
    _ensure_player_runtime_defaults(db, player)

    stats = {}
    subjects = ["Math", "Science", "Social_Studies", "ELA"]

    for subj in subjects:
        done, total = get_subject_completion_stats(player.id, db, subj)
        percent = round((done / total) * 100, 1) if total > 0 else 0.0
        stats[subj] = percent

    done_grade, total_grade = get_all_subjects_stats(player.id, db)
    grade_percent = round((done_grade / total_grade) * 100, 1) if total_grade > 0 else 0.0

    stats["grade_completion"] = grade_percent
    stats["current_grade_level"] = player.grade_level
    stats["role"] = _effective_learning_role(player)
    stats["avatar_id"] = normalize_avatar_id(player.avatar_id)
    stats["has_personal_openai_key"] = bool(player.openai_api_key_encrypted)
    stats["openai_key_hint"] = mask_secret(player.openai_api_key_encrypted)
    stats["display_name"] = player.display_name or player.username
    stats["curriculum_region"] = player.curriculum_region
    stats["is_admin"] = _is_admin_user(player)
    return {"stats": stats}

@app.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)):
    print(f"[API] /register request received for: {request.username}")
    now = datetime.utcnow()
    cleaned_username = request.username.strip()
    cleaned_email = request.email.strip()

    existing = db.query(Player).filter(Player.username == cleaned_username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already registered")

    if not _is_valid_email(cleaned_email):
        raise HTTPException(status_code=400, detail="A valid email is required for password recovery.")
    if len(request.password.strip()) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    guardian_email = _clean_optional_text(request.guardian_email)
    if guardian_email and not _is_valid_email(guardian_email):
        raise HTTPException(status_code=400, detail="Guardian email must be a valid email address.")

    openai_key = _clean_optional_text(request.openai_api_key)
    hashed_pwd = get_password_hash(request.password)
    player = Player(
        username=cleaned_username,
        password_hash=hashed_pwd,
        email=cleaned_email,
        display_name=_clean_optional_text(request.display_name) or cleaned_username,
        grade_level=request.grade_level,
        location=request.location,
        curriculum_region=_clean_optional_text(request.curriculum_region) or request.location,
        learning_style=request.learning_style,
        sex=request.sex,
        role=_normalize_user_role(request.role),
        birthday=request.birthday,
        interests=request.interests,
        avatar_id=normalize_avatar_id(request.avatar_id),
        openai_api_key_encrypted=encrypt_profile_secret(openai_key),
        preferred_model=_clean_optional_text(request.preferred_model),
        school_name=_clean_optional_text(request.school_name),
        district_name=_clean_optional_text(request.district_name),
        classroom_id=_clean_optional_text(request.classroom_id),
        roster_id=_clean_optional_text(request.roster_id),
        guardian_name=_clean_optional_text(request.guardian_name),
        guardian_email=guardian_email,
        created_at=now,
        updated_at=now,
        password_changed_at=now,
        openai_api_key_updated_at=now if openai_key else None,
    )
    db.add(player)
    db.commit()
    return {"message": "User created successfully"}


@app.post("/get_profile", response_model=ProfileResponse)
async def get_profile(request: ProfileRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")
    _ensure_player_runtime_defaults(db, player)
    return _build_profile_response(player)


@app.post("/get_billing_status", response_model=BillingStatusResponse)
async def get_billing_status(request: BillingStatusRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")
    return BillingStatusResponse(**build_billing_status(db, player))


@app.post("/create_checkout_session", response_model=BillingCheckoutResponse)
async def create_checkout_session(request: BillingCheckoutRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")
    url = create_billing_checkout_session(db, player, request.plan_code)
    return BillingCheckoutResponse(url=url)


@app.post("/create_billing_portal_session", response_model=BillingPortalResponse)
async def create_billing_portal(request: BillingPortalRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")
    url = create_billing_portal_session(db, player)
    return BillingPortalResponse(url=url)


@app.post("/redeem_access_code", response_model=RedeemAccessCodeResponse)
async def redeem_access_code_endpoint(request: RedeemAccessCodeRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = _get_player_by_username(db, request.username)
    _, grant, created = redeem_promo_code(db, player, request.code)
    db.commit()
    db.refresh(grant)
    return RedeemAccessCodeResponse(
        status="redeemed" if created else "already_active",
        plan_code=grant.plan_code,
        access_source_type=grant.source_type,
        expires_at=grant.expires_at,
        message="Access code accepted." if created else "Access code was already active for this user.",
    )


@app.post("/admin/create_access_code", response_model=CreatePromoCodeResponse)
async def admin_create_access_code(request: CreatePromoCodeRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    assigned_player = _get_player_by_username(db, request.assigned_username) if request.assigned_username else None
    expires_at = _resolve_expiration(request.expires_at, request.duration_days)
    promo_code, raw_code = create_promo_code(
        db,
        plan_code=request.plan_code,
        assigned_player_id=assigned_player.id if assigned_player else None,
        created_by_player_id=current_user.id,
        starts_at=request.starts_at,
        expires_at=expires_at,
        max_redemptions=request.max_redemptions,
        raw_code=request.code,
        notes=_clean_optional_text(request.notes),
        extra_metadata=request.extra_metadata,
    )
    db.commit()
    db.refresh(promo_code)
    return CreatePromoCodeResponse(
        promo_code=PromoCodeSummary(**serialize_promo_code(promo_code)),
        code=raw_code,
    )


@app.post("/admin/grant_access", response_model=AccessGrantSummary)
async def admin_grant_access(request: GrantAccessRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    target_player = _get_player_by_username(db, request.target_username)
    expires_at = _resolve_expiration(request.expires_at, request.duration_days)
    grant = create_manual_access_grant(
        db,
        player_id=target_player.id,
        plan_code=request.plan_code,
        created_by_player_id=current_user.id,
        starts_at=request.starts_at,
        expires_at=expires_at,
        notes=_clean_optional_text(request.notes),
        extra_metadata=request.extra_metadata,
    )
    db.commit()
    db.refresh(grant)
    return AccessGrantSummary(**serialize_access_grant(grant))


@app.post("/admin/get_hosted_model_config", response_model=HostedModelConfigResponse)
async def admin_get_hosted_model_config(request: HostedModelConfigRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    payload = build_hosted_model_config(db)
    return HostedModelConfigResponse(
        teacher_model=payload["teacher_model"],
        verifier_model=payload["verifier_model"],
        main_model=payload["main_model"],
        fast_model=payload["fast_model"],
        teacher_priority_enabled=payload.get("teacher_priority_enabled", False),
        verifier_priority_enabled=payload.get("verifier_priority_enabled", False),
        fast_priority_enabled=payload.get("fast_priority_enabled", False),
        main_priority_enabled=payload.get("main_priority_enabled", payload.get("teacher_priority_enabled", False)),
        teacher_provider=payload["teacher_provider"],
        verifier_provider=payload["verifier_provider"],
        main_provider=payload["main_provider"],
        fast_provider=payload["fast_provider"],
        teacher_display_name=payload.get("teacher_display_name"),
        verifier_display_name=payload.get("verifier_display_name"),
        main_display_name=payload.get("main_display_name"),
        fast_display_name=payload.get("fast_display_name"),
        catalog=[HostedModelOptionSummary(**entry) for entry in payload.get("catalog", [])],
    )


@app.post("/admin/set_hosted_model_config", response_model=HostedModelConfigResponse)
async def admin_set_hosted_model_config(request: UpdateHostedModelConfigRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    teacher_model = (request.teacher_model or request.main_model or "").strip()
    verifier_model = (request.verifier_model or teacher_model).strip()
    teacher_priority_enabled = request.teacher_priority_enabled
    if request.main_priority_enabled is not None:
        teacher_priority_enabled = request.main_priority_enabled

    payload = set_hosted_models(
        db,
        teacher_model,
        verifier_model,
        request.fast_model,
        teacher_priority_enabled=teacher_priority_enabled,
        verifier_priority_enabled=request.verifier_priority_enabled,
        fast_priority_enabled=request.fast_priority_enabled,
        updated_by_player_id=current_user.id,
    )
    db.commit()
    return HostedModelConfigResponse(
        teacher_model=payload["teacher_model"],
        verifier_model=payload["verifier_model"],
        main_model=payload["main_model"],
        fast_model=payload["fast_model"],
        teacher_priority_enabled=payload.get("teacher_priority_enabled", False),
        verifier_priority_enabled=payload.get("verifier_priority_enabled", False),
        fast_priority_enabled=payload.get("fast_priority_enabled", False),
        main_priority_enabled=payload.get("main_priority_enabled", payload.get("teacher_priority_enabled", False)),
        teacher_provider=payload["teacher_provider"],
        verifier_provider=payload["verifier_provider"],
        main_provider=payload["main_provider"],
        fast_provider=payload["fast_provider"],
        teacher_display_name=payload.get("teacher_display_name"),
        verifier_display_name=payload.get("verifier_display_name"),
        main_display_name=payload.get("main_display_name"),
        fast_display_name=payload.get("fast_display_name"),
        catalog=[HostedModelOptionSummary(**entry) for entry in payload.get("catalog", [])],
    )


@app.post("/admin/revoke_access_grant", response_model=AccessGrantSummary)
async def admin_revoke_access_grant(request: RevokeAccessGrantRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    grant = revoke_access_grant(db, request.access_grant_id, reason=_clean_optional_text(request.reason))
    db.commit()
    db.refresh(grant)
    return AccessGrantSummary(**serialize_access_grant(grant))


@app.post("/admin/revoke_access_code", response_model=PromoCodeSummary)
async def admin_revoke_access_code(request: RevokePromoCodeRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    promo_code = revoke_promo_code(
        db,
        request.promo_code_id,
        reason=_clean_optional_text(request.reason),
        revoke_linked_grants=bool(request.revoke_grants),
    )
    db.commit()
    db.refresh(promo_code)
    return PromoCodeSummary(**serialize_promo_code(promo_code))


@app.post("/admin/list_access_grants", response_model=AccessGrantListResponse)
async def admin_list_access_grants(request: ListAccessGrantsRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    target_player = _get_player_by_username(db, request.target_username) if request.target_username else None
    grants = list_access_grants(
        db,
        player_id=target_player.id if target_player else None,
        include_revoked=request.include_revoked,
    )
    return AccessGrantListResponse(grants=[AccessGrantSummary(**serialize_access_grant(grant)) for grant in grants])


@app.post("/admin/list_access_codes", response_model=PromoCodeListResponse)
async def admin_list_access_codes(request: ListPromoCodesRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)

    assigned_player = _get_player_by_username(db, request.assigned_username) if request.assigned_username else None
    promo_codes = list_promo_codes(
        db,
        assigned_player_id=assigned_player.id if assigned_player else None,
        include_revoked=request.include_revoked,
    )
    return PromoCodeListResponse(
        promo_codes=[PromoCodeSummary(**serialize_promo_code(promo_code)) for promo_code in promo_codes]
    )


@app.post("/update_profile", response_model=ProfileResponse)
async def update_profile(request: UpdateProfileRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")

    guardian_email = _clean_optional_text(request.guardian_email)
    if guardian_email and not _is_valid_email(guardian_email):
        raise HTTPException(status_code=400, detail="Guardian email must be a valid email address.")

    now = datetime.utcnow()
    if request.display_name is not None:
        player.display_name = _clean_optional_text(request.display_name) or player.username
    if request.email is not None:
        trimmed_email = request.email.strip()
        if trimmed_email and not _is_valid_email(trimmed_email):
            raise HTTPException(status_code=400, detail="Please enter a valid email address.")
        player.email = trimmed_email or None
    if request.avatar_id is not None:
        player.avatar_id = normalize_avatar_id(request.avatar_id)
    if request.curriculum_region is not None:
        player.curriculum_region = _clean_optional_text(request.curriculum_region)
    if request.preferred_model is not None:
        player.preferred_model = _clean_optional_text(request.preferred_model)
    if request.school_name is not None:
        player.school_name = _clean_optional_text(request.school_name)
    if request.district_name is not None:
        player.district_name = _clean_optional_text(request.district_name)
    if request.classroom_id is not None:
        player.classroom_id = _clean_optional_text(request.classroom_id)
    if request.roster_id is not None:
        player.roster_id = _clean_optional_text(request.roster_id)
    if request.guardian_name is not None:
        player.guardian_name = _clean_optional_text(request.guardian_name)
    if request.guardian_email is not None:
        player.guardian_email = guardian_email

    if request.clear_openai_api_key:
        player.openai_api_key_encrypted = None
        player.openai_api_key_updated_at = now
    elif request.openai_api_key is not None:
        trimmed_key = request.openai_api_key.strip()
        if trimmed_key:
            player.openai_api_key_encrypted = encrypt_profile_secret(trimmed_key)
            player.openai_api_key_updated_at = now

    player.updated_at = now
    db.commit()
    db.refresh(player)
    return _build_profile_response(player)


@app.post("/request_teacher_link", response_model=TeacherLinkSummary)
async def request_teacher_link(request: TeacherLinkRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    student = _get_player_by_username(db, request.username)
    link = create_teacher_request(
        db,
        student=student,
        teacher_username=request.teacher_username,
        request_note=_clean_optional_text(request.request_note),
    )
    db.commit()
    db.refresh(link)
    return TeacherLinkSummary(**serialize_teacher_link(link))


@app.post("/list_teacher_links", response_model=TeacherLinkListResponse)
async def list_teacher_links(request: TeacherLinkListRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    links = list_teacher_links_for_user(db, current_user)
    return TeacherLinkListResponse(links=[TeacherLinkSummary(**serialize_teacher_link(link)) for link in links])


@app.post("/respond_teacher_link", response_model=TeacherLinkSummary)
async def respond_teacher_link(request: TeacherLinkActionRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_teacher_or_admin_user(current_user)

    link = respond_to_teacher_request(
        db,
        teacher=current_user,
        link_id=request.link_id,
        action=request.action,
        response_note=_clean_optional_text(request.response_note),
    )
    db.commit()
    db.refresh(link)
    return TeacherLinkSummary(**serialize_teacher_link(link))


@app.post("/revoke_teacher_link", response_model=TeacherLinkSummary)
async def revoke_teacher_link_endpoint(request: TeacherLinkRevokeRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    link = revoke_teacher_link(
        db,
        actor=current_user,
        link_id=request.link_id,
        reason=_clean_optional_text(request.reason),
    )
    db.commit()
    db.refresh(link)
    return TeacherLinkSummary(**serialize_teacher_link(link))


@app.post("/teacher_dashboard", response_model=TeacherDashboardResponse)
async def teacher_dashboard(request: TeacherLinkListRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_teacher_or_admin_user(current_user)

    payload = get_teacher_dashboard_payload(db, current_user)
    return TeacherDashboardResponse(
        pending_requests=[TeacherLinkSummary(**row) for row in payload["pending_requests"]],
        accepted_students=[TeacherStudentSummary(**row) for row in payload["accepted_students"]],
    )


@app.post("/teacher_student_progress", response_model=TeacherStudentProgressResponse)
async def teacher_student_progress(request: TeacherStudentProgressRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_teacher_or_admin_user(current_user)

    student = _get_player_by_username(db, request.student_username)
    teacher_link = assert_teacher_can_view_student(db, current_user, student)
    payload = build_student_progress_detail(db, student, teacher_link=teacher_link)
    return TeacherStudentProgressResponse(
        teacher_link=TeacherLinkSummary(**payload["teacher_link"]) if payload["teacher_link"] else None,
        student=TeacherStudentSummary(**payload["student"]),
        topics=[StudentTopicProgressSummary(**row) for row in payload["topics"]],
        nodes=[StudentNodeProgressSummary(**row) for row in payload["nodes"]],
        recent_sessions=[StudentActivitySessionSummary(**row) for row in payload["recent_sessions"]],
    )


@app.post("/get_node_links", response_model=NodeLinksResponse)
async def get_node_links(request: NodeLinksRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    payload = get_node_links_for_node(
        db,
        request.node_id,
        viewer_player_id=current_user.id,
        is_admin=_is_admin_user(current_user),
    )
    return NodeLinksResponse(**payload)


@app.post("/submit_node_link", response_model=SubmitNodeLinkResponse)
async def submit_node_link_endpoint(request: SubmitNodeLinkRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    link = submit_node_link(
        db,
        submitted_by_player_id=current_user.id,
        node_id=request.node_id,
        topic=request.topic,
        title=request.title,
        url=request.url,
        description=request.description,
        provider=request.provider,
        link_type=request.link_type,
        extra_metadata=request.extra_metadata,
    )
    db.commit()
    db.refresh(link)
    return SubmitNodeLinkResponse(status="pending_review", link=NodeLinkSummary(**serialize_node_link(link)))


@app.post("/admin/list_node_links", response_model=PendingNodeLinksResponse)
async def admin_list_node_links(request: PendingNodeLinksRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)
    links = list_reviewable_node_links(db, review_status=request.review_status, node_id=request.node_id)
    return PendingNodeLinksResponse(links=[NodeLinkSummary(**link) for link in links])


@app.post("/admin/review_node_link", response_model=NodeLinkSummary)
async def admin_review_node_link(request: ReviewNodeLinkRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    _ensure_admin_user(current_user)
    link = review_node_link(
        db,
        link_id=request.link_id,
        reviewed_by_player_id=current_user.id,
        review_status=request.review_status,
        review_notes=request.review_notes,
        is_active=request.is_active,
        sort_order=request.sort_order,
    )
    db.commit()
    db.refresh(link)
    return NodeLinkSummary(**serialize_node_link(link))


@app.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    handle_stripe_webhook(db, payload, signature)
    return {"status": "ok"}


@app.get("/billing/success", response_class=HTMLResponse)
async def billing_success():
    return HTMLResponse(content="<h2>Subscription Started</h2><p>Your billing setup was completed. You can return to Adaptive Tutor and refresh your profile.</p>")


@app.get("/billing/cancel", response_class=HTMLResponse)
async def billing_cancel():
    return HTMLResponse(content="<h2>Checkout Cancelled</h2><p>No changes were made to your subscription. You can return to Adaptive Tutor.</p>")


@app.get("/billing/manage-return", response_class=HTMLResponse)
async def billing_manage_return():
    return HTMLResponse(content="<h2>Billing Updated</h2><p>Your subscription settings were updated. You can return to Adaptive Tutor and refresh your profile.</p>")

@app.post("/request-password-reset")
async def request_password_reset(request: PasswordResetRequest, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.username == request.username).first()
    if not player or not player.email:
        # Don't reveal if user exists? For internal app usually mostly fine, but best practice is generic message.
        # "If user exists, email sent".
        return {"message": "If username exists with an email, a reset link has been sent."}
    
    now = datetime.utcnow()
    player.last_password_reset_requested_at = now
    player.updated_at = now
    db.commit()

    token = create_reset_token({"sub": player.username})
    reset_link = f"{PUBLIC_BASE_URL}/reset-password?token={token}"
    send_email_reset_link(player.email, reset_link)
    return {"message": "If username exists with an email, a reset link has been sent."}

@app.get("/reset-password", response_class=HTMLResponse)
async def reset_password_form(token: str):
    safe_token = html.escape(token, quote=True)
    return f"""
    <html>
        <head>
            <title>Reset Password</title>
            <style>
                body {{ font-family: sans-serif; max-width: 400px; margin: 40px auto; padding: 20px; }}
                input {{ width: 100%; padding: 10px; margin-bottom: 10px; }}
                button {{ width: 100%; padding: 10px; background: #007bff; color: white; border: none; cursor: pointer; }}
            </style>
        </head>
        <body>
            <h2>Reset Password</h2>
            <form action="/reset-password-confirm" method="post">
                <input type="hidden" name="token" value="{safe_token}">
                <input type="password" name="new_password" placeholder="New Password" minlength="8" required>
                <button type="submit">Reset Password</button>
            </form>
        </body>
    </html>
    """

@app.post("/reset-password-confirm")
async def reset_password_confirm(token: str = Form(...), new_password: str = Form(...), db: Session = Depends(get_db)):
    if len(new_password.strip()) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if username is None:
             raise HTTPException(status_code=400, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid token")
        
    player = db.query(Player).filter(Player.username == username).first()
    if not player:
        raise HTTPException(status_code=404, detail="User not found")

    now = datetime.utcnow()
    player.password_hash = get_password_hash(new_password)
    player.password_changed_at = now
    player.updated_at = now
    db.query(AuthSession).filter(
        AuthSession.player_id == player.id,
        AuthSession.revoked_at.is_(None),
    ).update({"revoked_at": now}, synchronize_session=False)
    db.commit()
    return HTMLResponse(content="<h2>Password Reset Successful</h2><p>You can now return to the app and login.</p>")

@app.post("/login")
async def login(request: LoginRequest, http_request: Request, db: Session = Depends(get_db)):
    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    if normalize_account_status(player.account_status) != "active":
        raise HTTPException(status_code=403, detail="Account is not active")
    if not player.password_hash:
        raise HTTPException(status_code=400, detail="Password reset required for this account")
    if not verify_password(request.password, player.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect username or password")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    now = datetime.utcnow()
    token_jti = str(uuid.uuid4())
    access_token = create_access_token(
        data={"sub": player.username, "jti": token_jti}, expires_delta=access_token_expires
    )
    player.last_login_at = now
    player.updated_at = now
    _record_auth_session(
        db,
        player,
        token_jti=token_jti,
        expires_at=now + access_token_expires,
        http_request=http_request,
    )
    start_activity_session(db, player, token_jti)
    db.commit()
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/logout")
async def logout(request: LogoutRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    now = datetime.utcnow()
    token_jti = getattr(current_user, "_token_jti", None)

    if token_jti:
        auth_session = db.query(AuthSession).filter(AuthSession.token_jti == token_jti).first()
        if auth_session and auth_session.revoked_at is None:
            auth_session.last_seen_at = now
            auth_session.revoked_at = now

    end_activity_session(db, current_user, token_jti)
    db.commit()
    return {"status": "ok"}

@app.post("/select_book", response_model=BookSelectResponse)
async def select_book(request: BookSelectRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        now = datetime.utcnow()
        player = Player(
            username=request.username,
            display_name=request.username,
            location="New Hampshire",
            curriculum_region="New Hampshire",
            grade_level=10,
            created_at=now,
            updated_at=now,
        )
        db.add(player)
        db.commit()
        db.refresh(player)
    else:
        _ensure_player_runtime_defaults(db, player)

    assert_tutoring_access(db, player)
    learning_mode = _resolved_learning_mode(request.learning_mode)
    resolved_topic = _resolved_topic_name(request.topic, learning_mode)
    target_grade = _session_target_grade(
        player,
        requested_topic=request.topic,
        learning_mode=learning_mode,
        session_grade_level=request.session_grade_level,
    )

    touch_activity_session(
        db,
        current_user,
        token_jti=getattr(current_user, "_token_jti", None),
        topic_name=resolved_topic,
        increment_request=False,
    )
    record_topic_session_start(db, player, resolved_topic, learning_mode=learning_mode)

    progress = get_mode_topic_progress(db, player.id, resolved_topic, learning_mode)
    if progress is None:
        raise HTTPException(status_code=500, detail="Unable to initialize progress for this topic.")

    progress.learning_mode = learning_mode
    _apply_topic_progress_metadata(progress, resolved_topic)
    progress.content_grade_level = target_grade

    topic_label = topic_label_for_mode(request.topic, learning_mode)
    adaptive_suggestion = ""
    resume_summary = None
    if is_knowledge_tracing_mode(learning_mode):
        if int(progress.answer_attempt_count or 0) > 0 or progress.current_node:
            resume_summary = (
                "Resuming "
                + topic_label
                + ". Subject mastery level: "
                + str(int(progress.mastery_level or 0))
                + "/10."
            )
        else:
            resume_summary = (
                "Starting "
                + topic_label
                + ". Adaptive testing is using the saved grade level of Grade "
                + str(target_grade)
                + "."
            )
    else:
        topic_grade_match = re.search(r"\d+", request.topic)
        current_grade_level = int(player.grade_level or 0)
        if request.session_grade_level is not None:
            current_grade_level = int(request.session_grade_level)
        if topic_grade_match:
            topic_grade = int(topic_grade_match.group())
            grade_diff = current_grade_level - topic_grade
            if not request.manual_mode and grade_diff > 0:
                adaptive_suggestion = (
                    f"\n\n[System]: Review Mode initialized. You are Grade {current_grade_level}, reviewing Grade {topic_grade} material."
                )
            elif not request.manual_mode and grade_diff < -2:
                adaptive_suggestion = (
                    f"\n\n[System]: Challenge Mode. You are Grade {current_grade_level} attempting Grade {topic_grade}. Good luck!"
                )
        if int(progress.answer_attempt_count or 0) > 0 or progress.current_node or progress.completed_nodes:
            resume_summary = f"Continuing {request.topic}. Mastery: {progress.mastery_score}%"
        else:
            resume_summary = f"Starting {request.topic}."

    full_summary = (resume_summary or f"Starting {topic_label}.") + adaptive_suggestion
    effective_grade = f"Grade {target_grade}"
    db.commit()
    db.refresh(progress)

    # 4. Initialize Graph Session
    session_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": session_id}}
    
    initial_state = {
        "session_id": session_id,
        "topic": resolved_topic,
        "grade_level": effective_grade, 
        "location": player.location,
        "learning_style": player.learning_style,
        "username": player.username,
        "mastery": progress.mastery_score,
        "messages": [], 
        "currrent_action": "IDLE",
        "last_problem": "",
        "next_dest": "GENERAL_CHAT",
        "role": _effective_learning_role(player), # Treat admins as teacher-capable in tutoring flows
        "view_as_student": False, # Default
        "learning_mode": learning_mode,
    }
    
    # In a real heavy app, we'd load 'last_state_snapshot' from DB into graph
    # But for now we just spin up a session.
    await graph.aupdate_state(config, initial_state)
    
    state_snapshot = _build_navigation_snapshot(
        db,
        player=player,
        topic_name=resolved_topic,
        learning_mode=learning_mode,
        target_grade=target_grade,
    )
    
    return BookSelectResponse(
        session_id=session_id,
        status=progress.status,
        xp=player.xp,
        level=player.level,
        mastery=progress.mastery_score,
        mastery_level=int(progress.mastery_level or 0),
        learning_mode=learning_mode,
        resolved_topic=resolved_topic,
        topic_label=topic_label,
        history_summary=full_summary,
        state_snapshot=state_snapshot,
        role=_effective_learning_role(player) # Treat admins as teacher-capable in classroom UI
    )

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _update_auth_session_last_seen(db, current_user)
    config = {"configurable": {"thread_id": request.session_id}}
    
    current_state = await graph.aget_state(config)
    if not current_state.values:
        raise HTTPException(status_code=404, detail="Session not found.")
    if current_state.values.get("username") != current_user.username:
        raise HTTPException(status_code=403, detail="Session access denied.")

    assert_tutoring_access(db, current_user)
    learning_mode = _resolved_learning_mode(current_state.values.get("learning_mode"))
    
    inputs = {
        "messages": [HumanMessage(content=request.message)],
        "view_as_student": request.view_as_student # [NEW]
    }
    
    if request.grade_override is not None and not is_knowledge_tracing_mode(learning_mode):
        inputs["grade_level"] = f"Grade {request.grade_override}"
        print(f"[API] Grade Override Applied: {inputs['grade_level']}")

    print(f"\n[API] /chat Request: {request.message}")
    result = await graph.ainvoke(inputs, config)
    
    messages = result.get("messages", [])
    last_msg = messages[-1].content if messages else ""
    current_action = result.get("current_action", "IDLE")

    print(f"[API] /chat Response: {last_msg}\n")
    
    # Extract mastery if updated
    mastery_update = result.get("mastery")
    
    snapshot = {
        "current_action": current_action,
        "learning_mode": learning_mode,
        "topic_label": topic_label_for_mode(current_state.values.get("topic", ""), learning_mode),
    }
    if mastery_update is not None:
        snapshot["mastery"] = mastery_update
    
    try:
        player = db.query(Player).filter(Player.username == current_state.values.get("username")).first()
        topic_name = current_state.values.get("topic")
        if player and topic_name:
            target_grade = _session_target_grade(
                player,
                requested_topic=topic_name,
                learning_mode=learning_mode,
            )
            snapshot.update(
                _build_navigation_snapshot(
                    db,
                    player=player,
                    topic_name=topic_name,
                    learning_mode=learning_mode,
                    target_grade=target_grade,
                )
            )
    except Exception as e:
        print(f"Error injecting nav context: {e}")

    increment_tutor_turn_usage(db, current_user)
    topic_name = current_state.values.get("topic")
    current_node_id = None
    if topic_name:
        current_progress = get_mode_topic_progress(db, current_user.id, topic_name, learning_mode)
        if current_progress:
            current_node_id = current_progress.current_node
    touch_activity_session(
        db,
        current_user,
        token_jti=getattr(current_user, "_token_jti", None),
        topic_name=topic_name,
        node_id=current_node_id,
        increment_request=False,
        increment_chat_turn=True,
    )
    db.commit()

    return ChatResponse(
        response=str(last_msg),
        state_snapshot=snapshot
    )

# Initialize GraphNavigator
from .graph_logic import GraphNavigator
navigator = GraphNavigator()

@app.post("/update_progress")
async def update_progress(username: str, topic: str, xp_delta: int, mastery_delta: int, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, username)
    _update_auth_session_last_seen(db, current_user)
    player = db.query(Player).filter(Player.username == username).first()
    next_suggestions = []
    
    if player:
        player.xp += xp_delta
        player.level = 1 + player.xp // 100
        player.updated_at = datetime.utcnow()
        
        progress = db.query(TopicProgress).filter(
            TopicProgress.player_id == player.id, 
            TopicProgress.topic_name == topic
        ).first()

        completed_just_now = False

        if not progress:
            # Create new if doesn't exist (edge case)
            now = datetime.utcnow()
            progress = TopicProgress(
                player_id=player.id,
                topic_name=topic,
                mastery_score=0,
                created_at=now,
                updated_at=now,
                last_interaction_at=now,
            )
            _apply_topic_progress_metadata(progress, topic)
            db.add(progress)

        progress.mastery_score = min(100, progress.mastery_score + mastery_delta)
        progress.updated_at = datetime.utcnow()
        progress.last_interaction_at = progress.updated_at
        _apply_topic_progress_metadata(progress, topic)
        
        # Mark visited/current node if topic matches a graph node? 
        # Currently "topic" in API is usually "Math 10" or "Solids".
        # We need to assume 'topic' maps to a node path or label.
        # Ideally frontend sends the NODE_ID (Path). 
        # But for now, let's assume topic is the "label" or "key".
        # We will try to update 'current_node' and 'completed_nodes'
        
        # Check completeness
        if progress.mastery_score >= 100:
            if progress.status != "COMPLETED":
                progress.status = "COMPLETED"
                completed_just_now = True
            
            # Add to completed_nodes list if not present
            # We assume 'topic' is the node identifier being tracked
            current_completed = list(progress.completed_nodes) if progress.completed_nodes else []
            if topic not in current_completed:
                current_completed.append(topic)
                progress.completed_nodes = current_completed
            if not progress.completed_at:
                progress.completed_at = datetime.utcnow()
                
        elif progress.status == "NOT_STARTED":
            progress.status = "IN_PROGRESS"
            
        progress.current_node = topic
        db.commit() # Commit updates
        
        # Calculate Next Node if Completed
        if completed_just_now:
            completed_list = list(progress.completed_nodes) if progress.completed_nodes else [topic]
            # Use Grade Level from Player
            suggestions = navigator.get_next_options(completed_list, player.grade_level)
            
            # Logic: If 1 suggestion, auto-assign?
            # User said: "If multiple edges... ask." -> Return list.
            # If one path -> "select next node".
            
            # We will return this in the response so Frontend can handle it.
            next_suggestions = suggestions

    return {"status": "ok", "next_nodes": next_suggestions}

@app.post("/init_session", response_model=InitSessionResponse)
async def init_session(request: InitSessionRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    normalized_avatar_id = normalize_avatar_id(request.avatar_id)
    now = datetime.utcnow()
    guardian_email = _clean_optional_text(request.guardian_email)
    if guardian_email and not _is_valid_email(guardian_email):
        raise HTTPException(status_code=400, detail="Guardian email must be a valid email address.")

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        player = Player(
            username=request.username, 
            display_name=_clean_optional_text(request.display_name) or request.username,
            grade_level=request.grade_level,
            location=request.location,
            curriculum_region=_clean_optional_text(request.curriculum_region) or request.location,
            learning_style=request.learning_style,
            sex=request.sex,
            birthday=request.birthday,
            interests=request.interests,
            role=_normalize_user_role(request.role),
            avatar_id=normalized_avatar_id,
            preferred_model=_clean_optional_text(request.preferred_model),
            school_name=_clean_optional_text(request.school_name),
            district_name=_clean_optional_text(request.district_name),
            classroom_id=_clean_optional_text(request.classroom_id),
            roster_id=_clean_optional_text(request.roster_id),
            guardian_name=_clean_optional_text(request.guardian_name),
            guardian_email=guardian_email,
            created_at=now,
            updated_at=now,
        )
        db.add(player)
        db.commit()
    else:
        if request.save_profile:
            player.display_name = _clean_optional_text(request.display_name) or player.display_name or player.username
            player.grade_level = request.grade_level
            player.location = request.location
            player.curriculum_region = _clean_optional_text(request.curriculum_region) or request.location
            player.learning_style = request.learning_style
            if request.sex: player.sex = request.sex
            if request.birthday: player.birthday = request.birthday
            if request.interests: player.interests = request.interests
            if request.role:
                player.role = _normalize_user_role(request.role, allow_admin=_is_admin_user(current_user))
            if request.avatar_id:
                player.avatar_id = normalized_avatar_id
            if request.preferred_model is not None:
                player.preferred_model = _clean_optional_text(request.preferred_model)
            if request.school_name is not None:
                player.school_name = _clean_optional_text(request.school_name)
            if request.district_name is not None:
                player.district_name = _clean_optional_text(request.district_name)
            if request.classroom_id is not None:
                player.classroom_id = _clean_optional_text(request.classroom_id)
            if request.roster_id is not None:
                player.roster_id = _clean_optional_text(request.roster_id)
            if request.guardian_name is not None:
                player.guardian_name = _clean_optional_text(request.guardian_name)
            if request.guardian_email is not None:
                player.guardian_email = guardian_email
            player.updated_at = now
            db.commit()
    
    db.refresh(player)
    effective_grade = request.grade_level 
    return InitSessionResponse(
        status="ok",
        username=player.username,
        grade_level=effective_grade,
        avatar_id=normalize_avatar_id(player.avatar_id),
    )

@app.post("/resume_shelf", response_model=ResumeShelfResponse)
async def resume_shelf(request: ResumeShelfRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    from .knowledge_graph import _subject_topic_prefixes

    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)

    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")

    learning_mode = _resolved_learning_mode(request.learning_mode)
    shelf_topic = request.shelf_category if request.shelf_category else "Science"
    query = db.query(TopicProgress).filter(
        TopicProgress.player_id == player.id,
        TopicProgress.learning_mode == learning_mode,
    )
    if request.shelf_category:
        subject_key = _topic_metadata_from_name(request.shelf_category)[0]
        prefixes = _subject_topic_prefixes(request.shelf_category)
        subject_filters = []
        if subject_key:
            subject_filters.append(TopicProgress.subject_key == subject_key)
        for prefix in prefixes:
            subject_filters.append(TopicProgress.topic_name.like(f"{prefix}%"))
        if subject_filters:
            query = query.filter(or_(*subject_filters))

    active_progress = query.filter(TopicProgress.status == "IN_PROGRESS").order_by(
        TopicProgress.last_interaction_at.desc(),
        TopicProgress.updated_at.desc(),
        TopicProgress.mastery_score.desc(),
    ).first()
    if active_progress:
        return ResumeShelfResponse(
            topic=active_progress.topic_name,
            reason=f"Resuming {topic_label_for_mode(active_progress.topic_name, learning_mode)}...",
            learning_mode=learning_mode,
            topic_label=topic_label_for_mode(active_progress.topic_name, learning_mode),
        )

    recent_progress = query.order_by(
        TopicProgress.last_interaction_at.desc(),
        TopicProgress.updated_at.desc(),
        TopicProgress.id.desc(),
    ).first()
    target_topic = recent_progress.topic_name if recent_progress else _resolved_topic_name(shelf_topic, learning_mode)
    target_grade = _session_target_grade(player, shelf_topic, learning_mode)

    if is_knowledge_tracing_mode(learning_mode):
        next_node = select_next_tracing_node(
            db,
            player_id=player.id,
            topic_name=target_topic,
            target_grade=target_grade,
            current_node_id=recent_progress.current_node if recent_progress else None,
        )
        reason = (
            "Continuing knowledge tracing with "
            + next_node.label
            if next_node is not None
            else "Knowledge tracing is ready for review."
        )
    else:
        next_node = select_next_teach_me_node(
            db,
            player_id=player.id,
            topic_name=target_topic,
            target_grade=target_grade,
            current_node_id=recent_progress.current_node if recent_progress else None,
        )
        if next_node is not None:
            reason = "Next logical topic: " + next_node.label
        elif get_subject_full_mastery_node_ids(db, player.id, target_topic):
            reason = "Curriculum complete! Review is available."
        else:
            reason = "Starting curriculum from the beginning."

    return ResumeShelfResponse(
        topic=target_topic,
        reason=reason,
        learning_mode=learning_mode,
        topic_label=topic_label_for_mode(target_topic, learning_mode),
    )
@app.post("/get_topic_graph", response_model=GraphDataResponse)
async def get_topic_graph(request: GraphDataRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    from .knowledge_graph import get_graph
    
    kg = get_graph(request.topic)
    if not kg or not kg.graph.nodes:
         return GraphDataResponse(nodes=[])
         
    # Get Player Progress
    player = db.query(Player).filter(Player.username == request.username).first()
    completed_set = set()
    current_node_id = ""
    current_learning_mode = TEACH_ME_MODE
    mastery_map: dict[str, int] = {}
    
    if player:
        prog = db.query(TopicProgress).filter(
            TopicProgress.player_id == player.id,
            TopicProgress.topic_name == request.topic,
        ).order_by(TopicProgress.updated_at.desc()).first()
        
        if prog:
            current_learning_mode = _resolved_learning_mode(prog.learning_mode)
            completed_set = set(get_subject_full_mastery_node_ids(db, player.id, request.topic))
            if prog.current_node:
                current_node_id = prog.current_node
        else:
            completed_set = set(get_subject_full_mastery_node_ids(db, player.id, request.topic))

        from .knowledge_tracing import get_subject_node_mastery_map
        mastery_map = get_subject_node_mastery_map(db, player.id, request.topic)
    
    # Build Node List
    result_nodes = []
    
    # We want to traverse in a logical order if possible, or just dump all and let UI tree sort?
    # UI in Godot will receive a list. It needs to know hierarchy.
    # We have Parent info in node_map in Navigator, but here we use KG graph.
    # KG graph has edges Parent->Child.
    
    # Access internal graph data to get type/parent
    # Windowing Logic
    focus = request.focus_node_id
    if not focus and current_node_id:
        focus = current_node_id
        
    window_limit = request.window_size if request.window_size > 0 else 20
    target_nodes = kg.get_window(focus, window_limit)
    
    link_counts = get_node_link_count_map(
        db,
        [node_obj.id for node_obj in target_nodes],
        include_pending=_is_admin_user(current_user),
    )

    for node_obj in target_nodes:
        node_id = node_obj.id
        node_data = kg.graph.nodes[node_id]
        
        # Determine Status
        status = "locked"
        if node_id in completed_set:
            status = "completed"
        elif node_id == current_node_id:
            status = "current"
        else:
             pass
             
        # Parents
        parent_id = None
        for pred in kg.graph.predecessors(node_id):
            if kg.graph.nodes[pred].get("type") in ["topic", "subtopic"]:
                parent_id = pred
                break
        
        result_nodes.append(GraphNode(
            id=node_id,
            label=node_data.get("label", node_id),
            grade_level=node_data.get("grade_level", 0),
            type=node_data.get("type", "concept"),
            status=status,
            mastery_level=max(0, min(10, int(mastery_map.get(node_id, 0)))),
            is_tentative=0 < int(mastery_map.get(node_id, 0)) < 10,
            parent=parent_id,
            authoritative_link_count=link_counts.get(node_id, {}).get("authoritative_link_count", 0),
            approved_user_link_count=link_counts.get(node_id, {}).get("approved_user_link_count", 0),
            pending_user_link_count=link_counts.get(node_id, {}).get("pending_user_link_count", 0),
        ))
        # Late pass for "Available"? 
    # Calling get_next_learnable_nodes is expensive if we do it for all?
    # Just do it once.
    target_grade = int(player.grade_level or 0) if player else None
    if current_learning_mode == KNOWLEDGE_TRACING_MODE and player:
        candidate = select_next_tracing_node(
            db,
            player_id=player.id,
            topic_name=request.topic,
            target_grade=target_grade,
            current_node_id=current_node_id,
        )
        candidate_ids = {candidate.id} if candidate else set()
    else:
        candidates = kg.get_next_learnable_nodes(list(completed_set), target_grade=target_grade)
        candidate_ids = set([c.id for c in candidates])
    
    for n in result_nodes:
        if n.status == "locked" and n.id in candidate_ids:
            n.status = "available"
            
    return GraphDataResponse(nodes=result_nodes)

@app.post("/set_current_node")
async def set_current_node(request: SetCurrentNodeRequest, current_user: Player = Depends(get_current_user), db: Session = Depends(get_db)):
    _ensure_current_user_matches(current_user, request.username)
    _update_auth_session_last_seen(db, current_user)
    player = db.query(Player).filter(Player.username == request.username).first()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found")
    progress = db.query(TopicProgress).filter(
        TopicProgress.player_id == player.id,
        TopicProgress.topic_name == request.topic,
    ).order_by(TopicProgress.updated_at.desc()).first()
    learning_mode = _resolved_learning_mode(progress.learning_mode if progress else TEACH_ME_MODE)
    touch_current_node(db, player, request.topic, request.node_id, learning_mode=learning_mode)
    touch_activity_session(
        db,
        current_user,
        token_jti=getattr(current_user, "_token_jti", None),
        topic_name=request.topic,
        node_id=request.node_id,
        increment_request=False,
    )
    db.commit()
    return {"status": "ok", "current_node": request.node_id}

if __name__ == "__main__":
    import uvicorn
    # Use PORT env var or default to 8000
    port = int(os.environ.get("PORT", 8000))
    # Bind to 0.0.0.0 for external access (Render)
    uvicorn.run("backend.main:app", host="0.0.0.0", port=port, reload=True)
