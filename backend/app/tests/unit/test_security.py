"""Password hashing and refresh-token hashing."""

from auth.security import get_hash, hash_token, verify_hash


def test_hash_round_trip():
    hashed = get_hash("Passw0rd!x")

    assert hashed != "Passw0rd!x"
    assert verify_hash("Passw0rd!x", hashed) is True
    assert verify_hash("wrong-password", hashed) is False


def test_same_password_hashes_differently_each_time():
    assert get_hash("Passw0rd!x") != get_hash("Passw0rd!x")


def test_verify_rejects_a_value_that_is_not_a_hash():
    assert verify_hash("x", "not-a-hash") is False


def test_hash_token_is_stable_sha256_hex():
    digest = hash_token("some.jwt.value")

    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")
    assert digest == hash_token("some.jwt.value")
    assert digest != hash_token("another.jwt.value")
