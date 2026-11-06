from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, Security, status
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.service import get_current_active_user
from core.config import getSettings
from core.database import get_db
from schemas.admin import UsageBreakdown, UsageDay, UsageSummaryResponse, UsageTopUser
from schemas.models import LlmUsage, Message, User

admin_usage_router = APIRouter(prefix="/admin")

_TOTAL = LlmUsage.prompt_tokens + LlmUsage.completion_tokens


@admin_usage_router.get(
    "/usage",
    response_model=UsageSummaryResponse,
    status_code=status.HTTP_200_OK,
)
async def get_usage(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Security(get_current_active_user, scopes=["audit:read"]),
):
    """Token usage of model calls: headline numbers, breakdowns and a daily series."""
    now = datetime.now(timezone.utc)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since = start_today - timedelta(days=days - 1)
    week = start_today - timedelta(days=6)

    async def tokens_since(when: datetime) -> int:
        result = await db.execute(select(func.coalesce(func.sum(_TOTAL), 0)).where(LlmUsage.created_at >= when))
        return int(result.scalar_one())

    window = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
                func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
                func.count(func.distinct(LlmUsage.user_id)),
                func.count().filter(LlmUsage.model == getSettings().MISTRAL_FALLBACK_MODEL),
            ).where(LlmUsage.created_at >= since)
        )
    ).one()
    calls, prompt_tokens, completion_tokens, active_users, fallback_calls = (int(v) for v in window)

    replies = int(
        (
            await db.execute(
                select(func.count()).select_from(Message).where(Message.role == "model", Message.created_at >= since)
            )
        ).scalar_one()
    )

    async def breakdown(column) -> list[UsageBreakdown]:
        rows = await db.execute(
            select(
                column,
                func.count(),
                func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
                func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
            )
            .where(LlmUsage.created_at >= since)
            .group_by(column)
            .order_by(func.sum(_TOTAL).desc())
        )
        return [
            UsageBreakdown(key=key, calls=c, prompt_tokens=int(p), completion_tokens=int(o))
            for key, c, p, o in rows.all()
        ]

    top = await db.execute(
        select(LlmUsage.user_id, User.email, func.count(), func.coalesce(func.sum(_TOTAL), 0))
        .outerjoin(User, User.id == LlmUsage.user_id)
        .where(LlmUsage.created_at >= since)
        .group_by(LlmUsage.user_id, User.email)
        .order_by(func.sum(_TOTAL).desc())
        .limit(10)
    )

    day = cast(LlmUsage.created_at, Date)
    daily_rows = await db.execute(
        select(
            day,
            func.coalesce(func.sum(LlmUsage.prompt_tokens), 0),
            func.coalesce(func.sum(LlmUsage.completion_tokens), 0),
        )
        .where(LlmUsage.created_at >= since)
        .group_by(day)
        .order_by(day)
    )
    by_day = {d.isoformat(): (int(p), int(o)) for d, p, o in daily_rows.all()}
    daily = [
        UsageDay(day=d, prompt_tokens=by_day.get(d, (0, 0))[0], completion_tokens=by_day.get(d, (0, 0))[1])
        for d in ((since + timedelta(days=i)).date().isoformat() for i in range(days))
    ]

    total = prompt_tokens + completion_tokens
    return UsageSummaryResponse(
        window_days=days,
        tokens_today=await tokens_since(start_today),
        tokens_7d=await tokens_since(week),
        tokens_window=total,
        prompt_tokens_window=prompt_tokens,
        completion_tokens_window=completion_tokens,
        model_calls_window=calls,
        replies_window=replies,
        avg_tokens_per_reply=round(total / replies) if replies else 0,
        active_users_window=active_users,
        fallback_share=round(fallback_calls / calls, 4) if calls else 0.0,
        by_purpose=await breakdown(LlmUsage.purpose),
        by_model=await breakdown(LlmUsage.model),
        top_users=[UsageTopUser(user_id=u, email=e, calls=c, total_tokens=int(t)) for u, e, c, t in top.all()],
        daily=daily,
    )
