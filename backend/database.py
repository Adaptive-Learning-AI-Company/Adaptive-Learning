from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, JSON, DateTime, Boolean, inspect, text, UniqueConstraint
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session
import datetime
import re

import os

from .config import DEFAULT_AVATAR_ID, load_local_env

load_local_env()

# Default to SQLite for local development
URL_DATABASE = os.getenv("DATABASE_URL", "sqlite:///./learning_data.db")

# Render uses 'postgres://' which is deprecated in SQLAlchemy 1.4+ (needs 'postgresql://')
if URL_DATABASE and URL_DATABASE.startswith("postgres://"):
    URL_DATABASE = URL_DATABASE.replace("postgres://", "postgresql://", 1)

print(f"[DB] Initializing Database connection...")
if "sqlite" in URL_DATABASE:
    print(f"[DB] Using SQLite: {URL_DATABASE}")
else:
    print(f"[DB] Using Remote Database (Postgres)")

# SQLite config options are not compatible with Postgres
connect_args = {}
if "sqlite" in URL_DATABASE:
    connect_args = {"check_same_thread": False}

engine = create_engine(URL_DATABASE, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def _utcnow():
    return datetime.datetime.utcnow()


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


def _extract_book_level(topic_name: str | None) -> int | None:
    if not topic_name:
        return None

    match = re.search(r"(\d+)", topic_name)
    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def apply_player_defaults(player: "Player") -> bool:
    changed = False

    if player.xp is None:
        player.xp = 0
        changed = True
    if player.level is None:
        player.level = 1
        changed = True
    if not player.location:
        player.location = "New Hampshire"
        changed = True
    if player.grade_level is None:
        player.grade_level = 10
        changed = True
    if not player.learning_style:
        player.learning_style = "Visual"
        changed = True
    if not player.sex:
        player.sex = "Not Specified"
        changed = True
    if not player.role:
        player.role = "Student"
        changed = True
    if not player.display_name:
        player.display_name = player.username
        changed = True
    if not player.account_status:
        player.account_status = "active"
        changed = True
    if not player.avatar_id:
        player.avatar_id = DEFAULT_AVATAR_ID
        changed = True
    if not player.curriculum_region and player.location:
        player.curriculum_region = player.location
        changed = True
    if player.subscription_status_cached is None:
        player.subscription_status_cached = "inactive"
        changed = True

    return changed

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    xp = Column(Integer, default=0)
    level = Column(Integer, default=1)
    location = Column(String, default="New Hampshire")
    grade_level = Column(Integer, default=10) # 0=K, 1-12, 13-16=College, 17+=Masters
    learning_style = Column(String, default="Visual") # Visual, Text, audit, etc
    sex = Column(String, default="Not Specified")
    birthday = Column(String, nullable=True) # YYYY-MM-DD
    interests = Column(Text, nullable=True)
    role = Column(String, default="Student") # Student, Teacher
    password_hash = Column(String, nullable=True) # [NEW] Auth Support
    email = Column(String, index=True, nullable=True) # [NEW] Email Support
    display_name = Column(String, nullable=True)
    account_status = Column(String, default="active")
    avatar_id = Column(String, default=DEFAULT_AVATAR_ID)
    curriculum_region = Column(String, nullable=True)
    openai_api_key_encrypted = Column(Text, nullable=True)
    preferred_model = Column(String, nullable=True)
    school_name = Column(String, nullable=True)
    district_name = Column(String, nullable=True)
    classroom_id = Column(String, nullable=True)
    roster_id = Column(String, nullable=True)
    guardian_name = Column(String, nullable=True)
    guardian_email = Column(String, nullable=True)
    billing_provider = Column(String, nullable=True)
    stripe_customer_id = Column(String, index=True, nullable=True)
    subscription_plan_code = Column(String, nullable=True)
    subscription_status_cached = Column(String, nullable=True)
    subscription_current_period_end = Column(DateTime, nullable=True)
    payment_method_brand = Column(String, nullable=True)
    payment_method_last4 = Column(String, nullable=True)
    payment_method_exp_month = Column(Integer, nullable=True)
    payment_method_exp_year = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_login_at = Column(DateTime, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    password_changed_at = Column(DateTime, nullable=True)
    last_password_reset_requested_at = Column(DateTime, nullable=True)
    openai_api_key_updated_at = Column(DateTime, nullable=True)
    
    progress = relationship("TopicProgress", back_populates="player")
    auth_sessions = relationship("AuthSession", back_populates="player")
    subscriptions = relationship("Subscription", back_populates="player")
    usage_cycles = relationship("UsageCycle", back_populates="player")
    billing_events = relationship("BillingEvent", back_populates="player")
    teacher_links_as_student = relationship("TeacherStudentLink", foreign_keys="TeacherStudentLink.student_id", back_populates="student")
    teacher_links_as_teacher = relationship("TeacherStudentLink", foreign_keys="TeacherStudentLink.teacher_id", back_populates="teacher")
    activity_sessions = relationship("StudentActivitySession", back_populates="player")
    node_progress_entries = relationship("StudentNodeProgress", back_populates="player")

class TopicProgress(Base):
    __tablename__ = "topic_progress"
    
    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    topic_name = Column(String, index=True)
    learning_mode = Column(String, index=True, default="teach_me")
    status = Column(String, default="NOT_STARTED") # NOT_STARTED, IN_PROGRESS, COMPLETED
    mastery_score = Column(Integer, default=0) # 0-100
    mastery_level = Column(Integer, default=0) # 0-10 subject-level mastery
    mistakes = Column(JSON, default=list) # List of strings (concepts/problems)
    last_state_snapshot = Column(JSON, nullable=True) # Full graph state dump
    
    completed_nodes = Column(JSON, default=list) # List of node_id strings (KG)
    current_node = Column(String, nullable=True) # The specific node_id being worked on
    subject_key = Column(String, index=True, nullable=True)
    book_level = Column(Integer, nullable=True)
    content_grade_level = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)
    last_interaction_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    answer_attempt_count = Column(Integer, default=0)
    correct_answer_count = Column(Integer, default=0)
    incorrect_answer_count = Column(Integer, default=0)
    cumulative_score_percent = Column(Integer, default=0)
    total_learning_seconds = Column(Integer, default=0)
    session_count = Column(Integer, default=0)
    first_answered_at = Column(DateTime, nullable=True)
    last_answered_at = Column(DateTime, nullable=True)
    current_node_started_at = Column(DateTime, nullable=True)
    
    player = relationship("Player", back_populates="progress")

class Interaction(Base):
    __tablename__ = "interactions"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    username = Column(String, index=True)
    subject = Column(String, index=True) # e.g. "Math", "Science"
    user_query = Column(Text, nullable=True)
    agent_response = Column(Text)
    source_node = Column(String) # "teacher", "verifier", etc.
    session_id = Column(String, index=True, nullable=True)
    topic_name = Column(String, index=True, nullable=True)
    node_id = Column(String, nullable=True)
    model_name = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    billing_source = Column(String, nullable=True)
    service_tier = Column(String, nullable=True)
    estimated_cost_cents = Column(Integer, nullable=True)
    event_type = Column(String, index=True, nullable=True)
    score_percent = Column(Integer, nullable=True)
    is_correct = Column(Boolean, nullable=True)


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    token_jti = Column(String, unique=True, index=True)
    device_label = Column(String, nullable=True)
    user_agent = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)

    player = relationship("Player", back_populates="auth_sessions")


