"""
Shared pytest fixtures for the Recipe Wizard backend test suite.

Boots the app against an in-memory SQLite database, overrides the
`get_db` dependency, and provides helpers for creating users, recipes,
authenticated requests, and stubbing out the OpenAI client so no real
network calls are made unless explicitly opted in (live_openai marker).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterator, List, Optional

import pytest

# ---------------------------------------------------------------------------
# Environment setup MUST happen before importing the app (auth + openai
# services validate required env vars at import time).
# ---------------------------------------------------------------------------
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production-use-only")
os.environ.setdefault("ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key")
os.environ.setdefault("DEFAULT_MODEL_FREE", "gpt-5.6-luna")
os.environ.setdefault("DEFAULT_MODEL_PAID", "gpt-5.6-terra")
# Hard-clear (not setdefault): a developer's local backend/.env may set a real
# DEFAULT_MODEL for local runs. openai_service.py calls load_dotenv() at import
# time, and dotenv never overrides an already-present env var — pre-setting
# this to "" keeps tests hermetic regardless of local .env contents.
os.environ["DEFAULT_MODEL"] = ""
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("ENABLE_RATE_LIMIT", "false")
os.environ.setdefault("REVENUECAT_WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("REVENUECAT_ALLOW_SANDBOX", "true")
os.environ.pop("REDIS_URL", None)
os.environ.pop("ALLOWED_ORIGINS", None)

# Make `app` importable when tests are run from the backend/ directory.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app import database as app_database  # noqa: E402
from app.database import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, User, Recipe, RecipeIngredient  # noqa: E402
from app.utils.auth import AuthUtils, create_access_token_for_user  # noqa: E402


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def _engine():
    """One in-memory SQLite engine for the whole test session.

    StaticPool keeps a single connection alive so every session/thread sees
    the same in-memory database (ordinary SQLite memory DBs are per-conn).
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def _SessionLocal(_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=_engine)


@pytest.fixture(autouse=True)
def _reset_database(_engine, _SessionLocal, monkeypatch):
    """Wipe all tables between tests AND repoint the app's global
    `SessionLocal` at the in-memory engine so non-DI consumers (e.g. the
    background job_service that calls `get_db()` directly) hit the same DB.
    """
    Base.metadata.drop_all(bind=_engine)
    Base.metadata.create_all(bind=_engine)
    monkeypatch.setattr(app_database, "SessionLocal", _SessionLocal)
    monkeypatch.setattr(app_database, "engine", _engine)
    yield


