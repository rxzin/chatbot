"""Password hashing and refresh-token hashing."""

import threading

import bcrypt

from auth import security
from auth.security import (
    get_hash,
    hash_password,
    hash_token,
    needs_rehash,
    verify_hash,
    verify_password,
)


def test_hash_round_trip():
    hashed = get_hash("Passw0rd!x")

    assert hashed != "Passw0rd!x"
    assert verify_hash("Passw0rd!x", hashed) is True
    assert verify_hash("wrong-password", hashed) is False


def test_new_hashes_are_argon2id():
    assert get_hash("x").startswith("$argon2id$")


def test_a_bcrypt_hash_still_verifies_and_needs_rehash():
    old = bcrypt.hashpw(b"Passw0rd!x", bcrypt.gensalt(rounds=4)).decode()

    assert verify_hash("Passw0rd!x", old) is True
    assert verify_hash("wrong", old) is False
    assert needs_rehash(old) is True
    assert needs_rehash(get_hash("Passw0rd!x")) is False


def test_weaker_argon2_parameters_need_rehash():
    from argon2 import PasswordHasher, Type

    weak = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1, type=Type.ID)

    assert needs_rehash(weak.hash("x")) is True


async def test_async_hashing_runs_off_the_event_loop_thread(monkeypatch):
    seen = []
    real = security.get_hash

    def recording(text):
        seen.append(threading.get_ident())
        return real(text)

    monkeypatch.setattr(security, "get_hash", recording)

    hashed = await hash_password("Passw0rd!x")

    assert seen and seen[0] != threading.get_ident()
    assert await verify_password("Passw0rd!x", hashed) is True
    assert await verify_password("nope", hashed) is False


def test_same_password_hashes_differently_each_time():
    assert get_hash("Passw0rd!x") != get_hash("Passw0rd!x")


def test_verify_rejects_a_value_that_is_not_a_hash():
    assert verify_hash("x", "not-a-hash") is False
    assert verify_hash("x", "garbage") is False
    assert verify_hash("x", "$argon2id$broken") is False
    assert verify_hash("x", "$2b$12$short") is False


def test_hash_token_is_stable_sha256_hex():
    digest = hash_token("some.jwt.value")

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert digest == hash_token("some.jwt.value")
    assert digest != hash_token("another.jwt.value")
