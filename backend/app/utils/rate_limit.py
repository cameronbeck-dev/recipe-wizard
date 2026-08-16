from fastapi import HTTPException, status
from fastapi_limiter import FastAPILimiter


async def require_rate_limiter_available() -> None:
    """
    Fail-closed guard for the guest generation branch only.

    Guests deliberately invert the app's default fail-open behavior: if the
    rate limiter backend (Redis) hasn't been initialized, guest generation
    is unavailable rather than silently unmetered. Authenticated requests
    are untouched by this guard and keep the existing fail-open behavior.
    """
    if FastAPILimiter.redis is None:
        # NOTE: detail is a plain string, not a dict — the app's global
        # HTTPException handler (main.py) builds an ErrorResponse whose
        # `detail` field is typed `str`; a dict there breaks the handler.
        # See the shopping_list.py 409 dict-body workaround for the
        # alternative when a structured error body is actually required.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GUEST_MODE_UNAVAILABLE: Guest recipe generation is temporarily unavailable. Please sign in or try again shortly."
        )
