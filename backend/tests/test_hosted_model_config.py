from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.billing import (
    build_hosted_model_config,
    get_hosted_priority_selection,
    get_hosted_model_selection,
    get_hosted_models,
    set_hosted_models,
)
from backend.database import Base


def _make_session():
    engine = create_engine("sqlite:///:memory:")
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    return TestingSessionLocal()


def test_default_hosted_model_config_contains_openai_and_gemini_catalog(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    db = _make_session()
    try:
        payload = build_hosted_model_config(db)
        model_ids = {entry["model_id"] for entry in payload["catalog"]}
        providers = {entry["provider"] for entry in payload["catalog"]}

        assert payload["teacher_model"] == "gpt-5-mini"
        assert payload["verifier_model"] == "gpt-5-mini"
        assert payload["fast_model"] == "gpt-5-mini"
        assert payload["teacher_priority_enabled"] is True
        assert payload["verifier_priority_enabled"] is True
        assert payload["fast_priority_enabled"] is True
        assert "openai" in providers
        assert "google" in providers
        assert "gpt-5-mini" in model_ids
        assert "gemini-2.5-flash" in model_ids
        catalog_by_id = {entry["model_id"]: entry for entry in payload["catalog"]}
        assert catalog_by_id["gpt-5-mini"]["supports_priority"] is True
        assert catalog_by_id["gemini-2.5-flash"]["supports_priority"] is False
    finally:
        db.close()


def test_setting_hosted_models_persists_runtime_selection(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

    db = _make_session()
    try:
        payload = set_hosted_models(
            db,
            "gpt-4.1",
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            teacher_priority_enabled=True,
            verifier_priority_enabled=False,
            fast_priority_enabled=False,
            updated_by_player_id=None,
        )
        db.commit()

        stored_teacher, stored_verifier, stored_fast_model = get_hosted_model_selection(db)
        stored_teacher_priority, stored_verifier_priority, stored_fast_priority = get_hosted_priority_selection(db)
        stored_main, stored_fast = get_hosted_models(db)

        assert payload["teacher_model"] == "gpt-4.1"
        assert payload["verifier_model"] == "gemini-2.5-pro"
        assert payload["fast_model"] == "gemini-2.5-flash"
        assert payload["teacher_priority_enabled"] is True
        assert payload["verifier_priority_enabled"] is False
        assert payload["fast_priority_enabled"] is False
        assert stored_teacher == "gpt-4.1"
        assert stored_verifier == "gemini-2.5-pro"
        assert stored_fast_model == "gemini-2.5-flash"
        assert stored_teacher_priority is True
        assert stored_verifier_priority is False
        assert stored_fast_priority is False
        assert stored_main == "gpt-4.1"
        assert stored_fast == "gemini-2.5-flash"
    finally:
        db.close()


def test_setting_gemini_model_requires_google_api_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    db = _make_session()
    try:
        try:
            set_hosted_models(db, "gpt-5-mini", "gemini-2.5-pro", "gemini-2.5-flash", updated_by_player_id=None)
            assert False, "Expected Gemini selection without GOOGLE_API_KEY to fail"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "GOOGLE_API_KEY" in str(exc.detail)
    finally:
        db.close()


def test_setting_priority_requires_supported_model(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-key")

    db = _make_session()
    try:
        try:
            set_hosted_models(
                db,
                "gpt-5-mini",
                "gemini-2.5-pro",
                "gemini-2.5-flash",
                teacher_priority_enabled=True,
                verifier_priority_enabled=True,
                fast_priority_enabled=False,
                updated_by_player_id=None,
            )
            assert False, "Expected unsupported Gemini priority selection to fail"
        except HTTPException as exc:
            assert exc.status_code == 400
            assert "Priority processing is not supported" in str(exc.detail)
    finally:
        db.close()
