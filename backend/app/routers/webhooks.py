import hmac
import os
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.webhook import RevenueCatWebhookPayload
from ..services.revenuecat_service import process_revenuecat_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


def verify_revenuecat_secret(authorization: str = Header(None)) -> None:
    expected = os.getenv("REVENUECAT_WEBHOOK_SECRET")
    if not expected or not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook credentials")


@router.post("/revenuecat")
async def revenuecat_webhook(
    payload: RevenueCatWebhookPayload,
    db: Session = Depends(get_db),
    _: None = Depends(verify_revenuecat_secret),
):
    process_revenuecat_event(db, payload.event)
    return {"status": "ok"}
