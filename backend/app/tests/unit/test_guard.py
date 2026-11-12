"""The guard that stops the suite from truncating anything but the test database."""

from pathlib import Path
from types import SimpleNamespace

import pytest
from dotenv import dotenv_values

from support.guard import assert_safe_test_target

TEST_ENV = Path(__file__).resolve().parents[1] / "test.env"


def target(**overrides) -> SimpleNamespace:
    """The settings the guard reads, taken from tests/test.env unless overridden."""
    values = dotenv_values(TEST_ENV)
    fields = {
        "POSTGRESQL_SERVER": values["POSTGRESQL_SERVER"],
        "POSTGRESQL_PORT": int(values["POSTGRESQL_PORT"]),
        "POSTGRESQL_DATABASE": values["POSTGRESQL_DATABASE"],
        "REDIS_URL": values["REDIS_URL"],
        "EXTERNAL_SERVICES": values["EXTERNAL_SERVICES"],
    }
    return SimpleNamespace(**{**fields, **overrides})


def dev_env(tmp_path: Path, **values) -> Path:
    path = tmp_path / ".env"
    path.write_text("".join(f"{k}={v}\n" for k, v in values.items()), encoding="utf-8")
    return path


def test_guard_rejects_non_test_database():
    with pytest.raises(RuntimeError):
        assert_safe_test_target(target(POSTGRESQL_DATABASE="chatbot"), None)


def test_guard_rejects_remote_host():
    with pytest.raises(RuntimeError):
        assert_safe_test_target(target(POSTGRESQL_SERVER="db.example.com"), None)


def test_guard_rejects_live_services():
    with pytest.raises(RuntimeError):
        assert_safe_test_target(target(EXTERNAL_SERVICES="live"), None)


def test_guard_rejects_default_redis_port():
    with pytest.raises(RuntimeError):
        assert_safe_test_target(target(REDIS_URL="redis://localhost:6379/0"), None)


def test_guard_rejects_dev_database(tmp_path):
    """A name ending in _test is not enough if it is the database the dev file names."""
    dev_file = dev_env(
        tmp_path,
        POSTGRESQL_SERVER="localhost",
        POSTGRESQL_PORT=55432,
        POSTGRESQL_DATABASE="x_test",
    )
    settings = target(POSTGRESQL_SERVER="127.0.0.1", POSTGRESQL_DATABASE="x_test")

    with pytest.raises(RuntimeError):
        assert_safe_test_target(settings, dev_file)


def test_guard_rejects_dev_database_on_default_port(tmp_path):
    """A dev file with no port means Postgres's default, 5432."""
    dev_file = dev_env(
        tmp_path, POSTGRESQL_SERVER="127.0.0.1", POSTGRESQL_DATABASE="x_test"
    )
    settings = target(POSTGRESQL_PORT=5432, POSTGRESQL_DATABASE="x_test")

    with pytest.raises(RuntimeError):
        assert_safe_test_target(settings, dev_file)


def test_guard_never_prints_dev_values(tmp_path):
    dev_file = dev_env(
        tmp_path,
        POSTGRESQL_SERVER="localhost",
        POSTGRESQL_PORT=55432,
        POSTGRESQL_DATABASE="x_test",
        POSTGRESQL_PASSWORD="dev-secret-value",
    )
    settings = target(POSTGRESQL_DATABASE="x_test")

    with pytest.raises(RuntimeError) as raised:
        assert_safe_test_target(settings, dev_file)

    assert "dev-secret-value" not in str(raised.value)


def test_guard_accepts_test_env(tmp_path):
    different_dev = dev_env(
        tmp_path,
        POSTGRESQL_SERVER="localhost",
        POSTGRESQL_PORT=5432,
        POSTGRESQL_DATABASE="chatbot",
    )

    assert_safe_test_target(target(), None)
    assert_safe_test_target(target(), tmp_path / "missing.env")
    assert_safe_test_target(target(), different_dev)
    assert_safe_test_target(target(POSTGRESQL_SERVER="localhost"), different_dev)
