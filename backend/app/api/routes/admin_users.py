from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Security, status
from sqlalchemy import delete, func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth.service import get_current_active_user
from core.database import get_db
from core.errors import BadRequest, NotFoundError
from schemas.admin import AdminSessionResponse, AdminUserPage, AdminUserResponse
from schemas.models import Roles, Session, User
from schemas.schema import AdminActionResponse

admin_users_router = APIRouter(prefix="/admin")

# Holding this permission marks an account as an administrator.
_ADMIN_PERMISSION = "users:ban"


def _active_session_conditions(now: datetime):
    return (Session.expires_at > now, Session.absolute_expires_at > now)


async def _get_user_or_404(db: AsyncSession, user_id: UUID) -> User:
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles).selectinload(Roles.permissions))
        .where(User.id == user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    return user


@admin_users_router.get(
    "/users",
    response_model=AdminUserPage,
    status_code=status.HTTP_200_OK,
)
async def list_users(
    search: Optional[str] = Query(default=None, max_length=255),
    cursor: Optional[UUID] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["users:ban"]),
):
    """List accounts with their active session counts, newest first."""
    session_counts = (
        select(Session.user_id, func.count().label("active_sessions"))
        .where(*_active_session_conditions(datetime.now(timezone.utc)))
        .group_by(Session.user_id)
        .subquery()
    )
    stmt = (
        select(User, func.coalesce(session_counts.c.active_sessions, 0))
        .options(selectinload(User.roles).selectinload(Roles.permissions))
        .outerjoin(session_counts, User.id == session_counts.c.user_id)
        .order_by(User.created_at.desc(), User.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        cursor_created_at = await db.scalar(
            select(User.created_at).where(User.id == cursor)
        )
        if cursor_created_at is None:
            raise BadRequest("Unknown cursor")
        stmt = stmt.where(tuple_(User.created_at, User.id) < (cursor_created_at, cursor))
    if search:
        stmt = stmt.where(User.email.icontains(search, autoescape=True))

    rows = (await db.execute(stmt)).all()
    page = rows[:limit]
    return AdminUserPage(
        items=[
            AdminUserResponse(
                id=user.id,
                email=user.email,
                is_active=user.is_active,
                is_admin=_ADMIN_PERMISSION in user.permissions,
                is_self=user.id == current_user.id,
                active_sessions=active_sessions,
                created_at=user.created_at,
            )
            for user, active_sessions in page
        ],
        next_cursor=page[-1][0].id if len(rows) > limit else None,
    )


@admin_users_router.get(
    "/users/{user_id}/sessions",
    response_model=list[AdminSessionResponse],
    status_code=status.HTTP_200_OK,
)
async def list_user_sessions(
    request: Request,
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["sessions:manage"]),
):
    await _get_user_or_404(db, user_id)
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == user_id,
            *_active_session_conditions(datetime.now(timezone.utc)),
        )
        .order_by(Session.created_at.desc(), Session.id.desc())
    )
    current_session_id = getattr(request.state, "session_id", None)
    return [
        AdminSessionResponse(
            id=session.id,
            ip_address=session.ip_address,
            user_agent=session.user_agent,
            is_current=session.id == current_session_id,
            created_at=session.created_at,
            last_rotated_at=session.rotated_at,
            expires_at=min(session.expires_at, session.absolute_expires_at),
        )
        for session in result.scalars().all()
    ]


@admin_users_router.delete(
    "/sessions/{session_id}",
    response_model=AdminActionResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_session(
    request: Request,
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["sessions:manage"]),
):
    """End one session. Its access and refresh tokens stop working on their next use."""
    if session_id == getattr(request.state, "session_id", None):
        raise BadRequest("This is your current session. Use log out instead.")

    session = await db.get(Session, session_id)
    if session is None:
        raise NotFoundError("Session not found")
    await db.delete(session)
    await db.commit()
    return AdminActionResponse(success=True, message="Session revoked.")


async def _delete_user_sessions(db: AsyncSession, user_id: UUID) -> int:
    result = await db.execute(delete(Session).where(Session.user_id == user_id))
    return result.rowcount


@admin_users_router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=AdminActionResponse,
    status_code=status.HTTP_200_OK,
)
async def revoke_user_sessions(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["sessions:manage"]),
):
    """Sign a user out everywhere without banning them."""
    if user_id == current_user.id:
        raise BadRequest("You can't revoke all of your own sessions here.")
    await _get_user_or_404(db, user_id)
    count = await _delete_user_sessions(db, user_id)
    await db.commit()
    return AdminActionResponse(success=True, message=f"Revoked {count} session(s).")


@admin_users_router.post(
    "/users/{user_id}/ban",
    response_model=AdminActionResponse,
    status_code=status.HTTP_200_OK,
)
async def ban_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["users:ban"]),
):
    """Block logins and end all of the user's sessions in one transaction."""
    if user_id == current_user.id:
        raise BadRequest("You can't ban your own account.")
    user = await _get_user_or_404(db, user_id)
    if _ADMIN_PERMISSION in user.permissions:
        raise BadRequest("Administrators can't be banned here. Remove their role first.")

    user.is_active = False
    count = await _delete_user_sessions(db, user_id)
    await db.commit()
    return AdminActionResponse(
        success=True, message=f"User banned and {count} session(s) revoked."
    )


@admin_users_router.post(
    "/users/{user_id}/unban",
    response_model=AdminActionResponse,
    status_code=status.HTTP_200_OK,
)
async def unban_user(
    user_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["users:ban"]),
):
    user = await _get_user_or_404(db, user_id)
    user.is_active = True
    await db.commit()
    return AdminActionResponse(success=True, message="User unbanned.")