class TeacherStudentLink(Base):
    __tablename__ = "teacher_student_links"
    __table_args__ = (
        UniqueConstraint("teacher_id", "student_id", name="uq_teacher_student_pair"),
    )

    id = Column(Integer, primary_key=True, index=True)
    teacher_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    student_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    status = Column(String, index=True, nullable=False, default="PENDING")
    request_note = Column(Text, nullable=True)
    response_note = Column(Text, nullable=True)
    requested_at = Column(DateTime, default=_utcnow)
    responded_at = Column(DateTime, nullable=True)
    accepted_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    teacher = relationship("Player", foreign_keys=[teacher_id], back_populates="teacher_links_as_teacher")
    student = relationship("Player", foreign_keys=[student_id], back_populates="teacher_links_as_student")


class StudentActivitySession(Base):
    __tablename__ = "student_activity_sessions"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    token_jti = Column(String, unique=True, index=True, nullable=True)
    started_at = Column(DateTime, default=_utcnow)
    last_seen_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    total_active_seconds = Column(Integer, default=0)
    request_count = Column(Integer, default=0)
    chat_turn_count = Column(Integer, default=0)
    last_topic_name = Column(String, nullable=True)
    last_node_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    player = relationship("Player", back_populates="activity_sessions")


class StudentNodeProgress(Base):
    __tablename__ = "student_node_progress"
    __table_args__ = (
        UniqueConstraint("player_id", "topic_name", "node_id", name="uq_student_node_progress"),
    )

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    topic_name = Column(String, index=True, nullable=False)
    node_id = Column(String, index=True, nullable=False)
    learning_mode = Column(String, index=True, default="teach_me")
    subject_key = Column(String, index=True, nullable=True)
    book_level = Column(Integer, nullable=True)
    status = Column(String, index=True, default="NOT_STARTED")
    mastery_level = Column(Integer, default=0)
    attempt_count = Column(Integer, default=0)
    correct_count = Column(Integer, default=0)
    incorrect_count = Column(Integer, default=0)
    cumulative_score_percent = Column(Integer, default=0)
    total_learning_seconds = Column(Integer, default=0)
    first_seen_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    last_score_percent = Column(Integer, nullable=True)
    last_problem = Column(Text, nullable=True)
    last_answer = Column(Text, nullable=True)
    last_feedback = Column(Text, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    player = relationship("Player", back_populates="node_progress_entries")


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"

    id = Column(Integer, primary_key=True, index=True)
    plan_code = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    provider = Column(String, default="stripe")
    stripe_price_id = Column(String, nullable=True)
    monthly_price_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String, default="usd")
    includes_hosted_usage = Column(Boolean, default=False)
    requires_personal_key = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    monthly_tutor_turn_cap = Column(Integer, nullable=True)
    monthly_llm_call_cap = Column(Integer, nullable=True)
    monthly_input_token_cap = Column(Integer, nullable=True)
    monthly_output_token_cap = Column(Integer, nullable=True)
    monthly_cost_cap_cents = Column(Integer, nullable=True)
    hosted_main_model = Column(String, nullable=True)
    hosted_fast_model = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    plan_code = Column(String, index=True, nullable=False)
    provider = Column(String, default="stripe")
    provider_customer_id = Column(String, index=True, nullable=True)
    provider_subscription_id = Column(String, unique=True, index=True, nullable=True)
    status = Column(String, index=True, nullable=False, default="inactive")
    current_period_start = Column(DateTime, nullable=True)
    current_period_end = Column(DateTime, nullable=True)
    cancel_at_period_end = Column(Boolean, default=False)
    canceled_at = Column(DateTime, nullable=True)
    trial_end = Column(DateTime, nullable=True)
    latest_invoice_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    player = relationship("Player", back_populates="subscriptions")


