"""Tests for guest mode — unauthenticated recipe generation.

The rolling weekly quota (check_and_reserve_generation) uses
`with_for_update()` for row-level locking under real Postgres. That lock
isn't meaningfully exercised here since the suite runs on in-memory SQLite
(`with_for_update()` is a no-op there) — these tests cover the quota logic
and reset behavior, not concurrency safety under real Postgres locking.

Background job processing is stubbed to a no-op (mirrors test_jobs.py) for
tests that create a job over HTTP and don't care about completion, so no
real OpenAI calls happen. The completion tests build a job row directly
and await `_process_generation_job` for real, with the fake OpenAI client.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models import RecipeJob, GuestUsage
from app.services import guest_service
from app.services.job_service import job_service


def _device_id() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def stub_job_processors(monkeypatch):
    """Replace the actual background processors with no-ops (see test_jobs.py)."""
    from app.services import job_service as js

    async def noop(self, job_id):
        return None

    monkeypatch.setattr(js.RecipeJobService, "_process_generation_job", noop)
    monkeypatch.setattr(js.RecipeJobService, "_process_modification_job", noop)


@pytest.fixture(autouse=True)
def _guest_mode_available(monkeypatch):
    """Simulate an initialized rate limiter backend by default so the
    fail-closed guard doesn't block guest generation in tests that aren't
    specifically exercising the uninitialized case.
    """
    from fastapi_limiter import FastAPILimiter
    monkeypatch.setattr(FastAPILimiter, "redis", object())


# ---------------------------------------------------------------------------
# Basic guest access
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("stub_job_processors")
class TestGuestGenerateAccess:
    def test_guest_generate_succeeds_with_valid_device_id(self, client):
        device_id = _device_id()
        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": device_id},
            json={"prompt": "garlic butter shrimp"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["job_id"]
        assert body["status"] == "pending"
        assert body["guest_generations_remaining"] == 9
        assert body["guest_quota_reset_at"]

    def test_malformed_device_id_returns_400(self, client):
        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": "not-a-uuid"},
            json={"prompt": "garlic butter shrimp"},
        )
        assert response.status_code == 400

    def test_no_auth_and_no_device_id_returns_401(self, client):
        response = client.post(
            "/api/jobs/recipes/generate",
            json={"prompt": "garlic butter shrimp"},
        )
        assert response.status_code == 401

    def test_persists_device_id_not_user_id(self, client, db_session):
        device_id = _device_id()
        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": device_id},
            json={"prompt": "garlic butter shrimp"},
        )
        job_id = response.json()["job_id"]
        job = db_session.query(RecipeJob).filter_by(id=job_id).first()
        assert job.user_id is None
        assert job.device_id == device_id


# ---------------------------------------------------------------------------
# Weekly quota
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("stub_job_processors")
class TestGuestQuota:
    def test_eleventh_generation_in_window_returns_quota_exceeded(self, client, db_session):
        device_id = _device_id()
        for _ in range(guest_service.GUEST_WEEKLY_LIMIT):
            guest_service.check_and_reserve_generation(db_session, device_id)

        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": device_id},
            json={"prompt": "one too many"},
        )
        assert response.status_code == 429
        body = response.json()
        assert body["code"] == "GUEST_QUOTA_EXCEEDED"
        assert body["reset_at"]

    def test_quota_renews_after_seven_days(self, client, db_session):
        device_id = _device_id()
        usage = GuestUsage(
            device_id=device_id,
            period_started_at=datetime.now(timezone.utc) - timedelta(days=8),
            generation_count=guest_service.GUEST_WEEKLY_LIMIT,
        )
        db_session.add(usage)
        db_session.commit()

        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": device_id},
            json={"prompt": "fresh window"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["guest_generations_remaining"] == guest_service.GUEST_WEEKLY_LIMIT - 1

    def test_partially_elapsed_window_does_not_reset(self, client, db_session):
        device_id = _device_id()
        usage = GuestUsage(
            device_id=device_id,
            period_started_at=datetime.now(timezone.utc) - timedelta(days=3),
            generation_count=guest_service.GUEST_WEEKLY_LIMIT,
        )
        db_session.add(usage)
        db_session.commit()

        response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": device_id},
            json={"prompt": "still capped"},
        )
        assert response.status_code == 429


# ---------------------------------------------------------------------------
# Job ownership isolation
# ---------------------------------------------------------------------------
class TestGuestJobOwnership:
    def test_device_a_cannot_read_device_b_job(self, client, db_session):
        device_a = _device_id()
        device_b = _device_id()
        job = RecipeJob(id="job-guest-b", device_id=device_b, status="pending",
                         job_type="generate", prompt="x", progress=0)
        db_session.add(job)
        db_session.commit()

        response = client.get(
            "/api/jobs/recipes/job-guest-b/status",
            headers={"X-Device-Id": device_a},
        )
        assert response.status_code == 404

    def test_guest_cannot_read_authenticated_users_job(self, client, db_session, user):
        job = RecipeJob(id="job-auth-user", user_id=user.id, status="pending",
                         job_type="generate", prompt="x", progress=0)
        db_session.add(job)
        db_session.commit()

        response = client.get(
            "/api/jobs/recipes/job-auth-user/status",
            headers={"X-Device-Id": _device_id()},
        )
        assert response.status_code == 404

    def test_authenticated_user_cannot_read_guest_job(self, client, db_session, auth_headers):
        device_id = _device_id()
        job = RecipeJob(id="job-guest-only", device_id=device_id, status="pending",
                         job_type="generate", prompt="x", progress=0)
        db_session.add(job)
        db_session.commit()

        response = client.get(
            "/api/jobs/recipes/job-guest-only/status",
            headers=auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# Fail-closed guard
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("stub_job_processors")
class TestFailClosedGuard:
    def test_rate_limiter_uninitialized_blocks_guest_but_not_auth(self, client, monkeypatch, auth_headers):
        from fastapi_limiter import FastAPILimiter
        monkeypatch.setattr(FastAPILimiter, "redis", None)

        guest_response = client.post(
            "/api/jobs/recipes/generate",
            headers={"X-Device-Id": _device_id()},
            json={"prompt": "guest attempt"},
        )
        assert guest_response.status_code == 503

        auth_response = client.post(
            "/api/jobs/recipes/generate",
            headers=auth_headers,
            json={"prompt": "auth attempt"},
        )
        assert auth_response.status_code == 200, auth_response.text


# ---------------------------------------------------------------------------
# /modify remains auth-only
# ---------------------------------------------------------------------------
class TestModifyStillAuthRequired:
    def test_modify_rejects_unauthenticated_guest(self, client):
        response = client.post(
            "/api/jobs/recipes/modify",
            headers={"X-Device-Id": _device_id()},
            json={"recipe_id": "1", "modification_prompt": "make it spicier"},
        )
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# End-to-end completion (NOT using stub_job_processors — these await the
# real processor directly against a job row inserted straight into the DB,
# bypassing the HTTP creation endpoint entirely so there's no race with a
# fire-and-forget background task).
# ---------------------------------------------------------------------------
class TestGuestJobCompletion:
    async def test_guest_job_completes_and_result_returns_result_json(
        self, client, db_session, fake_openai
    ):
        device_id = _device_id()
        job = RecipeJob(id="job-guest-done", device_id=device_id, status="pending",
                         job_type="generate", prompt="creamy chicken pasta", progress=0,
                         preferences={"groceryCategories": ["produce", "dry-goods", "pantry"]})
        db_session.add(job)
        db_session.commit()

        await job_service._process_generation_job("job-guest-done")

        status_response = client.get(
            "/api/jobs/recipes/job-guest-done/status", headers={"X-Device-Id": device_id}
        )
        assert status_response.json()["status"] == "completed"

        result_response = client.get(
            "/api/jobs/recipes/job-guest-done/result", headers={"X-Device-Id": device_id}
        )
        assert result_response.status_code == 200, result_response.text
        body = result_response.json()
        assert body["recipe_id"] is None
        assert body["recipe"]["title"] == "Creamy Chicken Pasta"
        assert len(body["ingredients"]) == 5


class TestUnresolvableUserFailsCleanly:
    """Covers the task-12 fix: a job whose user_id was set but the user
    can't be resolved (e.g. account deleted mid-job) must be marked
    "failed", not left stuck in "pending" forever.
    """

    async def test_job_with_unresolvable_user_id_marked_failed(self, db_session):
        job = RecipeJob(id="job-ghost-user", user_id=999999, status="pending",
                         job_type="generate", prompt="x", progress=0)
        db_session.add(job)
        db_session.commit()

        await job_service._process_generation_job("job-ghost-user")

        db_session.expire_all()
        refreshed = db_session.query(RecipeJob).filter_by(id="job-ghost-user").first()
        assert refreshed.status == "failed"
        assert refreshed.error_message
