from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class InitRequest(BaseModel):
    user_id: str # This will be the username now
    grade_level: str
    topic: str
    additional_context: Optional[str] = None

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str # [NEW]
    display_name: Optional[str] = None
    grade_level: int
    location: str
    curriculum_region: Optional[str] = None
    learning_style: str
    sex: str
    role: str
    birthday: str
    interests: str
    avatar_id: Optional[str] = "schoolgirl"
    openai_api_key: Optional[str] = None
    preferred_model: Optional[str] = None
    school_name: Optional[str] = None
    district_name: Optional[str] = None
    classroom_id: Optional[str] = None
    roster_id: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_email: Optional[str] = None

class LoginRequest(BaseModel):
    username: str
    password: str

class LogoutRequest(BaseModel):
    username: str

class PasswordResetRequest(BaseModel):
    username: str # Allow finding by username (since children might not know parent email)
    # OR email? User said "from email addresses retrieved from the userid".
    # So user inputs UserID, we find Email, and send link.

class HelpRequest(BaseModel):
    name: str
    email: str
    user_id: Optional[str] = None
    message: str

class ChatRequest(BaseModel):
    session_id: str
    message: str
    view_as_student: bool = False # Toggle mode
    grade_override: Optional[int] = None # Force content grade level

class ChatResponse(BaseModel):
    response: str
    state_snapshot: Optional[Dict] = None

class BookSelectRequest(BaseModel):
    username: str
    topic: str
    manual_mode: bool = False
    session_grade_level: Optional[int] = None # The grade effective for this session
    learning_mode: str = "teach_me"

class BookSelectResponse(BaseModel):
    session_id: str
    status: str
    xp: int
    level: int
    mastery: int
    mastery_level: int = 0
    learning_mode: str = "teach_me"
    resolved_topic: Optional[str] = None
    topic_label: Optional[str] = None
    history_summary: Optional[str] = None
    state_snapshot: Optional[Dict] = None 
    role: Optional[str] = "Student" # To inform UI to show toggle

class InitSessionRequest(BaseModel):
    username: str
    grade_level: int
    location: str
    curriculum_region: Optional[str] = None
    learning_style: str
    sex: Optional[str] = "Not Specified"
    birthday: Optional[str] = None
    interests: Optional[str] = None
    role: Optional[str] = None
    display_name: Optional[str] = None
    avatar_id: Optional[str] = None
    preferred_model: Optional[str] = None
    school_name: Optional[str] = None
    district_name: Optional[str] = None
    classroom_id: Optional[str] = None
    roster_id: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_email: Optional[str] = None
    save_profile: bool = False

class InitSessionResponse(BaseModel):
    status: str
    username: str
    grade_level: int
    avatar_id: str

class ProfileRequest(BaseModel):
    username: str

