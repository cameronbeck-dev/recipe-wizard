import os
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from ..models import User
from ..schemas.webhook import RevenueCatEvent

logger = logging.getLogger(__name__)

_ENTITLEMENT_ID_ENV = os.getenv("REVENUECAT_ENTITLEMENT_ID")
if not _ENTITLEMENT_ID_ENV:
    logger.warning("REVENUECAT_ENTITLEMENT_ID not set, defaulting to 'premium_features'")
ENTITLEMENT_ID = _ENTITLEMENT_ID_ENV or "premium_features"

# Lifetime/non-renewing purchases with no expiration are granted access until this
# far-future sentinel rather than treated as "never expires" (None), so `is_premium`
# keeps working off a single expiry comparison.
LIFETIME_SENTINEL = datetime(2099, 1, 1, tzinfo=timezone.utc)

_ALLOW_SANDBOX_WARNED = False

_GRANT_EVENT_TYPES = {
    "INITIAL_PURCHASE", "RENEWAL", "PRODUCT_CHANGE", "UNCANCELLATION",
    "SUBSCRIPTION_EXTENDED", "TEMPORARY_ENTITLEMENT_GRANT",
}
_REVOKE_EVENT_TYPES = {"EXPIRATION", "SUBSCRIPTION_PAUSED"}
_NOOP_EVENT_TYPES = {"TEST", "SUBSCRIBER_ALIAS", "INVOICE_ISSUANCE"}


def _resolve_user(db: Session, event: RevenueCatEvent) -> Optional[User]:
    candidates = []
    if event.app_user_id:
        candidates.append(event.app_user_id)
    if event.original_app_user_id:
        candidates.append(event.original_app_user_id)
    candidates.extend(event.aliases or [])

    for candidate in candidates:
        if not candidate.isdigit():
            continue
        user = db.query(User).filter(User.id == int(candidate)).first()
        if user:
            user.revenuecat_customer_id = candidate
            return user
    return None


def _is_sandbox_allowed() -> bool:
    global _ALLOW_SANDBOX_WARNED
    raw = os.getenv("REVENUECAT_ALLOW_SANDBOX")
    if raw is None:
        if not _ALLOW_SANDBOX_WARNED:
            logger.warning(
                "REVENUECAT_ALLOW_SANDBOX not explicitly configured, defaulting to allow — "
                "set to 'false' after launch stabilizes to reject sandbox purchases in production"
            )
            _ALLOW_SANDBOX_WARNED = True
        return True
    return raw.lower() != "false"


def process_revenuecat_event(db: Session, event: RevenueCatEvent) -> None:
    user = _resolve_user(db, event)
    if user is None:
        logger.info(f"RevenueCat event for unknown app_user_id={event.app_user_id!r}, ignoring")
        return

    if event.entitlement_ids and ENTITLEMENT_ID not in event.entitlement_ids:
        logger.info(
            f"RevenueCat event entitlement_ids={event.entitlement_ids} does not include "
            f"{ENTITLEMENT_ID!r} for user {user.id}, ignoring"
        )
        return

    if (
        user.premium_event_at_ms is not None
        and event.event_timestamp_ms is not None
        and event.event_timestamp_ms <= user.premium_event_at_ms
    ):
        logger.info(
            f"Stale/replayed RevenueCat event ({event.event_timestamp_ms}) for user {user.id}, ignoring"
        )
        return

    if event.environment == "SANDBOX":
        if not _is_sandbox_allowed():
            logger.info(f"Ignoring SANDBOX RevenueCat event for user {user.id} (REVENUECAT_ALLOW_SANDBOX=false)")
            return
        logger.warning(f"Processing SANDBOX RevenueCat event for user {user.id}")

    event_type = event.type

    if event_type in _GRANT_EVENT_TYPES:
        if event.expiration_at_ms is not None:
            user.premium_expires_at = datetime.fromtimestamp(event.expiration_at_ms / 1000, tz=timezone.utc)
        user.premium_product_id = event.product_id

    elif event_type == "NON_RENEWING_PURCHASE":
        if event.expiration_at_ms is not None:
            user.premium_expires_at = datetime.fromtimestamp(event.expiration_at_ms / 1000, tz=timezone.utc)
        else:
            user.premium_expires_at = LIFETIME_SENTINEL
        user.premium_product_id = event.product_id

    elif event_type == "CANCELLATION":
        # Auto-renew turned off — access continues until the existing expiry. Only
        # sync the stored expiry if RevenueCat sent one; never shorten access below
        # what's already granted here.
        if event.expiration_at_ms is not None:
            user.premium_expires_at = datetime.fromtimestamp(event.expiration_at_ms / 1000, tz=timezone.utc)

    elif event_type == "BILLING_ISSUE":
        if event.grace_period_expiration_at_ms is not None:
            grace_expiry = datetime.fromtimestamp(event.grace_period_expiration_at_ms / 1000, tz=timezone.utc)
            current_expiry = user.premium_expires_at
            if current_expiry is not None and current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=timezone.utc)
            if current_expiry is None or grace_expiry > current_expiry:
                user.premium_expires_at = grace_expiry

    elif event_type in _REVOKE_EVENT_TYPES:
        if event.expiration_at_ms is not None:
            user.premium_expires_at = datetime.fromtimestamp(event.expiration_at_ms / 1000, tz=timezone.utc)
        else:
            user.premium_expires_at = datetime.now(timezone.utc)

    elif event_type == "TRANSFER":
        logger.info(f"TRANSFER event received, not yet handled: {event.id}")
        return

    elif event_type in _NOOP_EVENT_TYPES:
        logger.info(f"Ignoring {event_type} RevenueCat event for user {user.id}")
        return

    else:
        logger.warning(f"Unrecognized RevenueCat event type {event_type!r} for user {user.id}")
        return

    if event.event_timestamp_ms is not None:
        user.premium_event_at_ms = event.event_timestamp_ms
    db.commit()
