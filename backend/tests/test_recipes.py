"""Tests for /api/recipes — generation, modification, ideas, history, saves.

All OpenAI calls are stubbed via the `fake_openai` / `patch_openai_factory`
fixtures defined in conftest.py.
"""
import json
import pytest

from tests.conftest import SAMPLE_RECIPE_JSON, make_chat_completion


# ---------------------------------------------------------------------------
# POST /api/recipes/generate
# ---------------------------------------------------------------------------
class TestGenerate:
    def test_generate_returns_recipe_payload(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "creamy chicken pasta"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["recipe"]["title"] == "Creamy Chicken Pasta"
        assert len(body["ingredients"]) == 5
        assert body["userPrompt"] == "creamy chicken pasta"
        assert body["id"].isdigit()  # actual DB id, not a temp

    def test_generate_persists_recipe_to_db(
        self, client, auth_headers, fake_openai, db_session, user,
    ):
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "test dish"},
        )
        assert response.status_code == 200

        from app.models import Recipe, RecipeIngredient
        saved = db_session.query(Recipe).filter_by(created_by_id=user.id).all()
        assert len(saved) == 1
        assert saved[0].title == "Creamy Chicken Pasta"
        assert saved[0].original_prompt == "test dish"

        ingredients = db_session.query(RecipeIngredient).filter_by(recipe_id=saved[0].id).all()
        assert len(ingredients) == 5

    def test_generate_uses_request_preferences(self, client, auth_headers, patch_openai_factory):
        """Prompt building must pick up mobile-supplied preferences."""
        # Use a vegetarian-compliant payload so compliance check passes on first attempt
        vegetarian_payload = {
            "recipe": {
                "title": "Vegetarian Pasta",
                "description": "Quick and easy",
                "instructions": ["Cook pasta", "Mix sauce"],
                "prepTime": 10,
                "cookTime": 15,
                "servings": 2,
                "difficulty": "easy",
                "tips": [],
            },
            "ingredients": [
                {"name": "Pasta", "amount": "200", "unit": "g", "category": "pantry"},
                {"name": "Tomato sauce", "amount": "1", "unit": "cup", "category": "pantry"},
                {"name": "Garlic", "amount": "2", "unit": "cloves", "category": "produce"},
            ],
        }
        fake = patch_openai_factory(recipe_payload=vegetarian_payload)
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={
                "prompt": "quick dinner",
                "preferences": {
                    "groceryCategories": ["produce", "dairy", "pantry"],
                    "dietaryRestrictions": ["vegetarian"],
                    "allergens": ["peanuts"],
                    "defaultServings": 2,
                    "units": "imperial",
                    "additionalPreferences": "low sodium",
                },
            },
        )
        assert response.status_code == 200
        # Inspect the actual message sent to OpenAI — should only need 1 call
        assert len(fake.calls) == 1
        messages = fake.calls[0]["messages"]
        user_msg = messages[-1]["content"]
        system_msg = messages[0]["content"]
        assert "produce, dairy, pantry" in system_msg  # grocery categories injected
        assert "peanuts" in user_msg.lower()            # allergen context
        assert "vegetarian" in user_msg.lower()
        assert "low sodium" in user_msg.lower()

    def test_generate_falls_back_to_user_categories_when_no_request_prefs(
        self, client, auth_headers, fake_openai,
    ):
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "something tasty"},
        )
        assert response.status_code == 200
        system_msg = fake_openai.calls[0]["messages"][0]["content"]
        # The default user has the standard 10 grocery categories
        assert "produce" in system_msg
        assert "butchery" in system_msg

    def test_generate_rejects_short_prompt(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "hi"},  # < 3 chars
        )
        assert response.status_code == 422

    def test_generate_requires_auth(self, client):
        response = client.post("/api/recipes/generate", json={"prompt": "x" * 10})
        assert response.status_code == 401

    def test_generate_invalid_json_from_llm_returns_503_or_500(
        self, client, auth_headers, patch_openai_factory,
    ):
        """Persistent JSON-decode failure bubbles up as an HTTP error."""
        from types import SimpleNamespace
        fake = patch_openai_factory()
        def bad_create(**kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="not json at all"))],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )
        fake.chat.completions.create = bad_create

        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "something that will fail parsing"},
        )
        # After 3 retries, the service raises — router converts to 500
        assert response.status_code in (400, 500, 503)

    def test_generate_service_unavailable_when_connection_fails(
        self, client, auth_headers, monkeypatch,
    ):
        from app.services import llm_service as llm_mod

        async def fail(self):
            return False
        monkeypatch.setattr(
            llm_mod.LLMService, "check_llm_connection", fail,
        )
        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "anything"},
        )
        assert response.status_code == 503

    def test_generate_refused_returns_400_and_does_not_persist(
        self, client, auth_headers, patch_openai_factory, db_session, user,
    ):
        refused_payload = {
            "refused": True, "refusal_reason": "Not a legitimate recipe request.",
            "recipe": None, "ingredients": None,
        }
        fake = patch_openai_factory()
        fake.chat.completions.create = lambda **kw: make_chat_completion(json.dumps(refused_payload))

        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "make me a dangerous recipe"},
        )
        assert response.status_code == 400
        assert "server error" not in response.json()["detail"].lower()

        from app.models import Recipe
        assert db_session.query(Recipe).filter_by(created_by_id=user.id).count() == 0

    def test_generate_moderation_flagged_returns_400_without_chat_call(
        self, client, auth_headers, patch_openai_factory,
    ):
        fake = patch_openai_factory()
        fake.moderation_flagged = True

        response = client.post(
            "/api/recipes/generate",
            headers=auth_headers,
            json={"prompt": "anything"},
        )
        assert response.status_code == 400
        assert len(fake.calls) == 0