class UsageCycle(Base):
    __tablename__ = "usage_cycles"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"))
    plan_code = Column(String, index=True, nullable=False)
    cycle_start = Column(DateTime, index=True, nullable=False)
    cycle_end = Column(DateTime, index=True, nullable=False)
    tutor_turns_used = Column(Integer, default=0)
    llm_calls_used = Column(Integer, default=0)
    input_tokens_used = Column(Integer, default=0)
    output_tokens_used = Column(Integer, default=0)
    estimated_cost_cents = Column(Integer, default=0)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    player = relationship("Player", back_populates="usage_cycles")


class BillingEvent(Base):
    __tablename__ = "billing_events"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    provider = Column(String, default="stripe")
    event_type = Column(String, index=True, nullable=False)
    provider_event_id = Column(String, unique=True, index=True, nullable=False)
    event_status = Column(String, default="processed")
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_utcnow)

    player = relationship("Player", back_populates="billing_events")


class PromoCode(Base):
    __tablename__ = "promo_codes"

    id = Column(Integer, primary_key=True, index=True)
    code_hash = Column(String, unique=True, index=True, nullable=False)
    code_prefix = Column(String, index=True, nullable=True)
    assigned_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    plan_code = Column(String, index=True, nullable=False)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, index=True, nullable=True)
    max_redemptions = Column(Integer, default=1)
    redemption_count = Column(Integer, default=0)
    revoked_at = Column(DateTime, index=True, nullable=True)
    revocation_reason = Column(Text, nullable=True)
    created_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    notes = Column(Text, nullable=True)
    extra_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    assigned_player = relationship("Player", foreign_keys=[assigned_player_id])
    created_by = relationship("Player", foreign_keys=[created_by_player_id])


class AccessGrant(Base):
    __tablename__ = "access_grants"

    id = Column(Integer, primary_key=True, index=True)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    source_type = Column(String, index=True, nullable=False, default="manual")
    source_id = Column(Integer, nullable=True)
    plan_code = Column(String, index=True, nullable=False)
    starts_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, index=True, nullable=True)
    revoked_at = Column(DateTime, index=True, nullable=True)
    revocation_reason = Column(Text, nullable=True)
    created_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    notes = Column(Text, nullable=True)
    extra_metadata = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    player = relationship("Player", foreign_keys=[player_id])
    created_by = relationship("Player", foreign_keys=[created_by_player_id])


