from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime
import os

from fastapi import HTTPException

from .access_grants import get_access_source_label, get_active_access_grant
from .config import load_local_env, load_repo_json_file

load_local_env()

STRIPE_PROVIDER = "stripe"
PLAN_BYOK_MONTHLY = "byok_monthly"
PLAN_HOSTED_MONTHLY = "hosted_monthly"
BILLING_CONFIG_FILENAME = "billing_config.json"


@dataclass(frozen=True)
class PlanDefinition:
    plan_code: str
    display_name: str
    description: str
    monthly_price_cents: int
    currency: str
    includes_hosted_usage: bool
    requires_personal_key: bool
    monthly_tutor_turn_cap: int | None
    monthly_llm_call_cap: int | None
    monthly_input_token_cap: int | None
    monthly_output_token_cap: int | None
    monthly_cost_cap_cents: int | None
    hosted_main_model: str | None
    hosted_fast_model: str | None
    stripe_price_id: str | None


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int | None) -> int | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_float(name: str, default: float | None) -> float | None:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _billing_config() -> dict:
    return load_repo_json_file(BILLING_CONFIG_FILENAME)


def _plans_config() -> dict:
    payload = _billing_config().get("plans", {})
    return payload if isinstance(payload, dict) else {}


def _plan_config(plan_code: str) -> dict:
    payload = _plans_config().get(plan_code, {})
    return payload if isinstance(payload, dict) else {}


def _model_pricing_config() -> dict:
    payload = _billing_config().get("model_pricing", {})
    return payload if isinstance(payload, dict) else {}


def _config_int(name: str, default: int | None) -> int | None:
    return _env_int(name, default)


def _config_float(name: str, default: float | None) -> float | None:
    return _env_float(name, default)


def _billing_currency() -> str:
    return os.getenv("BILLING_CURRENCY", _billing_config().get("currency", "usd"))


def _month_window(now: datetime) -> tuple[datetime, datetime]:
    cycle_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = monthrange(now.year, now.month)[1]
    cycle_end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)
    return cycle_start, cycle_end


