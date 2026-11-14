from fastapi import Header

from core.errors import ValidationError


def idempotency_key(
    value: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=128
    ),
) -> str | None:
    """
    The optional Idempotency-Key header. A repeat request with the same key returns the
    original result instead of doing the work again. Absent means no idempotency.
    """
    if value is not None and not value.strip():
        raise ValidationError("Idempotency-Key must not be empty")
    return value