class PromoRedemption(Base):
    __tablename__ = "promo_redemptions"

    id = Column(Integer, primary_key=True, index=True)
    promo_code_id = Column(Integer, ForeignKey("promo_codes.id"), nullable=False)
    player_id = Column(Integer, ForeignKey("players.id"), nullable=False)
    access_grant_id = Column(Integer, ForeignKey("access_grants.id"), nullable=True)
    redeemed_at = Column(DateTime, default=_utcnow)

    promo_code = relationship("PromoCode")
    player = relationship("Player", foreign_keys=[player_id])
    access_grant = relationship("AccessGrant")


class NodeLink(Base):
    __tablename__ = "node_links"

    id = Column(Integer, primary_key=True, index=True)
    external_key = Column(String, unique=True, index=True, nullable=True)
    node_id = Column(String, index=True, nullable=False)
    subject_key = Column(String, index=True, nullable=True)
    title = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    provider = Column(String, nullable=True)
    link_type = Column(String, default="general")
    source_kind = Column(String, index=True, default="user")
    review_status = Column(String, index=True, default="pending")
    review_notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    extra_metadata = Column(JSON, default=dict)
    submitted_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    reviewed_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    submitted_by = relationship("Player", foreign_keys=[submitted_by_player_id])
    reviewed_by = relationship("Player", foreign_keys=[reviewed_by_player_id])


class AppSetting(Base):
    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, unique=True, index=True, nullable=False)
    value_text = Column(Text, nullable=True)
    updated_by_player_id = Column(Integer, ForeignKey("players.id"), nullable=True)
    created_at = Column(DateTime, default=_utcnow)
    updated_at = Column(DateTime, default=_utcnow, onupdate=_utcnow)

    updated_by = relationship("Player", foreign_keys=[updated_by_player_id])

def init_db():
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    ensure_indexes()
    backfill_schema_defaults()
    sync_subscription_catalog()
    sync_node_link_catalog()


