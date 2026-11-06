from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal
from pydantic import computed_field, Field, PostgresDsn
from functools import lru_cache
from pydantic_core import MultiHostUrl
import os


API_PREFIX = "/api"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        env_ignore_empty=True,
        case_sensitive=True,
    )
    CORS_ORIGINS: list[str] = Field(default_factory=list)
    MISTRAL_API_KEY: str
    MISTRAL_MODEL: str = "ministral-14b-latest"
    MISTRAL_FALLBACK_MODEL: str = "ministral-8b-latest"
    MISTRAL_EMBED_MODEL: str = "mistral-embed"
    EMBEDDING_DIMENSION: int = 1024
    COHERE_API_KEY: str
    REDIS_URL: str
    DOMAIN: str = "localhost"
    ENVIRONMENT: Literal["local", "staging", "production"] = "local"
    JWT_SECRET_KEY: str
    JIRA_DOMAIN: str
    JIRA_EMAIL: str
    JIRA_API_TOKEN: str
    JIRA_PROJECT_KEY: str
    JIRA_ISSUE_TYPE: str
    BUG_REPORT_RATE_LIMIT_SECONDS: int
    # Agent loop: tool rounds per turn before the model must answer, and calls per round.
    AGENT_MAX_TOOL_ROUNDS: int = 4
    AGENT_MAX_CALLS_PER_ROUND: int = 4
    # Web search. "none", or an empty key, turns the web_search tool off.
    SEARCH_PROVIDER: Literal["exa", "none"] = "exa"
    EXA_API_KEY: str = ""
    WEB_SEARCH_RESULTS: int = 5
    WEB_SEARCH_DAILY_LIMIT_PER_USER: int = 30
    ALLOW_PUBLIC_REGISTRATION: bool = True
    # Sign-ups are counted per window. The per-IP cap only applies when the real
    # client IP is known (TRUST_PROXY_HEADERS); the global cap always applies.
    REGISTRATION_RATE_LIMIT_SECONDS: int = 3600
    REGISTRATION_MAX_PER_IP: int = 10
    REGISTRATION_MAX_GLOBAL: int = 100
    MAX_REFRESH_SESSIONS_PER_USER: int = 5
    SESSION_ABSOLUTE_LIFETIME_DAYS: int = 30
    REFRESH_REUSE_GRACE_SECONDS: int = 30
    LOGIN_RATE_LIMIT_WINDOW_SECONDS: int = 900
    LOGIN_MAX_FAILURES_PER_ACCOUNT: int = 10
    LOGIN_MAX_FAILURES_PER_IP: int = 50
    # Enable only when a trusted proxy sets X-Real-IP and the app can't be reached directly.
    TRUST_PROXY_HEADERS: bool = False
    AUDIT_RETENTION_DAYS: int = 90
    SMTP_SERVER: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    PINECONE_API: str
    PINECONE_INDEX_NAME: str = "documents-mistral-embed"
    VECTOR_STORE_PROVIDER: Literal["pinecone"]
    ADMIN_PASSWORD: str
    ADMIN_EMAIL: str
    LOG_QUEUE_SIZE: int = Field(default=10000, ge=1, le=100000)

    @computed_field
    @property
    def server_host(self) -> str:
        # Use HTTPS for anything other than local development
        if self.ENVIRONMENT == "local":
            return f"http://{self.DOMAIN}"
        return f"https://{self.DOMAIN}"

    POSTGRESQL_USERNAME: str
    POSTGRESQL_PASSWORD: str
    POSTGRESQL_SERVER: str
    POSTGRESQL_PORT: int = 5432
    POSTGRESQL_DATABASE: str

    # Set for MISTRAL_MODEL; change these together. The soft input limit
    # (input * SUMMARIZE_THRESHOLD) plus the output limit must fit in the context window.
    MODEL_INPUT_TOKEN_LIMIT: int = 256_000
    MODEL_OUTPUT_TOKEN_LIMIT: int = 8_192
    INPUT_TOKEN_BUFFER: int = 4096
    MAX_REDIS_MESSAGES: int = 100
    MIN_RECENT_TURNS: int = 4
    SUMMARIZE_THRESHOLD: float = 0.8

    RAG_INITIAL_TOP_K: int = 20
    RAG_TOP_K: int = 5
    RAG_RELEVANCE_THRESHOLD: float = 0.4
    MAX_UPLOAD_BYTES: int = 10_485_760
    PARENT_CHUNK_SIZE_TOKENS: int = 2000
    PARENT_CHUNK_OVERLAP_TOKENS: int = 100

    @computed_field  # type: ignore[misc]
    @property
    def SQLALCHEMY_DATABASE_URI(self) -> PostgresDsn:
        uri_string = (
            f"postgresql+asyncpg://{self.POSTGRESQL_USERNAME}:"
            f"{self.POSTGRESQL_PASSWORD}@{self.POSTGRESQL_SERVER}:"
            f"{self.POSTGRESQL_PORT}/{self.POSTGRESQL_DATABASE}"
        )
        return MultiHostUrl(uri_string)


@lru_cache()
def getSettings():
    """Return cached settings loaded from environment variables."""
    return Settings()
