import os
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from ..models import GuestUsage

logger = logging.getLogger(__name__)

GUEST_WEEKLY_LIMIT = int(os.getenv("GUEST_WEEKLY_LIMIT", "10"))
_WINDOW = timedelta(days=7)


class GuestQuotaState(NamedTuple):
    remaining: int
    reset_at: datetime


class GuestQuotaExceeded(Exception):
    """Raised when a guest device has used up its weekly generation quota."""

    def __init__(self, reset_at: datetime):
        self.reset_at = reset_at
        super().__init__(f"Guest weekly quota exceeded, resets at {reset_at.isoformat()}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def check_and_reserve_generation(db: Session, device_id: str) -> GuestQuotaState:
    """Look up (or create) the device's usage row, apply the rolling 7-day
    window reset if due, and reserve one generation.

    Raises GuestQuotaExceeded (without incrementing) if the device has no
    generations left in the current period.
    """
    now = _now()

    usage = (
        db.query(GuestUsage)
        .filter(GuestUsage.device_id == device_id)
        .with_for_update()
        .first()
    )

    if usage is None:
        # Two truly concurrent first-ever requests from the same device can
        # both reach here (nothing to row-lock yet, since no row exists).
        # The unique index on device_id makes the loser's insert raise
        # IntegrityError instead of silently duplicating a row - recover by
        # rolling back and re-reading the winner's row under the lock.
        usage = GuestUsage(
            device_id=device_id,
            period_started_at=now,
            generation_count=0,
        )
        db.add(usage)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            usage = (
                db.query(GuestUsage)
                .filter(GuestUsage.device_id == device_id)
                .with_for_update()
                .first()
            )

    period_started_at = usage.period_started_at
    if period_started_at.tzinfo is None:
        period_started_at = period_started_at.replace(tzinfo=timezone.utc)

    if now - period_started_at >= _WINDOW:
        usage.period_started_at = now
        usage.generation_count = 0
        period_started_at = now

    if usage.generation_count >= GUEST_WEEKLY_LIMIT:
        reset_at = period_started_at + _WINDOW
        raise GuestQuotaExceeded(reset_at=reset_at)

    usage.generation_count += 1
    usage.last_seen_at = func.now()
    db.commit()

    return GuestQuotaState(
        remaining=GUEST_WEEKLY_LIMIT - usage.generation_count,
        reset_at=period_started_at + _WINDOW,
    )


def get_remaining(db: Session, device_id: str) -> GuestQuotaState:
    """Read-only equivalent of check_and_reserve_generation, for status checks."""
    now = _now()

    usage = db.query(GuestUsage).filter(GuestUsage.device_id == device_id).first()

    if usage is None:
        return GuestQuotaState(remaining=GUEST_WEEKLY_LIMIT, reset_at=now + _WINDOW)

    period_started_at = usage.period_started_at
    if period_started_at.tzinfo is None:
        period_started_at = period_started_at.replace(tzinfo=timezone.utc)

    generation_count = usage.generation_count
    if now - period_started_at >= _WINDOW:
        period_started_at = now
        generation_count = 0

    return GuestQuotaState(
        remaining=max(0, GUEST_WEEKLY_LIMIT - generation_count),
        reset_at=period_started_at + _WINDOW,
    )
