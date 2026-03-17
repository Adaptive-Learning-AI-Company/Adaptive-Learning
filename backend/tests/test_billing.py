from backend.billing import PLAN_BYOK_MONTHLY, PLAN_HOSTED_MONTHLY, estimate_model_cost_cents, get_plan_definition


def test_default_plan_catalog_contains_both_subscription_types():
    byok = get_plan_definition(PLAN_BYOK_MONTHLY)
    hosted = get_plan_definition(PLAN_HOSTED_MONTHLY)

    assert byok is not None
    assert hosted is not None
    assert byok.requires_personal_key is True
    assert hosted.includes_hosted_usage is True


def test_estimate_model_cost_cents_uses_default_gpt5_mini_prices(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_FAST_MODEL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_INPUT_PRICE_PER_1M", raising=False)
    monkeypatch.delenv("OPENAI_MODEL_OUTPUT_PRICE_PER_1M", raising=False)

    estimated = estimate_model_cost_cents("gpt-5-mini", 1_000_000, 500_000)

    assert estimated == 125