def ensure_schema():
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())

    table_columns = {}
    for table_name in ["players", "topic_progress", "interactions", "student_node_progress"]:
        if table_name in table_names:
            table_columns[table_name] = {column["name"] for column in inspector.get_columns(table_name)}

    schema_updates = {
        "players": {
            "display_name": "ALTER TABLE players ADD COLUMN display_name VARCHAR",
            "account_status": "ALTER TABLE players ADD COLUMN account_status VARCHAR DEFAULT 'active'",
            "avatar_id": "ALTER TABLE players ADD COLUMN avatar_id VARCHAR DEFAULT '%s'" % DEFAULT_AVATAR_ID,
            "curriculum_region": "ALTER TABLE players ADD COLUMN curriculum_region VARCHAR",
            "openai_api_key_encrypted": "ALTER TABLE players ADD COLUMN openai_api_key_encrypted TEXT",
            "preferred_model": "ALTER TABLE players ADD COLUMN preferred_model VARCHAR",
            "school_name": "ALTER TABLE players ADD COLUMN school_name VARCHAR",
            "district_name": "ALTER TABLE players ADD COLUMN district_name VARCHAR",
            "classroom_id": "ALTER TABLE players ADD COLUMN classroom_id VARCHAR",
            "roster_id": "ALTER TABLE players ADD COLUMN roster_id VARCHAR",
            "guardian_name": "ALTER TABLE players ADD COLUMN guardian_name VARCHAR",
            "guardian_email": "ALTER TABLE players ADD COLUMN guardian_email VARCHAR",
            "billing_provider": "ALTER TABLE players ADD COLUMN billing_provider VARCHAR",
            "stripe_customer_id": "ALTER TABLE players ADD COLUMN stripe_customer_id VARCHAR",
            "subscription_plan_code": "ALTER TABLE players ADD COLUMN subscription_plan_code VARCHAR",
            "subscription_status_cached": "ALTER TABLE players ADD COLUMN subscription_status_cached VARCHAR",
            "subscription_current_period_end": "ALTER TABLE players ADD COLUMN subscription_current_period_end TIMESTAMP",
            "payment_method_brand": "ALTER TABLE players ADD COLUMN payment_method_brand VARCHAR",
            "payment_method_last4": "ALTER TABLE players ADD COLUMN payment_method_last4 VARCHAR",
            "payment_method_exp_month": "ALTER TABLE players ADD COLUMN payment_method_exp_month INTEGER",
            "payment_method_exp_year": "ALTER TABLE players ADD COLUMN payment_method_exp_year INTEGER",
            "created_at": "ALTER TABLE players ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "ALTER TABLE players ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "last_login_at": "ALTER TABLE players ADD COLUMN last_login_at TIMESTAMP",
            "email_verified_at": "ALTER TABLE players ADD COLUMN email_verified_at TIMESTAMP",
            "password_changed_at": "ALTER TABLE players ADD COLUMN password_changed_at TIMESTAMP",
            "last_password_reset_requested_at": "ALTER TABLE players ADD COLUMN last_password_reset_requested_at TIMESTAMP",
            "openai_api_key_updated_at": "ALTER TABLE players ADD COLUMN openai_api_key_updated_at TIMESTAMP",
        },
        "topic_progress": {
            "learning_mode": "ALTER TABLE topic_progress ADD COLUMN learning_mode VARCHAR DEFAULT 'teach_me'",
            "subject_key": "ALTER TABLE topic_progress ADD COLUMN subject_key VARCHAR",
            "book_level": "ALTER TABLE topic_progress ADD COLUMN book_level INTEGER",
            "content_grade_level": "ALTER TABLE topic_progress ADD COLUMN content_grade_level INTEGER",
            "mastery_level": "ALTER TABLE topic_progress ADD COLUMN mastery_level INTEGER DEFAULT 0",
            "created_at": "ALTER TABLE topic_progress ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "updated_at": "ALTER TABLE topic_progress ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "last_interaction_at": "ALTER TABLE topic_progress ADD COLUMN last_interaction_at TIMESTAMP",
            "completed_at": "ALTER TABLE topic_progress ADD COLUMN completed_at TIMESTAMP",
            "answer_attempt_count": "ALTER TABLE topic_progress ADD COLUMN answer_attempt_count INTEGER DEFAULT 0",
            "correct_answer_count": "ALTER TABLE topic_progress ADD COLUMN correct_answer_count INTEGER DEFAULT 0",
            "incorrect_answer_count": "ALTER TABLE topic_progress ADD COLUMN incorrect_answer_count INTEGER DEFAULT 0",
            "cumulative_score_percent": "ALTER TABLE topic_progress ADD COLUMN cumulative_score_percent INTEGER DEFAULT 0",
            "total_learning_seconds": "ALTER TABLE topic_progress ADD COLUMN total_learning_seconds INTEGER DEFAULT 0",
            "session_count": "ALTER TABLE topic_progress ADD COLUMN session_count INTEGER DEFAULT 0",
            "first_answered_at": "ALTER TABLE topic_progress ADD COLUMN first_answered_at TIMESTAMP",
            "last_answered_at": "ALTER TABLE topic_progress ADD COLUMN last_answered_at TIMESTAMP",
            "current_node_started_at": "ALTER TABLE topic_progress ADD COLUMN current_node_started_at TIMESTAMP",
        },
        "interactions": {
            "session_id": "ALTER TABLE interactions ADD COLUMN session_id VARCHAR",
            "topic_name": "ALTER TABLE interactions ADD COLUMN topic_name VARCHAR",
            "node_id": "ALTER TABLE interactions ADD COLUMN node_id VARCHAR",
            "model_name": "ALTER TABLE interactions ADD COLUMN model_name VARCHAR",
            "input_tokens": "ALTER TABLE interactions ADD COLUMN input_tokens INTEGER",
            "output_tokens": "ALTER TABLE interactions ADD COLUMN output_tokens INTEGER",
            "latency_ms": "ALTER TABLE interactions ADD COLUMN latency_ms INTEGER",
            "billing_source": "ALTER TABLE interactions ADD COLUMN billing_source VARCHAR",
            "service_tier": "ALTER TABLE interactions ADD COLUMN service_tier VARCHAR",
            "estimated_cost_cents": "ALTER TABLE interactions ADD COLUMN estimated_cost_cents INTEGER",
            "event_type": "ALTER TABLE interactions ADD COLUMN event_type VARCHAR",
            "score_percent": "ALTER TABLE interactions ADD COLUMN score_percent INTEGER",
            "is_correct": "ALTER TABLE interactions ADD COLUMN is_correct BOOLEAN",
        },
        "student_node_progress": {
            "learning_mode": "ALTER TABLE student_node_progress ADD COLUMN learning_mode VARCHAR DEFAULT 'teach_me'",
            "mastery_level": "ALTER TABLE student_node_progress ADD COLUMN mastery_level INTEGER DEFAULT 0",
        },
    }

    statements = []
    for table_name, column_updates in schema_updates.items():
        if table_name not in table_columns:
            continue
        existing_columns = table_columns[table_name]
        for column_name, statement in column_updates.items():
            if column_name not in existing_columns:
                statements.append(statement)

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def ensure_indexes():
    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_players_account_status ON players (account_status)",
        "CREATE INDEX IF NOT EXISTS ix_players_curriculum_region ON players (curriculum_region)",
        "CREATE INDEX IF NOT EXISTS ix_players_stripe_customer_id ON players (stripe_customer_id)",
        "CREATE INDEX IF NOT EXISTS ix_players_subscription_status_cached ON players (subscription_status_cached)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_learning_mode ON topic_progress (learning_mode)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_subject_key ON topic_progress (subject_key)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_last_interaction_at ON topic_progress (last_interaction_at)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_completed_at ON topic_progress (completed_at)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_last_answered_at ON topic_progress (last_answered_at)",
        "CREATE INDEX IF NOT EXISTS ix_topic_progress_current_node_started_at ON topic_progress (current_node_started_at)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_session_id ON interactions (session_id)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_topic_name ON interactions (topic_name)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_model_name ON interactions (model_name)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_billing_source ON interactions (billing_source)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_service_tier ON interactions (service_tier)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_event_type ON interactions (event_type)",
        "CREATE INDEX IF NOT EXISTS ix_interactions_is_correct ON interactions (is_correct)",
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_player_id ON auth_sessions (player_id)",
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_expires_at ON auth_sessions (expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_auth_sessions_revoked_at ON auth_sessions (revoked_at)",
        "CREATE INDEX IF NOT EXISTS ix_teacher_student_links_teacher_id ON teacher_student_links (teacher_id)",
        "CREATE INDEX IF NOT EXISTS ix_teacher_student_links_student_id ON teacher_student_links (student_id)",
        "CREATE INDEX IF NOT EXISTS ix_teacher_student_links_status ON teacher_student_links (status)",
        "CREATE INDEX IF NOT EXISTS ix_student_activity_sessions_player_id ON student_activity_sessions (player_id)",
        "CREATE INDEX IF NOT EXISTS ix_student_activity_sessions_token_jti ON student_activity_sessions (token_jti)",
        "CREATE INDEX IF NOT EXISTS ix_student_activity_sessions_last_seen_at ON student_activity_sessions (last_seen_at)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_player_id ON student_node_progress (player_id)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_topic_name ON student_node_progress (topic_name)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_node_id ON student_node_progress (node_id)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_learning_mode ON student_node_progress (learning_mode)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_status ON student_node_progress (status)",
        "CREATE INDEX IF NOT EXISTS ix_student_node_progress_last_seen_at ON student_node_progress (last_seen_at)",
        "CREATE INDEX IF NOT EXISTS ix_promo_codes_code_prefix ON promo_codes (code_prefix)",
        "CREATE INDEX IF NOT EXISTS ix_promo_codes_assigned_player_id ON promo_codes (assigned_player_id)",
        "CREATE INDEX IF NOT EXISTS ix_promo_codes_plan_code ON promo_codes (plan_code)",
        "CREATE INDEX IF NOT EXISTS ix_promo_codes_expires_at ON promo_codes (expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_promo_codes_revoked_at ON promo_codes (revoked_at)",
        "CREATE INDEX IF NOT EXISTS ix_promo_redemptions_promo_code_id ON promo_redemptions (promo_code_id)",
        "CREATE INDEX IF NOT EXISTS ix_promo_redemptions_player_id ON promo_redemptions (player_id)",
        "CREATE INDEX IF NOT EXISTS ix_promo_redemptions_access_grant_id ON promo_redemptions (access_grant_id)",
        "CREATE INDEX IF NOT EXISTS ix_access_grants_player_id ON access_grants (player_id)",
        "CREATE INDEX IF NOT EXISTS ix_access_grants_source_type ON access_grants (source_type)",
        "CREATE INDEX IF NOT EXISTS ix_access_grants_plan_code ON access_grants (plan_code)",
        "CREATE INDEX IF NOT EXISTS ix_access_grants_expires_at ON access_grants (expires_at)",
        "CREATE INDEX IF NOT EXISTS ix_access_grants_revoked_at ON access_grants (revoked_at)",
        "CREATE INDEX IF NOT EXISTS ix_node_links_node_id ON node_links (node_id)",
        "CREATE INDEX IF NOT EXISTS ix_node_links_subject_key ON node_links (subject_key)",
        "CREATE INDEX IF NOT EXISTS ix_node_links_source_kind ON node_links (source_kind)",
        "CREATE INDEX IF NOT EXISTS ix_node_links_review_status ON node_links (review_status)",
        "CREATE INDEX IF NOT EXISTS ix_app_settings_key ON app_settings (key)",
    ]

    with engine.begin() as connection:
        for statement in index_statements:
            connection.execute(text(statement))


