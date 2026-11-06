from fastapi import Request

from core.client_info import trusted_client_ip
from core.config import getSettings
from core.errors import TooManyRequestsError
from core.logging import logger


def _limits(request: Request, email: str) -> list[tuple[str, int]]:
    settings = getSettings()
    limits = [
        (
            f"login_failures:account:{email.strip().lower()}",
            settings.LOGIN_MAX_FAILURES_PER_ACCOUNT,
        )
    ]
    ip = trusted_client_ip(request)
    if ip:
        limits.append((f"login_failures:ip:{ip}", settings.LOGIN_MAX_FAILURES_PER_IP))
    return limits


async def ensure_login_allowed(request: Request, email: str) -> None:
    """Reject the attempt before checking the password if a limit has been reached."""
    redis = request.app.state.redis_service.redis_client
    limits = _limits(request, email)
    try:
        counts = [await redis.get(key) for key, _ in limits]
    except Exception:
        # Losing Redis should not lock everyone out of the app.
        logger.exception("Login rate limit check failed")
        return

    for count, (_, limit) in zip(counts, limits):
        if count is not None and int(count) >= limit:
            raise TooManyRequestsError(
                "Too many failed login attempts. Please try again later."
            )


async def record_login_failure(request: Request, email: str) -> None:
    redis = request.app.state.redis_service.redis_client
    window = getSettings().LOGIN_RATE_LIMIT_WINDOW_SECONDS
    try:
        for key, _ in _limits(request, email):
            if await redis.incr(key) == 1:
                await redis.expire(key, window)
    except Exception:
        logger.exception("Failed to record login failure")


async def clear_login_failures(request: Request, email: str) -> None:
    """Reset the account counter. The IP counter stays, so one valid login can't reset it."""
    redis = request.app.state.redis_service.redis_client
    key, _ = _limits(request, email)[0]
    try:
        await redis.delete(key)
    except Exception:
        logger.exception("Failed to clear login failures")


def _registration_limits(request: Request) -> list[tuple[str, int, str]]:
    """Return (key, limit, message) for each sign-up limit that applies."""
    settings = getSettings()
    limits = [
        (
            "registrations:all",
            settings.REGISTRATION_MAX_GLOBAL,
            "Sign-ups are paused for a while. Please try again later.",
        )
    ]
    # Without a trusted IP every visitor shares one address (the proxy), so a
    # per-IP cap would lock out everyone at once, like a shared Wi-Fi network.
    ip = trusted_client_ip(request)
    if ip:
        limits.append(
            (
                f"registrations:ip:{ip}",
                settings.REGISTRATION_MAX_PER_IP,
                "Too many sign-ups from this network. Please try again later.",
            )
        )
    return limits


async def ensure_registration_allowed(request: Request) -> None:
    """Count this sign-up attempt and reject it once a limit is reached."""
    redis = request.app.state.redis_service.redis_client
    window = getSettings().REGISTRATION_RATE_LIMIT_SECONDS
    exceeded: str | None = None
    try:
        for key, limit, message in _registration_limits(request):
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window)
            if count > limit and exceeded is None:
                exceeded = message
    except Exception:
        # Losing Redis should not stop people from signing up.
        logger.exception("Registration rate limit check failed")
        return

    if exceeded:
        raise TooManyRequestsError(exceeded)
