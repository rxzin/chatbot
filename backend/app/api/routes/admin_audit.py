from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from auth.service import get_current_active_user
from core.database import get_db
from core.errors import BadRequest
from schemas.admin import AdminSummaryResponse, AuditLogPage, AuditLogResponse
from schemas.models import AuditLog, PendingJiraTicket, Session, User

admin_audit_router = APIRouter(prefix="/admin")

_STATUS_RANGES = {"2xx": (200, 299), "3xx": (300, 399), "4xx": (400, 499), "5xx": (500, 599)}


async def _count(db: AsyncSession, *conditions, model) -> int:
    result = await db.execute(select(func.count()).select_from(model).where(*conditions))
    return result.scalar_one()


@admin_audit_router.get(
    "/summary",
    response_model=AdminSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["audit:read"]),
):
    """Headline numbers for the admin dashboard."""
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(hours=24)
    return AdminSummaryResponse(
        pending_tickets=await _count(
            db, PendingJiraTicket.status == "pending", model=PendingJiraTicket
        ),
        total_users=await _count(db, model=User),
        banned_users=await _count(db, User.is_active.is_(False), model=User),
        active_sessions=await _count(
            db,
            Session.expires_at > now,
            Session.absolute_expires_at > now,
            model=Session,
        ),
        requests_24h=await _count(db, AuditLog.created_at >= day_ago, model=AuditLog),
        # Only 5xx: 4xx is mostly normal use (logged-out 401s, wrong passwords,
        # taken emails, rate limits), which made the count look alarming.
        failed_requests_24h=await _count(
            db,
            AuditLog.created_at >= day_ago,
            AuditLog.status_code >= 500,
            model=AuditLog,
        ),
    )


@admin_audit_router.get(
    "/audit-logs",
    response_model=AuditLogPage,
    status_code=status.HTTP_200_OK,
)
async def list_audit_logs(
    email: Optional[str] = Query(default=None, max_length=255),
    path: Optional[str] = Query(default=None, max_length=512),
    method: Optional[Literal["GET", "POST", "PUT", "PATCH", "DELETE"]] = None,
    status_class: Optional[Literal["2xx", "3xx", "4xx", "5xx"]] = None,
    cursor: Optional[UUID] = None,
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["audit:read"]),
):
    """List requests, newest first. The cursor is a row id; paging is by (created_at, id)."""
    stmt = (
        select(AuditLog, User.email)
        .outerjoin(User, AuditLog.user_id == User.id)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(limit + 1)
    )
    if cursor:
        cursor_created_at = await db.scalar(
            select(AuditLog.created_at).where(AuditLog.id == cursor)
        )
        if cursor_created_at is None:
            raise BadRequest("Unknown cursor")
        stmt = stmt.where(
            tuple_(AuditLog.created_at, AuditLog.id) < (cursor_created_at, cursor)
        )
    if email:
        stmt = stmt.where(User.email.icontains(email, autoescape=True))
    if path:
        stmt = stmt.where(AuditLog.path.icontains(path, autoescape=True))
    if method:
        stmt = stmt.where(AuditLog.method == method)
    if status_class:
        low, high = _STATUS_RANGES[status_class]
        stmt = stmt.where(AuditLog.status_code.between(low, high))

    rows = (await db.execute(stmt)).all()
    page = rows[:limit]
    return AuditLogPage(
        items=[
            AuditLogResponse(
                id=log.id,
                user_id=log.user_id,
                user_email=user_email,
                method=log.method,
                path=log.path,
                status_code=log.status_code,
                duration_ms=log.duration_ms,
                ip_address=log.ip_address,
                user_agent=log.user_agent,
                request_id=log.request_id,
                created_at=log.created_at,
            )
            for log, user_email in page
        ],
        next_cursor=page[-1][0].id if len(rows) > limit else None,
    )