def backfill_schema_defaults():
    db: Session = SessionLocal()
    now = _utcnow()
    changed = False
    try:
        for player in db.query(Player).all():
            if apply_player_defaults(player):
                changed = True
            if not player.created_at:
                player.created_at = now
                changed = True
            if not player.updated_at:
                player.updated_at = player.created_at or now
                changed = True
            if player.password_hash and not player.password_changed_at:
                player.password_changed_at = player.created_at or now
                changed = True
            if player.openai_api_key_encrypted and not player.openai_api_key_updated_at:
                player.openai_api_key_updated_at = player.updated_at or player.created_at or now
                changed = True

        for progress in db.query(TopicProgress).all():
            derived_subject = _normalize_subject_key(progress.topic_name)
            derived_level = _extract_book_level(progress.topic_name)

            if not progress.learning_mode:
                progress.learning_mode = "teach_me"
                changed = True
            if not progress.subject_key and derived_subject:
                progress.subject_key = derived_subject
                changed = True
            if progress.book_level is None and derived_level is not None:
                progress.book_level = derived_level
                changed = True
            if progress.content_grade_level is None and derived_level is not None:
                progress.content_grade_level = derived_level
                changed = True
            if not progress.created_at:
                progress.created_at = now
                changed = True
            if not progress.updated_at:
                progress.updated_at = progress.created_at or now
                changed = True
            if not progress.last_interaction_at and (
                progress.current_node or progress.completed_nodes or progress.mastery_score > 0
            ):
                progress.last_interaction_at = progress.updated_at or progress.created_at or now
                changed = True
            if progress.status == "COMPLETED" and not progress.completed_at:
                progress.completed_at = progress.updated_at or progress.created_at or now
                changed = True
            if progress.answer_attempt_count is None:
                progress.answer_attempt_count = 0
                changed = True
            if progress.mastery_level is None:
                progress.mastery_level = max(0, min(10, int(round(float(progress.mastery_score or 0) / 10.0))))
                changed = True
            if progress.correct_answer_count is None:
                progress.correct_answer_count = 0
                changed = True
            if progress.incorrect_answer_count is None:
                progress.incorrect_answer_count = 0
                changed = True
            if progress.cumulative_score_percent is None:
                progress.cumulative_score_percent = 0
                changed = True
            if progress.total_learning_seconds is None:
                progress.total_learning_seconds = 0
                changed = True
            if progress.session_count is None:
                progress.session_count = 0
                changed = True
            if progress.current_node and not progress.current_node_started_at:
                progress.current_node_started_at = progress.last_interaction_at or progress.updated_at or now
                changed = True

        for node_progress in db.query(StudentNodeProgress).all():
            if not node_progress.learning_mode:
                node_progress.learning_mode = "teach_me"
                changed = True
            if node_progress.mastery_level is None:
                node_progress.mastery_level = 10 if node_progress.status == "COMPLETED" else 0
                changed = True

        for interaction in db.query(Interaction).all():
            if not interaction.topic_name and interaction.subject:
                interaction.topic_name = interaction.subject
                changed = True

        if changed:
            db.commit()
    except Exception as exc:
        print(f"[DB] Backfill error: {exc}")
        db.rollback()
    finally:
        db.close()

