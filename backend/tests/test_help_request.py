import asyncio
import sys
import types

import pytest
from fastapi import HTTPException

if "jose" not in sys.modules:
    jose_stub = types.ModuleType("jose")

    class _JWTError(Exception):
        pass

    class _JWTStub:
        @staticmethod
        def encode(*args, **kwargs):
            return "stub-token"

        @staticmethod
        def decode(*args, **kwargs):
            return {}

    jose_stub.jwt = _JWTStub
    jose_stub.JWTError = _JWTError
    sys.modules["jose"] = jose_stub

from backend import main
from backend.models import HelpRequest


def test_help_request_model_keeps_optional_user_id():
    payload = HelpRequest(
        name="Ada Lovelace",
        email="ada@example.com",
        user_id="adal",
        message="I need help logging in.",
    )

    assert payload.name == "Ada Lovelace"
    assert payload.email == "ada@example.com"
    assert payload.user_id == "adal"
    assert payload.message == "I need help logging in."


def test_request_help_rejects_invalid_email():
    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            main.request_help(
                HelpRequest(
                    name="Ada Lovelace",
                    email="invalid-email",
                    message="I need help logging in.",
                )
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "Enter a valid email address."


def test_request_help_sends_email(monkeypatch):
    captured = {}

    def fake_send_help_request_email(name, email_address, user_id, message):
        captured["name"] = name
        captured["email_address"] = email_address
        captured["user_id"] = user_id
        captured["message"] = message

    monkeypatch.setattr(main, "send_help_request_email", fake_send_help_request_email)

    response = asyncio.run(
        main.request_help(
            HelpRequest(
                name="Ada Lovelace",
                email="ada@example.com",
                user_id="adal",
                message="I need help logging in.",
            )
        )
    )

    assert response["message"] == "Help request sent."
    assert captured == {
        "name": "Ada Lovelace",
        "email_address": "ada@example.com",
        "user_id": "adal",
        "message": "I need help logging in.",
    }