def _stripe_timestamp_to_datetime(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.utcfromtimestamp(int(value))
    except (TypeError, ValueError, OSError):
        return None


def get_hosted_models() -> tuple[str, str]:
    hosted_plan = _plan_config(PLAN_HOSTED_MONTHLY)
    default_main = hosted_plan.get("hosted_main_model", "gpt-5-mini")
    main_model = os.getenv("OPENAI_MODEL", default_main)
    fast_model = os.getenv("OPENAI_FAST_MODEL", hosted_plan.get("hosted_fast_model", main_model))
    return main_model, fast_model


def get_plan_definitions() -> list[PlanDefinition]:
    hosted_main_model, hosted_fast_model = get_hosted_models()
    byok_config = _plan_config(PLAN_BYOK_MONTHLY)
    hosted_config = _plan_config(PLAN_HOSTED_MONTHLY)
    return [
        PlanDefinition(
            plan_code=PLAN_BYOK_MONTHLY,
            display_name=byok_config.get("display_name", "Bring Your Own Key"),
            description=byok_config.get("description", "Use your own OpenAI API key inside Adaptive Tutor."),
            monthly_price_cents=_config_int("PLAN_BYOK_MONTHLY_PRICE_CENTS", byok_config.get("monthly_price_cents", 99)) or 99,
            currency=_billing_currency(),
            includes_hosted_usage=bool(byok_config.get("includes_hosted_usage", False)),
            requires_personal_key=bool(byok_config.get("requires_personal_key", True)),
            monthly_tutor_turn_cap=_config_int("PLAN_BYOK_MONTHLY_TUTOR_TURN_CAP", byok_config.get("monthly_tutor_turn_cap")),
            monthly_llm_call_cap=_config_int("PLAN_BYOK_MONTHLY_LLM_CALL_CAP", byok_config.get("monthly_llm_call_cap")),
            monthly_input_token_cap=_config_int("PLAN_BYOK_MONTHLY_INPUT_TOKEN_CAP", byok_config.get("monthly_input_token_cap")),
            monthly_output_token_cap=_config_int("PLAN_BYOK_MONTHLY_OUTPUT_TOKEN_CAP", byok_config.get("monthly_output_token_cap")),
            monthly_cost_cap_cents=_config_int("PLAN_BYOK_MONTHLY_COST_CAP_CENTS", byok_config.get("monthly_cost_cap_cents")),
            hosted_main_model=None,
            hosted_fast_model=None,
            stripe_price_id=os.getenv("STRIPE_PRICE_ID_BYOK_MONTHLY"),
        ),
        PlanDefinition(
            plan_code=PLAN_HOSTED_MONTHLY,
            display_name=hosted_config.get("display_name", "Hosted AI Tutor"),
            description=hosted_config.get("description", "Adaptive Tutor includes OpenAI usage with GPT-5 mini and built-in monthly caps."),
            monthly_price_cents=_config_int("PLAN_HOSTED_MONTHLY_PRICE_CENTS", hosted_config.get("monthly_price_cents", 499)) or 499,
            currency=_billing_currency(),
            includes_hosted_usage=bool(hosted_config.get("includes_hosted_usage", True)),
            requires_personal_key=bool(hosted_config.get("requires_personal_key", False)),
            monthly_tutor_turn_cap=_config_int("PLAN_HOSTED_MONTHLY_TUTOR_TURN_CAP", hosted_config.get("monthly_tutor_turn_cap", 1200)),
            monthly_llm_call_cap=_config_int("PLAN_HOSTED_MONTHLY_LLM_CALL_CAP", hosted_config.get("monthly_llm_call_cap", 2500)),
            monthly_input_token_cap=_config_int("PLAN_HOSTED_MONTHLY_INPUT_TOKEN_CAP", hosted_config.get("monthly_input_token_cap", 5_000_000)),
            monthly_output_token_cap=_config_int("PLAN_HOSTED_MONTHLY_OUTPUT_TOKEN_CAP", hosted_config.get("monthly_output_token_cap", 750_000)),
            monthly_cost_cap_cents=_config_int("PLAN_HOSTED_MONTHLY_COST_CAP_CENTS", hosted_config.get("monthly_cost_cap_cents", 250)),
            hosted_main_model=hosted_main_model,
            hosted_fast_model=hosted_fast_model,
            stripe_price_id=os.getenv("STRIPE_PRICE_ID_HOSTED_MONTHLY"),
        ),
    ]


def get_plan_definition(plan_code: str | None) -> PlanDefinition | None:
    for definition in get_plan_definitions():
        if definition.plan_code == plan_code:
            return definition
    return None


def billing_is_enforced() -> bool:
    return not _env_bool("ALLOW_OPEN_TUTORING_ACCESS", False)


def billing_is_configured() -> bool:
    return bool(
        os.getenv("STRIPE_SECRET_KEY")
        and os.getenv("STRIPE_PRICE_ID_BYOK_MONTHLY")
        and os.getenv("STRIPE_PRICE_ID_HOSTED_MONTHLY")
    )


def stripe_checkout_is_available() -> bool:
    return billing_is_configured()


def stripe_portal_is_available() -> bool:
    return bool(os.getenv("STRIPE_SECRET_KEY"))


def get_billing_success_url() -> str:
    public_base = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return os.getenv("STRIPE_SUCCESS_URL", f"{public_base}/billing/success")


def get_billing_cancel_url() -> str:
    public_base = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return os.getenv("STRIPE_CANCEL_URL", f"{public_base}/billing/cancel")


def get_billing_portal_return_url() -> str:
    public_base = os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    return os.getenv("STRIPE_PORTAL_RETURN_URL", f"{public_base}/billing/manage-return")


def _active_subscription_statuses() -> set[str]:
    statuses = {"active", "trialing"}
    if _env_bool("BILLING_ALLOW_PAST_DUE_ACCESS", False):
        statuses.add("past_due")
    return statuses


def _get_stripe():
    try:
        import stripe
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Stripe support is not installed on the server.") from exc

    secret_key = os.getenv("STRIPE_SECRET_KEY")
    if not secret_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured.")

    stripe.api_key = secret_key
    return stripe


def _plan_code_from_price_id(price_id: str | None) -> str | None:
    if not price_id:
        return None
    for definition in get_plan_definitions():
        if definition.stripe_price_id == price_id:
            return definition.plan_code
    return None


def _current_cycle_window(subscription) -> tuple[datetime, datetime]:
    now = datetime.utcnow()
    if subscription and subscription.current_period_start and subscription.current_period_end:
        return subscription.current_period_start, subscription.current_period_end
    return _month_window(now)


def get_current_subscription(db, player):
    from .database import Subscription

    return db.query(Subscription).filter(
        Subscription.player_id == player.id
    ).order_by(
        Subscription.current_period_end.desc(),
        Subscription.updated_at.desc(),
    ).first()


def get_plan_record(db, plan_code: str | None):
    from .database import SubscriptionPlan

    if not plan_code:
        return None
    return db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_code == plan_code).first()