class UpdateProfileRequest(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    grade_level: Optional[int] = None
    location: Optional[str] = None
    learning_style: Optional[str] = None
    role: Optional[str] = None
    avatar_id: Optional[str] = None
    openai_api_key: Optional[str] = None
    clear_openai_api_key: bool = False
    curriculum_region: Optional[str] = None
    preferred_model: Optional[str] = None
    school_name: Optional[str] = None
    district_name: Optional[str] = None
    classroom_id: Optional[str] = None
    roster_id: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_email: Optional[str] = None

class ProfileResponse(BaseModel):
    username: str
    display_name: Optional[str] = None
    email: Optional[str] = None
    grade_level: int = 1
    location: Optional[str] = None
    learning_style: Optional[str] = None
    role: str = "Student"
    avatar_id: str
    has_personal_openai_key: bool = False
    openai_key_hint: Optional[str] = None
    account_status: str = "active"
    curriculum_region: Optional[str] = None
    preferred_model: Optional[str] = None
    school_name: Optional[str] = None
    district_name: Optional[str] = None
    classroom_id: Optional[str] = None
    roster_id: Optional[str] = None
    guardian_name: Optional[str] = None
    guardian_email: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    email_verified_at: Optional[datetime] = None
    password_changed_at: Optional[datetime] = None
    last_password_reset_requested_at: Optional[datetime] = None
    openai_api_key_updated_at: Optional[datetime] = None


class TeacherLinkRequest(BaseModel):
    username: str
    teacher_username: str
    request_note: Optional[str] = None


class TeacherLinkListRequest(BaseModel):
    username: str


class TeacherLinkActionRequest(BaseModel):
    username: str
    link_id: int
    action: str
    response_note: Optional[str] = None


class TeacherLinkRevokeRequest(BaseModel):
    username: str
    link_id: int
    reason: Optional[str] = None


class TeacherStudentProgressRequest(BaseModel):
    username: str
    student_username: str


class TeacherLinkSummary(BaseModel):
    id: int
    teacher_username: Optional[str] = None
    student_username: Optional[str] = None
    status: str
    request_note: Optional[str] = None
    response_note: Optional[str] = None
    requested_at: Optional[datetime] = None
    responded_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TeacherLinkListResponse(BaseModel):
    links: List[TeacherLinkSummary] = Field(default_factory=list)


class TeacherStudentSummary(BaseModel):
    teacher_link_id: Optional[int] = None
    username: str
    display_name: Optional[str] = None
    grade_level: int
    last_login_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    current_topic: Optional[str] = None
    current_node: Optional[str] = None
    grade_completion: float = 0.0
    subject_completion: Dict[str, float] = Field(default_factory=dict)
    total_answer_attempts: int = 0
    correct_answer_count: int = 0
    incorrect_answer_count: int = 0
    average_score_percent: float = 0.0
    correct_rate_percent: float = 0.0
    total_learning_seconds: int = 0
    total_login_seconds: int = 0
    total_request_count: int = 0
    total_chat_turns: int = 0
    session_count: int = 0
    active_topic_count: int = 0
    linked_at: Optional[datetime] = None


class StudentTopicProgressSummary(BaseModel):
    topic_name: str
    subject_key: Optional[str] = None
    book_level: Optional[int] = None
    learning_mode: str = "teach_me"
    status: str
    mastery_score: int = 0
    mastery_level: int = 0
    current_node: Optional[str] = None
    completed_nodes_count: int = 0
    answer_attempt_count: int = 0
    correct_answer_count: int = 0
    incorrect_answer_count: int = 0
    average_score_percent: float = 0.0
    total_learning_seconds: int = 0
    session_count: int = 0
    last_interaction_at: Optional[datetime] = None
    last_answered_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StudentNodeProgressSummary(BaseModel):
    topic_name: str
    node_id: str
    subject_key: Optional[str] = None
    book_level: Optional[int] = None
    learning_mode: str = "teach_me"
    status: str
    mastery_level: int = 0
    attempt_count: int = 0
    correct_count: int = 0
    incorrect_count: int = 0
    average_score_percent: float = 0.0
    total_learning_seconds: int = 0
    last_score_percent: Optional[int] = None
    last_problem: Optional[str] = None
    last_answer: Optional[str] = None
    last_feedback: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class StudentActivitySessionSummary(BaseModel):
    started_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    total_active_seconds: int = 0
    request_count: int = 0
    chat_turn_count: int = 0
    last_topic_name: Optional[str] = None
    last_node_id: Optional[str] = None


class TeacherDashboardResponse(BaseModel):
    pending_requests: List[TeacherLinkSummary] = Field(default_factory=list)
    accepted_students: List[TeacherStudentSummary] = Field(default_factory=list)


class TeacherStudentProgressResponse(BaseModel):
    teacher_link: Optional[TeacherLinkSummary] = None
    student: TeacherStudentSummary
    topics: List[StudentTopicProgressSummary] = Field(default_factory=list)
    nodes: List[StudentNodeProgressSummary] = Field(default_factory=list)
    recent_sessions: List[StudentActivitySessionSummary] = Field(default_factory=list)


class HostedModelConfigRequest(BaseModel):
    username: str


class UpdateHostedModelConfigRequest(BaseModel):
    username: str
    teacher_model: Optional[str] = None
    verifier_model: Optional[str] = None
    main_model: Optional[str] = None
    teacher_priority_enabled: bool = False
    verifier_priority_enabled: bool = False
    main_priority_enabled: Optional[bool] = None
    fast_priority_enabled: bool = False
    fast_model: str


class HostedModelOptionSummary(BaseModel):
    model_id: str
    provider: str
    display_name: str
    description: Optional[str] = None
    input_price_per_1m: Optional[float] = None
    output_price_per_1m: Optional[float] = None
    priority_input_price_per_1m: Optional[float] = None
    priority_output_price_per_1m: Optional[float] = None
    supports_priority: bool = False
    required_env_var: Optional[str] = None
    is_available: bool = False


class HostedModelConfigResponse(BaseModel):
    teacher_model: str
    verifier_model: str
    fast_model: str
    teacher_priority_enabled: bool = False
    verifier_priority_enabled: bool = False
    fast_priority_enabled: bool = False
    teacher_provider: str
    verifier_provider: str
    fast_provider: str
    teacher_display_name: Optional[str] = None
    verifier_display_name: Optional[str] = None
    fast_display_name: Optional[str] = None
    main_model: str
    main_priority_enabled: bool = False
    main_provider: str
    main_display_name: Optional[str] = None
    catalog: List[HostedModelOptionSummary] = Field(default_factory=list)


class BillingStatusRequest(BaseModel):
    username: str


class BillingCheckoutRequest(BaseModel):
    username: str
    plan_code: str


class BillingPortalRequest(BaseModel):
    username: str


class BillingPlanSummary(BaseModel):
    plan_code: str
    display_name: str
    description: Optional[str] = None
    monthly_price_cents: int
    currency: str = "usd"
    includes_hosted_usage: bool = False
    requires_personal_key: bool = False
    monthly_tutor_turn_cap: Optional[int] = None
    monthly_llm_call_cap: Optional[int] = None
    monthly_input_token_cap: Optional[int] = None
    monthly_output_token_cap: Optional[int] = None
    monthly_cost_cap_cents: Optional[int] = None
    hosted_main_model: Optional[str] = None
    hosted_fast_model: Optional[str] = None
    is_recommended: bool = False


class BillingUsageSummary(BaseModel):
    cycle_start: Optional[datetime] = None
    cycle_end: Optional[datetime] = None
    tutor_turns_used: int = 0
    llm_calls_used: int = 0
    input_tokens_used: int = 0
    output_tokens_used: int = 0
    estimated_cost_cents: int = 0


class BillingStatusResponse(BaseModel):
    billing_enabled: bool = False
    billing_enforced: bool = False
    checkout_available: bool = False
    portal_available: bool = False
    uses_personal_key: bool = False
    recommended_plan_code: Optional[str] = None
    effective_plan_code: Optional[str] = None
    access_source_type: Optional[str] = None
    access_source_label: Optional[str] = None
    access_grant_expires_at: Optional[datetime] = None
    subscription_plan_code: Optional[str] = None
    subscription_status: Optional[str] = None
    subscription_current_period_end: Optional[datetime] = None
    cancel_at_period_end: bool = False
    payment_method_brand: Optional[str] = None
    payment_method_last4: Optional[str] = None
    usage: BillingUsageSummary
    plans: List[BillingPlanSummary]
    access_allowed: bool = True
    access_reason: Optional[str] = None
    active_hosted_model: Optional[str] = None
    active_verifier_model: Optional[str] = None
    active_fast_model: Optional[str] = None


class BillingCheckoutResponse(BaseModel):
    url: str


class BillingPortalResponse(BaseModel):
    url: str


class RedeemAccessCodeRequest(BaseModel):
    username: str
    code: str


class RedeemAccessCodeResponse(BaseModel):
    status: str
    plan_code: str
    access_source_type: str
    expires_at: Optional[datetime] = None
    message: Optional[str] = None


class CreatePromoCodeRequest(BaseModel):
    username: str
    plan_code: str
    assigned_username: Optional[str] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    duration_days: Optional[int] = None
    max_redemptions: int = 1
    code: Optional[str] = None
    notes: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class GrantAccessRequest(BaseModel):
    username: str
    target_username: str
    plan_code: str
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    duration_days: Optional[int] = None
    notes: Optional[str] = None
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class RevokeAccessGrantRequest(BaseModel):
    username: str
    access_grant_id: int
    reason: Optional[str] = None


class RevokePromoCodeRequest(BaseModel):
    username: str
    promo_code_id: int
    reason: Optional[str] = None
    revoke_grants: bool = True


class ListAccessGrantsRequest(BaseModel):
    username: str
    target_username: Optional[str] = None
    include_revoked: bool = False


class ListPromoCodesRequest(BaseModel):
    username: str
    assigned_username: Optional[str] = None
    include_revoked: bool = False


class AccessGrantSummary(BaseModel):
    id: int
    username: Optional[str] = None
    plan_code: str
    source_type: str
    source_id: Optional[int] = None
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by_username: Optional[str] = None


class PromoCodeSummary(BaseModel):
    id: int
    code_prefix: Optional[str] = None
    assigned_username: Optional[str] = None
    plan_code: str
    starts_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    max_redemptions: int = 1
    redemption_count: int = 0
    revoked_at: Optional[datetime] = None
    revocation_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by_username: Optional[str] = None


class CreatePromoCodeResponse(BaseModel):
    promo_code: PromoCodeSummary
    code: str


class AccessGrantListResponse(BaseModel):
    grants: List[AccessGrantSummary] = Field(default_factory=list)


class PromoCodeListResponse(BaseModel):
    promo_codes: List[PromoCodeSummary] = Field(default_factory=list)


class ResumeShelfRequest(BaseModel):
    username: str
    shelf_category: str # e.g. "Math" (Optional, if we want to just resume general)
    learning_mode: str = "teach_me"

class ResumeShelfResponse(BaseModel):
    topic: str
    reason: str
    learning_mode: str = "teach_me"
    topic_label: Optional[str] = None

class PlayerStatsRequest(BaseModel):
    username: str

class GraphDataRequest(BaseModel):
    topic: str
    username: str
    focus_node_id: Optional[str] = None # Center of the window
    window_size: int = 20 # Total nodes to return (half before, half after)

class GraphNode(BaseModel):
    id: str
    label: str
    grade_level: int
    type: str # topic, subtopic, concept
    status: str # locked, available, completed, current
    mastery_level: int = 0
    is_tentative: bool = False
    parent: Optional[str] = None
    authoritative_link_count: int = 0
    approved_user_link_count: int = 0
    pending_user_link_count: int = 0

class GraphDataResponse(BaseModel):
    nodes: List[GraphNode]

class SetCurrentNodeRequest(BaseModel):
    username: str
    topic: str
    node_id: str


class NodeLinksRequest(BaseModel):
    username: str
    node_id: str
    topic: Optional[str] = None


class SubmitNodeLinkRequest(BaseModel):
    username: str
    node_id: str
    topic: Optional[str] = None
    title: str
    url: str
    description: Optional[str] = None
    provider: Optional[str] = None
    link_type: Optional[str] = "general"
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewNodeLinkRequest(BaseModel):
    username: str
    link_id: int
    review_status: str
    review_notes: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class PendingNodeLinksRequest(BaseModel):
    username: str
    review_status: Optional[str] = "pending"
    node_id: Optional[str] = None


class NodeLinkSummary(BaseModel):
    id: int
    node_id: str
    subject_key: Optional[str] = None
    title: str
    url: str
    description: Optional[str] = None
    provider: Optional[str] = None
    link_type: str = "general"
    source_kind: str
    review_status: str
    review_notes: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    extra_metadata: Dict[str, Any] = Field(default_factory=dict)
    submitted_by_username: Optional[str] = None
    reviewed_by_username: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class NodeLinksResponse(BaseModel):
    authoritative_links: List[NodeLinkSummary] = Field(default_factory=list)
    approved_user_links: List[NodeLinkSummary] = Field(default_factory=list)
    pending_user_links: List[NodeLinkSummary] = Field(default_factory=list)
    is_admin: bool = False


class SubmitNodeLinkResponse(BaseModel):
    status: str
    link: NodeLinkSummary


class PendingNodeLinksResponse(BaseModel):
    links: List[NodeLinkSummary] = Field(default_factory=list)
