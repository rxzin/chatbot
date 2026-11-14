import logging
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from auth import handler
from auth.security import (
    get_hash,
    hash_password,
    hash_token,
    needs_rehash,
    verify_password,
)
from core.config import API_PREFIX, getSettings
from core.database import get_db
from core.errors import BadRequest, ConflictError, UnauthorizedError, ForbiddenError
from core.logging import log_event
from schemas.models import Session, User
from services.user import get_user_by_email
from fastapi.security import SecurityScopes
from fastapi import Security

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{API_PREFIX}/auth/login")

# Checked when an email doesn't exist, so a login takes the same time either way and
# response timing doesn't reveal which accounts exist.
_DUMMY_PASSWORD_HASH = get_hash("timing-equalizer")


async def authenticate_user(email: str, password: str, db: AsyncSession) -> User | None:
    user = await get_user_by_email(db, email)
    if not user:
        await verify_password(password, _DUMMY_PASSWORD_HASH)
        return None
    if not await verify_password(password, user.password):
        return None
    if not user.is_active:
        return None
    if needs_rehash(user.password):
        # Committed with the session the login creates next.
        user.password = await hash_password(password)
    return user


async def get_session_by_refresh_token(
    db: AsyncSession, refresh_token: str
) -> Session | None:
    token_hash = hash_token(refresh_token)
    result = await db.execute(
        select(Session).where(Session.refresh_token == token_hash)
    )
    return result.scalar_one_or_none()


def _session_id_from(payload: dict) -> UUID:
    try:
        return UUID(payload["sid"])
    except (KeyError, TypeError, ValueError) as e:
        raise UnauthorizedError("Invalid token payload") from e


def _is_session_expired(session: Session, now: datetime) -> bool:
    return now >= session.expires_at or now >= session.absolute_expires_at