def _subscription_has_access(subscription) -> bool:
    if not subscription:
        return False
    if subscription.status not in _active_subscription_statuses():
        return False
    if subscription.current_period_end and subscription.current_period_end < datetime.utcnow():
        return False
    return True


def get_or_create_usage_cycle(db, player, subscription, plan, now: datetime | None = None):
    from .database import UsageCycle

    current_time = now or datetime.utcnow()
    cycle_start, cycle_end = _current_cycle_window(subscription)
    cycle = db.query(UsageCycle).filter(
        UsageCycle.player_id == player.id,
        UsageCycle.plan_code == plan.plan_code,
        UsageCycle.cycle_start == cycle_start,
        UsageCycle.cycle_end == cycle_end,
    ).first()
    if cycle:
        return cycle

    cycle = UsageCycle(
        player_id=player.id,
        plan_code=plan.plan_code,
        cycle_start=cycle_start,
        cycle_end=cycle_end,
        created_at=current_time,
        updated_at=current_time,
    )
    db.add(cycle)
    db.flush()
    return cycle


def get_billing_state(db, player) -> dict:
    sync_subscription_catalog(db)

    active_access_grant = get_active_access_grant(db, player.id)
    subscription = get_current_subscription(db, player)
    plan = get_plan_record(
        db,
        active_access_grant.plan_code if active_access_grant else (
            subscription.plan_code if subscription else player.subscription_plan_code
        ),
    )
    uses_personal_key = bool(player.openai_api_key_encrypted)
    recommended_plan_code = PLAN_BYOK_MONTHLY if uses_personal_key else PLAN_HOSTED_MONTHLY

    usage_cycle = None
    allowed = True
    reason = None
    access_source_type = None
    access_source_label = None

    if active_access_grant:
        access_source_type = active_access_grant.source_type
        access_source_label = get_access_source_label(active_access_grant)
        if not plan:
            allowed = False
            reason = "Your access grant references a plan that could not be resolved."
        elif plan.requires_personal_key and not uses_personal_key:
            allowed = False
            reason = "This access grant requires a personal OpenAI API key."
        elif not uses_personal_key and not plan.includes_hosted_usage:
            allowed = False
            reason = "This access grant does not include hosted AI usage."
        else:
            usage_cycle = get_or_create_usage_cycle(db, player, None, plan)
    elif billing_is_enforced():
        if not billing_is_configured():
            allowed = False
            reason = "Billing is not configured on the server."
        elif not _subscription_has_access(subscription):
            allowed = False
            reason = "Tutoring access requires an active subscription or access code."
        elif not plan:
            allowed = False
            reason = "Your subscription plan could not be resolved."
        elif plan.requires_personal_key and not uses_personal_key:
            allowed = False
            reason = "This subscription requires a personal OpenAI API key."
        elif not uses_personal_key and not plan.includes_hosted_usage:
            allowed = False
            reason = "Your subscription does not include hosted AI usage."
        else:
            access_source_type = "subscription"
            access_source_label = "Stripe subscription"
            usage_cycle = get_or_create_usage_cycle(db, player, subscription, plan)
    elif plan and subscription:
        access_source_type = "subscription"
        access_source_label = "Stripe subscription"
        usage_cycle = get_or_create_usage_cycle(db, player, subscription, plan)

    if allowed and usage_cycle and plan and not uses_personal_key:
        if plan.monthly_tutor_turn_cap is not None and usage_cycle.tutor_turns_used >= plan.monthly_tutor_turn_cap:
            allowed = False
            reason = "Monthly tutor-turn limit reached for this access plan."
        elif plan.monthly_llm_call_cap is not None and usage_cycle.llm_calls_used >= plan.monthly_llm_call_cap:
            allowed = False
            reason = "Monthly LLM call limit reached for this access plan."
        elif plan.monthly_input_token_cap is not None and usage_cycle.input_tokens_used >= plan.monthly_input_token_cap:
            allowed = False
            reason = "Monthly input token limit reached for this access plan."
        elif plan.monthly_output_token_cap is not None and usage_cycle.output_tokens_used >= plan.monthly_output_token_cap:
            allowed = False
            reason = "Monthly output token limit reached for this access plan."
        elif plan.monthly_cost_cap_cents is not None and usage_cycle.estimated_cost_cents >= plan.monthly_cost_cap_cents:
            allowed = False
            reason = "Monthly hosted AI budget reached for this access plan."

    return {
        "allowed": allowed,
        "reason": reason,
        "active_access_grant": active_access_grant,
        "subscription": subscription,
        "plan": plan,
        "usage_cycle": usage_cycle,
        "uses_personal_key": uses_personal_key,
        "recommended_plan_code": recommended_plan_code,
        "effective_plan_code": plan.plan_code if plan else None,
        "access_source_type": access_source_type,
        "access_source_label": access_source_label,
    }


