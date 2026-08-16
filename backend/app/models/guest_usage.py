from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from .base import Base


class GuestUsage(Base):
    """Tracks the rolling weekly generation quota for a guest device.

    generation_count is PERIOD-SCOPED and RESETS every 7 days (the window
    rolls forward from period_started_at) — it is explicitly NOT a lifetime
    total. Do not "fix" this into a monotonic counter.

    No FK to users — guests have no user row.
    """

    __tablename__ = "guest_usage"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    device_id = Column(String(36), unique=True, index=True, nullable=False)
    period_started_at = Column(DateTime(timezone=True), nullable=False)
    generation_count = Column(Integer, nullable=False, default=0)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<GuestUsage(device_id='{self.device_id}', generation_count={self.generation_count})>"
