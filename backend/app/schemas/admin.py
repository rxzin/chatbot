from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AdminSummaryResponse(BaseModel):
    pending_tickets: int
    total_users: int
    banned_users: int
    active_sessions: int
    requests_24h: int
    failed_requests_24h: int


class AuditLogResponse(BaseModel):
    id: UUID
    user_id: Optional[UUID]
    user_email: Optional[str]
    method: str
    path: str
    status_code: int
    duration_ms: int
    ip_address: Optional[str]
    user_agent: Optional[str]
    request_id: Optional[str]
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogResponse]
    next_cursor: Optional[UUID]


class AdminUserResponse(BaseModel):
    id: UUID
    email: str
    is_active: bool
    is_admin: bool
    is_self: bool
    active_sessions: int
    created_at: datetime


class AdminUserPage(BaseModel):
    items: list[AdminUserResponse]
    next_cursor: Optional[UUID]


class AdminSessionResponse(BaseModel):
    id: UUID
    ip_address: Optional[str]
    user_agent: Optional[str]
    is_current: bool
    created_at: datetime
    last_rotated_at: Optional[datetime]
    expires_at: datetime


class UsageBreakdown(BaseModel):
    key: str
    calls: int
    prompt_tokens: int
    completion_tokens: int


class UsageTopUser(BaseModel):
    user_id: UUID
    email: Optional[str]
    calls: int
    total_tokens: int


class UsageDay(BaseModel):
    day: str
    prompt_tokens: int
    completion_tokens: int


class UsageSummaryResponse(BaseModel):
    window_days: int
    tokens_today: int
    tokens_7d: int
    tokens_window: int
    prompt_tokens_window: int
    completion_tokens_window: int
    model_calls_window: int
    replies_window: int
    avg_tokens_per_reply: int
    active_users_window: int
    fallback_share: float
    by_purpose: list[UsageBreakdown]
    by_model: list[UsageBreakdown]
    top_users: list[UsageTopUser]
    daily: list[UsageDay]