def assert_tutoring_access(db, player):
    state = get_billing_state(db, player)
    if not state["allowed"]:
        raise HTTPException(status_code=402, detail=state["reason"])
    return state


def increment_tutor_turn_usage(db, player):
    state = get_billing_state(db, player)
    usage_cycle = state.get("usage_cycle")
    if usage_cycle:
        usage_cycle.tutor_turns_used += 1
        usage_cycle.updated_at = datetime.utcnow()
    return state


def record_interaction_usage(
    db,
    username: str,
    model_name: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    billing_source: str | None,
) -> int | None:
    from .database import Player

    if billing_source != "platform":
        return 0 if billing_source else None

    player = db.query(Player).filter(Player.username == username).first()
    if not player:
        return None

    estimated_cost_cents = estimate_model_cost_cents(model_name, input_tokens, output_tokens)
    state = get_billing_state(db, player)
    usage_cycle = state.get("usage_cycle")
    if usage_cycle:
        usage_cycle.llm_calls_used += 1
        usage_cycle.input_tokens_used += int(input_tokens or 0)
        usage_cycle.output_tokens_used += int(output_tokens or 0)
        usage_cycle.estimated_cost_cents += int(estimated_cost_cents or 0)
        usage_cycle.updated_at = datetime.utcnow()
    return estimated_cost_cents


def estimate_model_cost_cents(model_name: str | None, input_tokens: int | None, output_tokens: int | None) -> int | None:
    if not model_name:
        return None

    hosted_main_model, hosted_fast_model = get_hosted_models()
    pricing_defaults = _model_pricing_config()
    main_defaults = pricing_defaults.get(hosted_main_model, {})
    fast_defaults = pricing_defaults.get(hosted_fast_model, {})
    pricing_map = {
        hosted_main_model: (
            _config_float("OPENAI_MODEL_INPUT_PRICE_PER_1M", main_defaults.get("input_price_per_1m", 0.25)),
            _config_float("OPENAI_MODEL_OUTPUT_PRICE_PER_1M", main_defaults.get("output_price_per_1m", 2.0)),
        ),
        hosted_fast_model: (
            _config_float("OPENAI_FAST_MODEL_INPUT_PRICE_PER_1M", fast_defaults.get("input_price_per_1m", 0.25)),
            _config_float("OPENAI_FAST_MODEL_OUTPUT_PRICE_PER_1M", fast_defaults.get("output_price_per_1m", 2.0)),
        ),
    }
    for configured_model, configured_prices in pricing_defaults.items():
        if configured_model in pricing_map or not isinstance(configured_prices, dict):
            continue
        pricing_map[configured_model] = (
            configured_prices.get("input_price_per_1m"),
            configured_prices.get("output_price_per_1m"),
        )
    pricing = pricing_map.get(model_name)
    if pricing is None:
        return None

    input_price, output_price = pricing
    if input_price is None or output_price is None:
        return None

    input_cost = (float(input_tokens or 0) / 1_000_000.0) * input_price
    output_cost = (float(output_tokens or 0) / 1_000_000.0) * output_price
    return int(round((input_cost + output_cost) * 100))