def add_mistake(username: str, topic: str, mistake_info: str):
    db: Session = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == username).first()
        if player:
            progress = db.query(TopicProgress).filter(
                TopicProgress.player_id == player.id, 
                TopicProgress.topic_name == topic
            ).first()
            if progress:
                current_mistakes = list(progress.mistakes) if progress.mistakes else []
                current_mistakes.append(mistake_info)
                progress.mistakes = current_mistakes # Reassign to trigger update
                progress.updated_at = _utcnow()
                progress.last_interaction_at = progress.updated_at
                db.commit()
    except Exception as e:
        print(f"DB Error (add_mistake): {e}")
    finally:
        db.close()

def get_mistakes(username: str, topic: str):
    db: Session = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == username).first()
        if player:
            progress = db.query(TopicProgress).filter(
                TopicProgress.player_id == player.id, 
                TopicProgress.topic_name == topic
            ).first()
            if progress and progress.mistakes:
                return list(progress.mistakes)
    except Exception as e:
        print(f"DB Error (get_mistakes): {e}")
    return []

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def update_player_progress(username: str, topic: str, xp_delta: int, mastery_delta: int):
    db: Session = SessionLocal()
    try:
        player = db.query(Player).filter(Player.username == username).first()
        if player:
            player.xp += xp_delta
            player.level = 1 + player.xp // 100
            player.updated_at = _utcnow()
            
            progress = db.query(TopicProgress).filter(
                TopicProgress.player_id == player.id, 
                TopicProgress.topic_name == topic
            ).first()
            
            if not progress:
                 now = _utcnow()
                 progress = TopicProgress(
                     player_id=player.id,
                     topic_name=topic,
                     mastery_score=0,
                     created_at=now,
                     updated_at=now,
                     last_interaction_at=now,
                 )
                 db.add(progress)

            progress.subject_key = progress.subject_key or _normalize_subject_key(topic)
            if progress.book_level is None:
                progress.book_level = _extract_book_level(topic)
            if progress.content_grade_level is None:
                progress.content_grade_level = progress.book_level
            progress.mastery_score = min(100, max(0, progress.mastery_score + mastery_delta))
            progress.updated_at = _utcnow()
            progress.last_interaction_at = progress.updated_at
            
            if progress.mastery_score >= 100:
                progress.status = "COMPLETED"
                progress.completed_at = progress.completed_at or progress.updated_at
            elif progress.status == "NOT_STARTED" and progress.mastery_score > 0:
                progress.status = "IN_PROGRESS"
                
            db.commit()
            return progress.mastery_score
        return -1
    except Exception as e:
        print(f"DB Error: {e}")
        db.rollback()
        return -1
    finally:
        db.close()

