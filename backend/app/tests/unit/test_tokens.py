"""JWT access and refresh tokens."""

from uuid import uuid4

import jwt
import pytest
from jwt.exceptions import InvalidTokenError

from auth import handler

EMAIL = "someone@example.com"


def test_access_token_payload():
    session_id = uuid4()

    payload = handler.decode(handler.create_access_token(EMAIL, session_id))

    assert payload["type"] == "access"
    assert payload["sub"] == EMAIL
    assert payload["sid"] == str(session_id)
    assert payload["exp"] - payload["iat"] == 15 * 60


def test_refresh_token_payload():
    payload = handler.decode(handler.create_refresh_token(EMAIL, uuid4()))

    assert payload["type"] == "refresh"
    assert payload["exp"] - payload["iat"] == 7 * 24 * 60 * 60


def test_tokens_for_the_same_inputs_differ():
    session_id = uuid4()

    first = handler.create_access_token(EMAIL, session_id)
    second = handler.create_access_token(EMAIL, session_id)

    assert first != second
    assert handler.decode(first)["jti"] != handler.decode(second)["jti"]


def test_tampered_token_is_rejected():
    token = handler.create_access_token(EMAIL, uuid4())
    header, payload, signature = token.split(".")
    flipped = ("A" if signature[0] != "A" else "B") + signature[1:]

    with pytest.raises(InvalidTokenError):
        handler.decode(f"{header}.{payload}.{flipped}")


def test_token_signed_with_another_key_is_rejected():
    forged = jwt.encode({"sub": EMAIL, "type": "access"}, "x" * 48, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        handler.decode(forged)