async def create_session(
    db: AsyncSession,
    user: User,
    *,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> tuple[str, str]:
    """Start a new login session and return its access and refresh tokens."""
    now = datetime.now(timezone.utc)
    absolute_expires_at = now + timedelta(
        days=getSettings().SESSION_ABSOLUTE_LIFETIME_DAYS
    )
    session = Session(
        user_id=user.id,
        # The token must contain the database-generated ID, so its hash can't exist
        # until after the insert. This random value keeps the column's NOT NULL and
        # UNIQUE rules satisfied, and is replaced before the transaction commits.
        refresh_token=secrets.token_hex(32),
        expires_at=min(now + handler.REFRESH_TOKEN_EXPIRE_DAYS, absolute_expires_at),
        absolute_expires_at=absolute_expires_at,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(session)
    await db.flush()

    refresh_token = handler.create_refresh_token(user.email, session.id)
    session.refresh_token = hash_token(refresh_token)
    await db.commit()
    return handler.create_access_token(user.email, session.id), refresh_token


async def prune_user_sessions(
    db: AsyncSession, user_id: UUID, max_sessions: int
) -> None:
    """Remove oldest refresh sessions so a new login stays within the cap."""
    if max_sessions <= 0:
        return

    # Concurrent logins by one user each counted the same sessions and all inserted,
    # passing the cap (F15). Locking the user's row queues them; the lock is held
    # until create_session commits, so the next login counts the new session.
    await db.execute(select(User.id).where(User.id == user_id).with_for_update())
    result = await db.execute(
        select(Session)
        .where(Session.user_id == user_id)
        .order_by(Session.created_at.asc())
    )
    sessions = list(result.scalars().all())
    excess = len(sessions) - max_sessions + 1
    if excess <= 0:
        return

    for session in sessions[:excess]:
        await db.delete(session)
    await db.flush()


async def get_current_user(
    request: Request,
    security_scopes: SecurityScopes,
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
):
    credential_exceptions = UnauthorizedError("Could not validate credentials")

    try:
        payload = handler.decode(token)
    except InvalidTokenError as e:
        raise credential_exceptions from e

    if payload.get("type") != "access":
        raise credential_exceptions

    email = payload.get("sub")
    if email is None:
        raise credential_exceptions

    # A valid signature isn't enough: logout deletes the session, which ends this
    # token immediately instead of when it expires.
    session = await db.get(Session, _session_id_from(payload))
    if session is None or _is_session_expired(session, datetime.now(timezone.utc)):
        raise credential_exceptions

    user = await get_user_by_email(db, email=email)
    if user is None or user.id != session.user_id:
        raise credential_exceptions

    # Set before the permission check, so denied requests are attributed in the audit log.
    request.state.user_id = user.id
    request.state.session_id = session.id

    live_permissions = user.permissions
    for scope in security_scopes.scopes:
        if scope not in live_permissions:
            raise ForbiddenError("Insufficient permissions")

    return user


async def get_current_active_user(current_user: User = Security(get_current_user)):
    if not current_user.is_active:
        raise BadRequest("Inactive user")
    return current_user


async def rotate_refresh_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    """
    Exchange a refresh token for new tokens, keeping the same session.

    The current token rotates. The previous one gets a 409 for a short time, because
    two tabs refreshing together is normal and that browser already has the new cookie.
    Any other old token means it was copied, so the session is revoked.
    """
    try:
        payload = handler.decode(refresh_token)
    except InvalidTokenError as e:
        raise UnauthorizedError("Invalid or expired refresh token") from e

    if payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid token type")

    session_id = _session_id_from(payload)
    result = await db.execute(
        select(Session).where(Session.id == session_id).with_for_update()
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise UnauthorizedError("Refresh token has been revoked")

    now = datetime.now(timezone.utc)
    if _is_session_expired(session, now):
        await db.delete(session)
        await db.commit()
        raise UnauthorizedError("Refresh token has expired")

    token_hash = hash_token(refresh_token)
    if token_hash != session.refresh_token:
        grace = timedelta(seconds=getSettings().REFRESH_REUSE_GRACE_SECONDS)
        if (
            token_hash == session.previous_refresh_token
            and session.rotated_at is not None
            and now - session.rotated_at <= grace
        ):
            await db.rollback()
            raise ConflictError("Refresh token was already rotated. Retry the request.")

        await db.delete(session)
        await db.commit()
        log_event(
            event="auth.refresh.reuse.detected",
            message="Stale refresh token used; session revoked",
            level=logging.WARNING,
            session_id=str(session_id),
        )
        raise UnauthorizedError("Refresh token has been revoked")

    user = await get_user_by_email(db, email=payload.get("sub"))
    if user is None or user.id != session.user_id:
        raise UnauthorizedError("Refresh token does not belong to current user")
    if not user.is_active:
        raise UnauthorizedError("Account is inactive")

    new_refresh_token = handler.create_refresh_token(user.email, session.id)
    try:
        session.previous_refresh_token = token_hash
        session.refresh_token = hash_token(new_refresh_token)
        session.rotated_at = now
        session.expires_at = min(
            now + handler.REFRESH_TOKEN_EXPIRE_DAYS, session.absolute_expires_at
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return handler.create_access_token(user.email, session.id), new_refresh_token


async def logout_service(db: AsyncSession, refresh_token: str, user: User) -> None:
    session = await get_session_by_refresh_token(db, refresh_token)
    if session is None:
        raise UnauthorizedError("Refresh token has been revoked")
    if session.user_id != user.id:
        raise UnauthorizedError("Refresh token does not belong to current user")
    await db.delete(session)
    await db.commit()


async def revoke_refresh_cookie_session(
    db: AsyncSession, refresh_token: str | None
) -> None:
    """Revoke a refresh session from the HttpOnly cookie when present."""
    if not refresh_token:
        return

    session = await get_session_by_refresh_token(db, refresh_token)
    if session is None:
        return

    await db.delete(session)
    await db.commit()