def log_interaction(
    username: str,
    subject: str,
    user_query: str,
    agent_response: str,
    source_node: str,
    session_id: str | None = None,
    topic_name: str | None = None,
    node_id: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: int | None = None,
    billing_source: str | None = None,
    service_tier: str | None = None,
    event_type: str | None = None,
    score_percent: int | None = None,
    is_correct: bool | None = None,
):
    db: Session = SessionLocal()
    try:
        estimated_cost_cents = None
        if billing_source:
            from .billing import record_interaction_usage

            estimated_cost_cents = record_interaction_usage(
                db,
                username=username,
                model_name=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                billing_source=billing_source,
                service_tier=service_tier,
            )

        interaction = Interaction(
            username=username,
            subject=subject,
            user_query=user_query,
            agent_response=agent_response,
            source_node=source_node,
            session_id=session_id,
            topic_name=topic_name or subject,
            node_id=node_id,
            model_name=model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
            billing_source=billing_source,
            service_tier=service_tier,
            estimated_cost_cents=estimated_cost_cents,
            event_type=event_type,
            score_percent=score_percent,
            is_correct=is_correct,
        )
        db.add(interaction)
        db.commit()
    except Exception as e:
        print(f"DB Error (log_interaction): {e}")
    finally:
        db.close()


def sync_subscription_catalog():
    from .billing import sync_subscription_catalog as sync_billing_catalog

    db: Session = SessionLocal()
    try:
        sync_billing_catalog(db)
    except Exception as exc:
        print(f"[DB] Billing catalog sync error: {exc}")
        db.rollback()
    finally:
        db.close()


def sync_node_link_catalog():
    from .node_links import sync_authoritative_node_links

    db: Session = SessionLocal()
    try:
        sync_authoritative_node_links(db)
    except Exception as exc:
        print(f"[DB] Node link catalog sync error: {exc}")
        db.rollback()
    finally:
        db.close()

def get_all_users():
    db: Session = SessionLocal()
    try:
        users = db.query(Player.username).all()
        return [u[0] for u in users]
    except Exception as e:
        print(f"DB Error (get_all_users): {e}")
        return []
    finally:
        db.close()