@pytest.fixture
def db_session(_SessionLocal):
    """Direct DB session for arrange-phase setup in tests."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# FastAPI client + dependency overrides
# ---------------------------------------------------------------------------
@pytest.fixture
def client(_SessionLocal) -> Iterator[TestClient]:
    """TestClient with `get_db` overridden to use the in-memory engine.

    NOTE: We deliberately do *not* enter TestClient as a context manager so
    the FastAPI startup events (which try to connect to Redis and init the
    real database) never run.
    """
    def override_get_db():
        session = _SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------
# User + auth helpers
# ---------------------------------------------------------------------------
DEFAULT_PASSWORD = "TestPassword123!"


@pytest.fixture
def user_factory(db_session) -> Callable[..., User]:
    """Create users directly in the DB. Returns a callable factory."""
    counter = {"i": 0}

    def _make(
        email: Optional[str] = None,
        password: str = DEFAULT_PASSWORD,
        username: Optional[str] = None,
        **kwargs: Any,
    ) -> User:
        counter["i"] += 1
        i = counter["i"]
        email = email or f"user{i}@example.com"
        username = username or f"user{i}"
        user = AuthUtils.create_user(
            db=db_session,
            email=email,
            password=password,
            username=username,
            **kwargs,
        )
        return user

    return _make


@pytest.fixture
def user(user_factory) -> User:
    return user_factory()


@pytest.fixture
def auth_headers(user) -> Dict[str, str]:
    """Bearer-token headers for the default `user` fixture."""
    token = create_access_token_for_user(user)["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_for() -> Callable[[User], Dict[str, str]]:
    """Build auth headers for any user."""
    def _make(u: User) -> Dict[str, str]:
        token = create_access_token_for_user(u)["access_token"]
        return {"Authorization": f"Bearer {token}"}
    return _make


# ---------------------------------------------------------------------------
# Recipe helpers
# ---------------------------------------------------------------------------
@pytest.fixture
def recipe_factory(db_session) -> Callable[..., Recipe]:
    """Insert a recipe + ingredients directly. Returns the Recipe object."""
    def _make(
        owner: User,
        title: str = "Test Pasta",
        ingredients: Optional[List[Dict[str, str]]] = None,
        **kwargs: Any,
    ) -> Recipe:
        if ingredients is None:
            ingredients = [
                {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
                {"name": "Tomato", "amount": "2", "unit": "", "category": "produce"},
            ]
        recipe = Recipe(
            title=title,
            description=kwargs.get("description", "A test recipe"),
            instructions=kwargs.get("instructions", ["Boil water", "Cook pasta", "Add sauce"]),
            prep_time=kwargs.get("prep_time", 10),
            cook_time=kwargs.get("cook_time", 20),
            servings=kwargs.get("servings", 4),
            difficulty=kwargs.get("difficulty", "easy"),
            tips=kwargs.get("tips", ["Salt the water"]),
            original_prompt=kwargs.get("original_prompt", "Quick pasta"),
            created_by_id=owner.id,
        )
        db_session.add(recipe)
        db_session.flush()
        for ing in ingredients:
            db_session.add(RecipeIngredient(
                recipe_id=recipe.id,
                name=ing["name"],
                amount=ing["amount"],
                unit=ing.get("unit", ""),
                category=ing.get("category", "pantry"),
            ))
        db_session.commit()
        db_session.refresh(recipe)
        return recipe
    return _make


# ---------------------------------------------------------------------------
# OpenAI mocking
# ---------------------------------------------------------------------------
def make_chat_completion(
    content: Optional[str] = None,
    prompt_tokens: int = 100,
    completion_tokens: int = 200,
    refusal: Optional[str] = None,
):
    """Build a SimpleNamespace shaped like an openai ChatCompletion response.

    Pass `refusal` to simulate the SDK-native refusal channel — `content`
    will be `None` and `message.refusal` will carry the refusal text.
    """
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(
            content=None if refusal else content,
            refusal=refusal,
        ))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
    )


SAMPLE_RECIPE_JSON = {
    "recipe": {
        "title": "Creamy Chicken Pasta",
        "description": "A quick weeknight dinner",
        "instructions": ["Cook pasta", "Sear chicken", "Combine with cream sauce"],
        "prepTime": 10,
        "cookTime": 20,
        "servings": 4,
        "difficulty": "easy",
        "tips": ["Use fresh basil"],
    },
    "ingredients": [
        {"name": "Pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
        {"name": "Chicken Breast", "amount": "400", "unit": "g", "category": "butchery"},
        {"name": "Cream", "amount": "200", "unit": "ml", "category": "chilled"},
        {"name": "Garlic", "amount": "2", "unit": "cloves", "category": "produce"},
        {"name": "Salt", "amount": "to taste", "unit": "N/A", "category": "spices"},
    ],
}


SAMPLE_IDEAS_JSON = {
    "ideas": [
        {"title": "Lemon Herb Chicken", "description": "Bright pan-seared chicken with lemon"},
        {"title": "Garlic Butter Shrimp", "description": "Fast skillet shrimp in garlic butter"},
        {"title": "Tomato Basil Pasta", "description": "Classic comfort with fresh basil"},
    ]
}


class FakeOpenAIClient:
    """A minimal stand-in for the OpenAI client used in tests."""

    def __init__(self, recipe_payload: Optional[Dict] = None, ideas_payload: Optional[Dict] = None):
        self.recipe_payload = recipe_payload if recipe_payload is not None else SAMPLE_RECIPE_JSON
        self.ideas_payload = ideas_payload if ideas_payload is not None else SAMPLE_IDEAS_JSON
        self.calls: List[Dict[str, Any]] = []
        self.moderation_calls: List[Dict[str, Any]] = []
        self.moderation_flagged = False

        chat = SimpleNamespace(completions=SimpleNamespace(create=self._create_chat))
        self.chat = chat
        self.moderations = SimpleNamespace(create=self._create_moderation)

        # `models.list()` is used by check_openai_connection
        self.models = SimpleNamespace(list=lambda: SimpleNamespace(
            data=[SimpleNamespace(id="gpt-4o-mini"), SimpleNamespace(id="gpt-4o")]
        ))

    def _create_moderation(self, **kwargs):
        self.moderation_calls.append(kwargs)
        return SimpleNamespace(results=[SimpleNamespace(flagged=self.moderation_flagged)])

    def _create_chat(self, **kwargs):
        self.calls.append(kwargs)
        messages = kwargs.get("messages", [])
        # Crude routing: ideas prompts use the ideas system prompt
        system = next((m["content"] for m in messages if m.get("role") == "system"), "")
        if "recipe brainstormer" in system or "recipe ideas" in system.lower():
            payload = self.ideas_payload
        else:
            payload = self.recipe_payload
        return make_chat_completion(json.dumps(payload))


@pytest.fixture
def fake_openai(monkeypatch):
    """Replace the global openai client with a FakeOpenAIClient.

    Returns the fake so tests can inspect `.calls` or swap payloads via
    `fake.recipe_payload = {...}` before triggering the route.
    """
    from app.services import openai_service as openai_module
    fake = FakeOpenAIClient()
    monkeypatch.setattr(openai_module.openai_service, "client", fake)
    return fake


@pytest.fixture
def patch_openai_factory(monkeypatch):
    """Like `fake_openai` but lets the test pick the payload up-front."""
    from app.services import openai_service as openai_module

    def _patch(recipe_payload: Optional[Dict] = None, ideas_payload: Optional[Dict] = None) -> FakeOpenAIClient:
        fake = FakeOpenAIClient(recipe_payload=recipe_payload, ideas_payload=ideas_payload)
        monkeypatch.setattr(openai_module.openai_service, "client", fake)
        return fake

    return _patch
