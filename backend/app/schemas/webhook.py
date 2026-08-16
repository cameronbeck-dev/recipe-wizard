from pydantic import BaseModel, ConfigDict
from typing import List, Optional


class RevenueCatEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: Optional[str] = None
    type: str
    event_timestamp_ms: Optional[int] = None
    app_user_id: Optional[str] = None
    original_app_user_id: Optional[str] = None
    aliases: Optional[List[str]] = None
    product_id: Optional[str] = None
    entitlement_ids: Optional[List[str]] = None
    expiration_at_ms: Optional[int] = None
    grace_period_expiration_at_ms: Optional[int] = None
    environment: Optional[str] = None


class RevenueCatWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_version: Optional[str] = None
    event: RevenueCatEvent