def sync_subscription_catalog(db):
    from .database import SubscriptionPlan

    now = datetime.utcnow()
    changed = False
    for definition in get_plan_definitions():
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.plan_code == definition.plan_code).first()
        if not plan:
            plan = SubscriptionPlan(plan_code=definition.plan_code, created_at=now)
            db.add(plan)
            changed = True

        plan.display_name = definition.display_name
        plan.description = definition.description
        plan.provider = STRIPE_PROVIDER
        plan.stripe_price_id = definition.stripe_price_id
        plan.monthly_price_cents = definition.monthly_price_cents
        plan.currency = definition.currency
        plan.includes_hosted_usage = definition.includes_hosted_usage
        plan.requires_personal_key = definition.requires_personal_key
        plan.is_active = True
        plan.monthly_tutor_turn_cap = definition.monthly_tutor_turn_cap
        plan.monthly_llm_call_cap = definition.monthly_llm_call_cap
        plan.monthly_input_token_cap = definition.monthly_input_token_cap
        plan.monthly_output_token_cap = definition.monthly_output_token_cap
        plan.monthly_cost_cap_cents = definition.monthly_cost_cap_cents
        plan.hosted_main_model = definition.hosted_main_model
        plan.hosted_fast_model = definition.hosted_fast_model
        plan.updated_at = now
        changed = True

    if changed:
        db.commit()


def _serialize_plan(plan, recommended_plan_code: str | None) -> dict:
    return {
        "plan_code": plan.plan_code,
        "display_name": plan.display_name,
        "description": plan.description,
        "monthly_price_cents": plan.monthly_price_cents,
        "currency": plan.currency,
        "includes_hosted_usage": bool(plan.includes_hosted_usage),
        "requires_personal_key": bool(plan.requires_personal_key),
        "monthly_tutor_turn_cap": plan.monthly_tutor_turn_cap,
        "monthly_llm_call_cap": plan.monthly_llm_call_cap,
        "monthly_input_token_cap": plan.monthly_input_token_cap,
        "monthly_output_token_cap": plan.monthly_output_token_cap,
        "monthly_cost_cap_cents": plan.monthly_cost_cap_cents,
        "hosted_main_model": plan.hosted_main_model,
        "hosted_fast_model": plan.hosted_fast_model,
        "is_recommended": plan.plan_code == recommended_plan_code,
    }


def build_billing_status(db, player) -> dict:
    from .database import SubscriptionPlan

    state = get_billing_state(db, player)
    subscription = state["subscription"]
    plan = state["plan"]
    usage_cycle = state["usage_cycle"]

    plan_rows = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active.is_(True)).order_by(
        SubscriptionPlan.monthly_price_cents.asc()
    ).all()

    return {
        "billing_enabled": billing_is_configured(),
        "billing_enforced": billing_is_enforced(),
        "checkout_available": stripe_checkout_is_available(),
        "portal_available": stripe_portal_is_available() and bool(player.stripe_customer_id),
        "uses_personal_key": state["uses_personal_key"],
        "recommended_plan_code": state["recommended_plan_code"],
        "effective_plan_code": state["effective_plan_code"],
        "access_source_type": state["access_source_type"],
        "access_source_label": state["access_source_label"],
        "access_grant_expires_at": state["active_access_grant"].expires_at if state["active_access_grant"] else None,
        "subscription_plan_code": subscription.plan_code if subscription else player.subscription_plan_code,
        "subscription_status": subscription.status if subscription else player.subscription_status_cached,
        "subscription_current_period_end": subscription.current_period_end if subscription else player.subscription_current_period_end,
        "cancel_at_period_end": bool(subscription.cancel_at_period_end) if subscription else False,
        "payment_method_brand": player.payment_method_brand,
        "payment_method_last4": player.payment_method_last4,
        "usage": {
            "cycle_start": usage_cycle.cycle_start if usage_cycle else None,
            "cycle_end": usage_cycle.cycle_end if usage_cycle else None,
            "tutor_turns_used": usage_cycle.tutor_turns_used if usage_cycle else 0,
            "llm_calls_used": usage_cycle.llm_calls_used if usage_cycle else 0,
            "input_tokens_used": usage_cycle.input_tokens_used if usage_cycle else 0,
            "output_tokens_used": usage_cycle.output_tokens_used if usage_cycle else 0,
            "estimated_cost_cents": usage_cycle.estimated_cost_cents if usage_cycle else 0,
        },
        "plans": [_serialize_plan(plan_row, state["recommended_plan_code"]) for plan_row in plan_rows],
        "access_allowed": state["allowed"],
        "access_reason": state["reason"],
        "active_hosted_model": plan.hosted_main_model if plan else None,
    }


