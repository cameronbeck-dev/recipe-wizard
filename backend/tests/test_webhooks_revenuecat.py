"""Tests for /api/webhooks/revenuecat — RevenueCat subscription event handling."""
from datetime import datetime, timedelta, timezone

from app.models import User

WEBHOOK_SECRET = "test-webhook-secret"


def _event(type="RENEWAL", app_user_id=None, expiration_at_ms=None, **overrides):
    event = {
        "id": overrides.pop("id", "evt_1"),
        "type": type,
        "event_timestamp_ms": overrides.pop("event_timestamp_ms", 1000),
        "app_user_id": app_user_id,
        "expiration_at_ms": expiration_at_ms,
    }
    event.update(overrides)
    return {"api_version": "1.0", "event": event}


def _post(client, body, secret=WEBHOOK_SECRET):
    headers = {}
    if secret is not None:
        headers["Authorization"] = secret
    return client.post("/api/webhooks/revenuecat", json=body, headers=headers)


def _future_ms(days=30):
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp() * 1000)


def _past_ms(days=1):
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)


class TestAuth:
    def test_correct_secret_succeeds(self, client, user):
        body = _event(type="TEST", app_user_id=str(user.id))
        response = _post(client, body)
        assert response.status_code == 200

    def test_wrong_secret_rejected(self, client, user):
        body = _event(type="TEST", app_user_id=str(user.id))
        response = _post(client, body, secret="wrong-secret")
        assert response.status_code == 401

    def test_missing_header_rejected(self, client, user):
        body = _event(type="TEST", app_user_id=str(user.id))
        response = _post(client, body, secret=None)
        assert response.status_code == 401

    def test_unset_secret_fails_closed(self, client, user, monkeypatch):
        monkeypatch.delenv("REVENUECAT_WEBHOOK_SECRET", raising=False)
        body = _event(type="TEST", app_user_id=str(user.id))
        response = _post(client, body, secret="")
        assert response.status_code == 401


class TestGrantEvents:
    def test_initial_purchase_grants_premium(self, client, user, db_session):
        body = _event(
            type="INITIAL_PURCHASE",
            app_user_id=str(user.id),
            expiration_at_ms=_future_ms(),
        )
        response = _post(client, body)
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.premium_expires_at is not None
        assert refreshed.is_premium is True

    def test_renewal_extends_expiry(self, client, user, db_session):
        _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(days=10), event_timestamp_ms=100,
        ))
        _post(client, _event(
            type="RENEWAL", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(days=40), event_timestamp_ms=200,
        ))

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        expected = datetime.fromtimestamp(_future_ms(days=40) / 1000, tz=timezone.utc)
        assert abs((refreshed.premium_expires_at.replace(tzinfo=timezone.utc) - expected).total_seconds()) < 5


class TestCancellationAndBillingIssue:
    def test_cancellation_does_not_revoke(self, client, user, db_session):
        future = _future_ms(days=10)
        _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=future, event_timestamp_ms=100,
        ))
        response = _post(client, _event(
            type="CANCELLATION", app_user_id=str(user.id), event_timestamp_ms=200,
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is True

    def test_billing_issue_does_not_revoke_and_extends_to_grace_period(self, client, user, db_session):
        _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(days=1), event_timestamp_ms=100,
        ))
        grace_ms = _future_ms(days=20)
        _post(client, _event(
            type="BILLING_ISSUE", app_user_id=str(user.id),
            event_timestamp_ms=200, grace_period_expiration_at_ms=grace_ms,
        ))

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is True
        expected = datetime.fromtimestamp(grace_ms / 1000, tz=timezone.utc)
        assert abs((refreshed.premium_expires_at.replace(tzinfo=timezone.utc) - expected).total_seconds()) < 5


class TestExpiration:
    def test_expiration_revokes(self, client, user, db_session):
        _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(days=10), event_timestamp_ms=100,
        ))
        response = _post(client, _event(
            type="EXPIRATION", app_user_id=str(user.id),
            expiration_at_ms=_past_ms(), event_timestamp_ms=200,
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is False

    def test_self_healing_past_expiry_is_not_premium(self, db_session, user_factory):
        u = user_factory()
        u.premium_expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.add(u)
        db_session.commit()
        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=u.id).first()
        assert refreshed.is_premium is False


class TestUnresolvedUsersAndIgnoredEvents:
    def test_unknown_anonymous_app_user_id_no_op(self, client):
        response = _post(client, _event(type="INITIAL_PURCHASE", app_user_id="$RCAnonymousID:abc123", expiration_at_ms=_future_ms()))
        assert response.status_code == 200

    def test_unknown_numeric_app_user_id_no_op(self, client, db_session):
        response = _post(client, _event(type="INITIAL_PURCHASE", app_user_id="999999", expiration_at_ms=_future_ms()))
        assert response.status_code == 200
        assert db_session.query(User).filter_by(id=999999).first() is None

    def test_test_event_type_no_mutation(self, client, user, db_session):
        response = _post(client, _event(type="TEST", app_user_id=str(user.id)))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.premium_expires_at is None

    def test_entitlement_filter_ignores_unrelated_entitlement(self, client, user, db_session):
        response = _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(), entitlement_ids=["some_other_entitlement"],
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.premium_expires_at is None

    def test_lenient_parsing_ignores_unknown_fields(self, client, user):
        body = _event(type="TEST", app_user_id=str(user.id))
        body["some_unexpected_field"] = "surprise"
        body["event"]["another_unexpected_field"] = 123
        response = _post(client, body)
        assert response.status_code == 200


class TestIdempotencyAndOrdering:
    def test_idempotent_replay_same_result(self, client, user, db_session):
        body = _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(), event_timestamp_ms=100,
        )
        r1 = _post(client, body)
        assert r1.status_code == 200
        db_session.expire_all()
        first_expiry = db_session.query(User).filter_by(id=user.id).first().premium_expires_at

        r2 = _post(client, body)
        assert r2.status_code == 200
        db_session.expire_all()
        second_expiry = db_session.query(User).filter_by(id=user.id).first().premium_expires_at

        assert first_expiry == second_expiry

    def test_out_of_order_stale_renewal_does_not_regrant(self, client, user, db_session):
        _post(client, _event(
            type="EXPIRATION", app_user_id=str(user.id),
            expiration_at_ms=_past_ms(), event_timestamp_ms=200,
        ))
        _post(client, _event(
            type="RENEWAL", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(), event_timestamp_ms=100,
        ))

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is False

    def test_alias_fallback_resolves_user(self, client, user, db_session):
        response = _post(client, _event(
            type="INITIAL_PURCHASE",
            app_user_id="$RCAnonymousID:def456",
            aliases=[str(user.id)],
            expiration_at_ms=_future_ms(),
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is True


class TestSandbox:
    def test_sandbox_processed_when_allowed(self, client, user, db_session, monkeypatch):
        monkeypatch.setenv("REVENUECAT_ALLOW_SANDBOX", "true")
        response = _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(), environment="SANDBOX",
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.is_premium is True

    def test_sandbox_ignored_when_disallowed(self, client, user, db_session, monkeypatch):
        monkeypatch.setenv("REVENUECAT_ALLOW_SANDBOX", "false")
        response = _post(client, _event(
            type="INITIAL_PURCHASE", app_user_id=str(user.id),
            expiration_at_ms=_future_ms(), environment="SANDBOX",
        ))
        assert response.status_code == 200

        db_session.expire_all()
        refreshed = db_session.query(User).filter_by(id=user.id).first()
        assert refreshed.premium_expires_at is None
