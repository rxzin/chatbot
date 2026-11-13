"""Settings: the switches that keep tests and benchmarks away from real services."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from core.config import Settings

TEST_ENV = Path(__file__).resolve().parents[1] / "test.env"

# Every setting without a default, so Settings can be built with no env file at all.
REQUIRED = {
    "MISTRAL_API_KEY": "k",
    "COHERE_API_KEY": "k",
    "PINECONE_API": "k",
    "REDIS_URL": "redis://127.0.0.1:56379/0",
    "JWT_SECRET_KEY": "s",
    "JIRA_DOMAIN": "jira.example.com",
    "JIRA_EMAIL": "bot@example.com",
    "JIRA_API_TOKEN": "k",
    "JIRA_PROJECT_KEY": "TEST",
    "JIRA_ISSUE_TYPE": "Bug",
    "BUG_REPORT_RATE_LIMIT_SECONDS": 3600,
    "VECTOR_STORE_PROVIDER": "pinecone",
    "ADMIN_PASSWORD": "AdminPassw0rd!",
    "ADMIN_EMAIL": "admin@example.com",
    "POSTGRESQL_USERNAME": "u",
    "POSTGRESQL_PASSWORD": "p",
    "POSTGRESQL_SERVER": "127.0.0.1",
    "POSTGRESQL_DATABASE": "d",
}

# A variable exported in the shell beats any env file, so clear the ones asserted on.
ASSERTED = [
    "MISTRAL_API_KEY",
    "LANGFUSE_PUBLIC_KEY",
    "EXA_API_KEY",
    "ENVIRONMENT",
    "EXTERNAL_SERVICES",
    "DB_SCHEME",
    "DB_QUERY",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
]


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in ASSERTED:
        monkeypatch.delenv(name, raising=False)


def test_settings_ignore_dev_env_file(monkeypatch):
    monkeypatch.setenv("APP_ENV_FILE", str(TEST_ENV))

    settings = Settings()

    assert settings.MISTRAL_API_KEY == "test-not-a-real-key"
    assert settings.LANGFUSE_PUBLIC_KEY == ""
    assert settings.EXA_API_KEY == ""
    assert settings.EXTERNAL_SERVICES == "fake"


def test_fake_services_rejected_in_production():
    with pytest.raises(ValidationError, match="EXTERNAL_SERVICES"):
        Settings(
            _env_file=None,
            **REQUIRED,
            ENVIRONMENT="production",
            EXTERNAL_SERVICES="fake",
        )


def test_fake_services_allowed_outside_production():
    settings = Settings(_env_file=None, **REQUIRED, EXTERNAL_SERVICES="fake")

    assert settings.EXTERNAL_SERVICES == "fake"


def test_database_uri_uses_scheme_and_query():
    settings = Settings(
        _env_file=None,
        **REQUIRED,
        DB_SCHEME="cockroachdb+asyncpg",
        DB_QUERY="ssl=disable",
    )

    uri = str(settings.SQLALCHEMY_DATABASE_URI)
    assert uri.startswith("cockroachdb+asyncpg://")
    assert uri.endswith("?ssl=disable")


def test_defaults_unchanged():
    settings = Settings(_env_file=None, **REQUIRED)

    assert settings.EXTERNAL_SERVICES == "live"
    assert settings.DB_POOL_SIZE == 5
    assert settings.DB_MAX_OVERFLOW == 10
    assert str(settings.SQLALCHEMY_DATABASE_URI) == "postgresql+asyncpg://u:p@127.0.0.1:5432/d"