def _ensure_customer(db, player) -> str:
    stripe = _get_stripe()
    if player.stripe_customer_id:
        return player.stripe_customer_id

    customer = stripe.Customer.create(
        email=player.email,
        name=player.display_name or player.username,
        metadata={"username": player.username},
    )
    player.stripe_customer_id = customer.id
    player.billing_provider = STRIPE_PROVIDER
    db.flush()
    return customer.id


def create_checkout_session(db, player, plan_code: str) -> str:
    stripe = _get_stripe()
    sync_subscription_catalog(db)
    plan = get_plan_record(db, plan_code)
    if not plan or not plan.is_active:
        raise HTTPException(status_code=404, detail="Subscription plan not found.")
    if not plan.stripe_price_id:
        raise HTTPException(status_code=503, detail="This plan is not configured in Stripe yet.")
    if plan.requires_personal_key and not player.openai_api_key_encrypted:
        raise HTTPException(status_code=400, detail="This plan requires a personal OpenAI API key on your profile.")

    current_subscription = get_current_subscription(db, player)
    if _subscription_has_access(current_subscription):
        raise HTTPException(status_code=400, detail="An active subscription already exists. Use Manage Billing instead.")

    customer_id = _ensure_customer(db, player)
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        customer=customer_id,
        client_reference_id=player.username,
        success_url=get_billing_success_url(),
        cancel_url=get_billing_cancel_url(),
        line_items=[{"price": plan.stripe_price_id, "quantity": 1}],
        allow_promotion_codes=True,
        metadata={
            "username": player.username,
            "plan_code": plan.plan_code,
        },
    )
    db.commit()
    return checkout_session.url


def create_billing_portal_session(db, player) -> str:
    stripe = _get_stripe()
    if not player.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No Stripe customer is associated with this account yet.")

    session = stripe.billing_portal.Session.create(
        customer=player.stripe_customer_id,
        return_url=get_billing_portal_return_url(),
    )
    return session.url


def _store_payment_method_snapshot(db, player, customer_id: str | None):
    if not customer_id:
        return

    stripe = _get_stripe()
    try:
        customer = stripe.Customer.retrieve(
            customer_id,
            expand=["invoice_settings.default_payment_method"],
        )
    except Exception:
        return

    payment_method = customer.get("invoice_settings", {}).get("default_payment_method")
    if isinstance(payment_method, str) or not payment_method:
        return

    card_details = payment_method.get("card") or {}
    player.payment_method_brand = card_details.get("brand")
    player.payment_method_last4 = card_details.get("last4")
    player.payment_method_exp_month = card_details.get("exp_month")
    player.payment_method_exp_year = card_details.get("exp_year")


def _update_player_subscription_cache(player, subscription):
    player.billing_provider = STRIPE_PROVIDER
    player.subscription_plan_code = subscription.plan_code
    player.subscription_status_cached = subscription.status
    player.subscription_current_period_end = subscription.current_period_end