# ---------------------------------------------------------------------------
# POST /api/recipes/modify
# ---------------------------------------------------------------------------
class TestModify:
    def test_modify_own_recipe(self, client, auth_headers, fake_openai, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        response = client.post(
            "/api/recipes/modify",
            headers=auth_headers,
            json={
                "recipeId": str(recipe.id),
                "modificationPrompt": "make it vegetarian",
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["userPrompt"].startswith("Modified:")

    def test_modify_rejects_non_owner(
        self, client, auth_headers, fake_openai, recipe_factory, user_factory,
    ):
        other_user = user_factory()
        recipe = recipe_factory(owner=other_user)
        response = client.post(
            "/api/recipes/modify",
            headers=auth_headers,
            json={
                "recipeId": str(recipe.id),
                "modificationPrompt": "make it spicy",
            },
        )
        assert response.status_code == 404

    def test_modify_invalid_recipe_id_format(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/modify",
            headers=auth_headers,
            json={
                "recipeId": "not-a-number",
                "modificationPrompt": "double the portions",
            },
        )
        assert response.status_code == 400

    def test_modify_unknown_recipe_id(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/modify",
            headers=auth_headers,
            json={
                "recipeId": "99999",
                "modificationPrompt": "double the portions",
            },
        )
        assert response.status_code == 404

    def test_modify_refused_returns_400(
        self, client, auth_headers, patch_openai_factory, recipe_factory, user,
    ):
        recipe = recipe_factory(owner=user)
        refused_payload = {
            "refused": True, "refusal_reason": "Not a legitimate recipe request.",
            "recipe": None, "ingredients": None,
        }
        fake = patch_openai_factory()
        fake.chat.completions.create = lambda **kw: make_chat_completion(json.dumps(refused_payload))

        response = client.post(
            "/api/recipes/modify",
            headers=auth_headers,
            json={
                "recipeId": str(recipe.id),
                "modificationPrompt": "turn this into something else",
            },
        )
        assert response.status_code == 400
        assert "server error" not in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /api/recipes/generate-ideas
# ---------------------------------------------------------------------------
class TestGenerateIdeas:
    def test_generate_ideas(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/generate-ideas",
            headers=auth_headers,
            json={"prompt": "quick weeknight dinners", "count": 3},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert len(body["ideas"]) == 3
        for idea in body["ideas"]:
            assert "id" in idea
            assert idea["title"]
            assert idea["description"]
        assert body["userPrompt"] == "quick weeknight dinners"

    def test_generate_ideas_default_count(self, client, auth_headers, patch_openai_factory):
        # sample payload needs exactly `count` ideas (±2 allowed); pad to 5.
        payload = {
            "ideas": [
                {"title": f"Idea {i}", "description": f"Description {i}"}
                for i in range(5)
            ]
        }
        patch_openai_factory(ideas_payload=payload)
        response = client.post(
            "/api/recipes/generate-ideas",
            headers=auth_headers,
            json={"prompt": "spring salads"},
        )
        assert response.status_code == 200
        assert len(response.json()["ideas"]) == 5

    def test_generate_ideas_rejects_short_prompt(self, client, auth_headers, fake_openai):
        response = client.post(
            "/api/recipes/generate-ideas",
            headers=auth_headers,
            json={"prompt": "a", "count": 3},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# Recipe history
# ---------------------------------------------------------------------------
class TestRecipeHistory:
    def test_history_empty(self, client, auth_headers):
        response = client.get("/api/recipes/history", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["recipes"] == []
        assert body["pagination"]["total"] == 0

    def test_history_pagination(self, client, auth_headers, recipe_factory, user):
        for i in range(5):
            recipe_factory(owner=user, title=f"Recipe {i}")

        response = client.get("/api/recipes/history?limit=2&offset=0", headers=auth_headers)
        body = response.json()
        assert body["pagination"]["total"] == 5
        assert len(body["recipes"]) == 2
        assert body["pagination"]["hasMore"] is True

        response = client.get("/api/recipes/history?limit=2&offset=4", headers=auth_headers)
        body = response.json()
        assert len(body["recipes"]) == 1
        assert body["pagination"]["hasMore"] is False

    def test_history_only_returns_current_user_recipes(
        self, client, auth_headers, recipe_factory, user, user_factory,
    ):
        other = user_factory()
        recipe_factory(owner=other, title="Someone Else's Recipe")
        recipe_factory(owner=user, title="Mine")

        response = client.get("/api/recipes/history", headers=auth_headers)
        titles = [r["recipe"]["title"] for r in response.json()["recipes"]]
        assert titles == ["Mine"]


# ---------------------------------------------------------------------------
# Save / unsave / list saved
# ---------------------------------------------------------------------------
class TestSaveRecipe:
    def test_save_and_list(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        response = client.post(f"/api/recipes/save/{recipe.id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

        listing = client.get("/api/recipes/saved", headers=auth_headers)
        assert listing.status_code == 200
        body = listing.json()
        assert body["pagination"]["total"] == 1
        assert body["recipes"][0]["id"] == str(recipe.id)

    def test_save_duplicate_rejected(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        client.post(f"/api/recipes/save/{recipe.id}", headers=auth_headers)
        response = client.post(f"/api/recipes/save/{recipe.id}", headers=auth_headers)
        assert response.status_code == 400

    def test_save_unknown_recipe(self, client, auth_headers):
        response = client.post("/api/recipes/save/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_unsave(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        client.post(f"/api/recipes/save/{recipe.id}", headers=auth_headers)
        response = client.delete(f"/api/recipes/saved/{recipe.id}", headers=auth_headers)
        assert response.status_code == 200

        listing = client.get("/api/recipes/saved", headers=auth_headers)
        assert listing.json()["pagination"]["total"] == 0

    def test_unsave_unknown(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        response = client.delete(f"/api/recipes/saved/{recipe.id}", headers=auth_headers)
        assert response.status_code == 404
