import asyncio
import hashlib
from functools import lru_cache

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from bcrypt import checkpw
from starlette.concurrency import run_in_threadpool

from core.config import getSettings


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    settings = getSettings()
    return PasswordHasher(
        time_cost=settings.ARGON2_TIME_COST,
        memory_cost=settings.ARGON2_MEMORY_KIB,
        parallelism=settings.ARGON2_PARALLELISM,
        type=Type.ID,
    )


def get_hash(text: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher().hash(text)


def verify_hash(plain_text: str, hashed_text: str) -> bool:
    """Verify a password against a bcrypt (old) or Argon2 hash."""
    try:
        if hashed_text.startswith("$2"):
            return checkpw(plain_text.encode("utf-8"), hashed_text.encode("utf-8"))
        if hashed_text.startswith("$argon2"):
            return _hasher().verify(hashed_text, plain_text)
    except (ValueError, VerificationError, InvalidHashError):
        return False
    return False


def needs_rehash(hashed_text: str) -> bool:
    """True for bcrypt hashes and for Argon2 hashes made with weaker parameters."""
    if hashed_text.startswith("$argon2"):
        try:
            return _hasher().check_needs_rehash(hashed_text)
        except InvalidHashError:
            return True
    return True


# Argon2 uses memory on purpose, so the number of hashes running at once is capped.
# Created on first use so it binds to the running event loop.
_semaphore: asyncio.Semaphore | None = None


def _hash_slots() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(getSettings().PASSWORD_HASH_CONCURRENCY)
    return _semaphore


async def hash_password(text: str) -> str:
    async with _hash_slots():
        return await run_in_threadpool(get_hash, text)


async def verify_password(plain_text: str, hashed_text: str) -> bool:
    async with _hash_slots():
        return await run_in_threadpool(verify_hash, plain_text, hashed_text)


def hash_token(token: str) -> str:
    """Hash a JWT refresh token for storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