def _upsert_subscription_from_object(db, player, subscription_object, plan_code_hint: str | None = None):
    from .database import Subscription

    provider_subscription_id = subscription_object.get("id")
    subscription = db.query(Subscription).filter(
        Subscription.provider_subscription_id == provider_subscription_id
    ).first()
    if not subscription:
        subscription = Subscription(
            player_id=player.id,
            provider=STRIPE_PROVIDER,
            provider_subscription_id=provider_subscription_id,
        )
        db.add(subscription)

    price_id = None
    items = subscription_object.get("items", {}).get("data", [])
    if items:
        price_id = items[0].get("price", {}).get("id")

    subscription.plan_code = plan_code_hint or _plan_code_from_price_id(price_id) or player.subscription_plan_code or PLAN_HOSTED_MONTHLY
    subscription.provider_customer_id = subscription_object.get("customer")
    subscription.status = subscription_object.get("status", "inactive")
    subscription.current_period_start = _stripe_timestamp_to_datetime(subscription_object.get("current_period_start"))
    subscription.current_period_end = _stripe_timestamp_to_datetime(subscription_object.get("current_period_end"))
    subscription.cancel_at_period_end = bool(subscription_object.get("cancel_at_period_end", False))
    subscription.canceled_at = _stripe_timestamp_to_datetime(subscription_object.get("canceled_at"))
    subscription.trial_end = _stripe_timestamp_to_datetime(subscription_object.get("trial_end"))
    subscription.latest_invoice_id = subscription_object.get("latest_invoice")
    subscription.updated_at = datetime.utcnow()

    player.stripe_customer_id = subscription.provider_customer_id or player.stripe_customer_id
    _update_player_subscription_cache(player, subscription)
    return subscription


def sync_subscription_from_stripe(db, player, subscription_id: str | None, customer_id: str | None = None, plan_code_hint: str | None = None):
    if not subscription_id:
        return None

    stripe = _get_stripe()
    subscription_object = stripe.Subscription.retrieve(subscription_id)
    subscription = _upsert_subscription_from_object(db, player, subscription_object, plan_code_hint=plan_code_hint)
    if customer_id:
        player.stripe_customer_id = customer_id
    _store_payment_method_snapshot(db, player, player.stripe_customer_id)
    return subscription


def _find_player_for_event(db, event_object):
    from .database import Player

    metadata = event_object.get("metadata", {}) if isinstance(event_object, dict) else {}
    username = metadata.get("username") or event_object.get("client_reference_id")
    customer_id = event_object.get("customer")

    if username:
        player = db.query(Player).filter(Player.username == username).first()
        if player:
            return player
    if customer_id:
        return db.query(Player).filter(Player.stripe_customer_id == customer_id).first()
    return None


def _record_billing_event(db, player_id: int | None, event, event_status: str = "processed"):
    from .database import BillingEvent

    payload = event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else event
    db.add(BillingEvent(
        player_id=player_id,
        provider=STRIPE_PROVIDER,
        event_type=event.get("type", "unknown"),
        provider_event_id=event.get("id"),
        event_status=event_status,
        payload=payload,
    ))


def process_stripe_event(db, event):
    from .database import BillingEvent

    event_id = event.get("id")
    if db.query(BillingEvent).filter(BillingEvent.provider_event_id == event_id).first():
        return

    event_type = event.get("type", "")
    event_object = event.get("data", {}).get("object", {})
    player = _find_player_for_event(db, event_object)
    plan_code_hint = event_object.get("metadata", {}).get("plan_code") if isinstance(event_object, dict) else None

    if event_type == "checkout.session.completed" and player:
        player.stripe_customer_id = event_object.get("customer") or player.stripe_customer_id
        player.billing_provider = STRIPE_PROVIDER
        sync_subscription_from_stripe(
            db,
            player,
            subscription_id=event_object.get("subscription"),
            customer_id=event_object.get("customer"),
            plan_code_hint=plan_code_hint,
        )
    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"} and player:
        subscription = _upsert_subscription_from_object(db, player, event_object, plan_code_hint=plan_code_hint)
        _store_payment_method_snapshot(db, player, subscription.provider_customer_id)
    elif event_type in {"invoice.paid", "invoice.payment_failed"} and player:
        sync_subscription_from_stripe(
            db,
            player,
            subscription_id=event_object.get("subscription"),
            customer_id=event_object.get("customer"),
            plan_code_hint=plan_code_hint,
        )

    _record_billing_event(db, player.id if player else None, event)
    db.commit()


def handle_stripe_webhook(db, payload: bytes, signature_header: str | None):
    stripe = _get_stripe()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        raise HTTPException(status_code=503, detail="Stripe webhook signing secret is not configured.")
    if not signature_header:
        raise HTTPException(status_code=400, detail="Missing Stripe signature header.")

    try:
        event = stripe.Webhook.construct_event(payload, signature_header, webhook_secret)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.") from exc

    process_stripe_event(db, event)
    return event
