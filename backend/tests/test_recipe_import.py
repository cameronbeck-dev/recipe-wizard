"""Tests for POST /api/recipes/import — guest -> account graduation."""


def _recipe_payload(title="Guest Pasta", **overrides):
    payload = {
        "recipe": {
            "title": title,
            "description": "A guest-generated recipe",
            "instructions": ["Boil water", "Cook pasta"],
            "prepTime": 10,
            "cookTime": 15,
            "servings": 2,
            "difficulty": "easy",
            "tips": [],
        },
        "ingredients": [
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ],
        "userPrompt": "quick pasta",
    }
    payload.update(overrides)
    return payload


class TestImportHappyPath:
    def test_imports_multiple_recipes(self, client, auth_headers):
        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("Guest Pasta"), _recipe_payload("Guest Tacos")]},
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"imported": 2, "skipped": 0}

    def test_imported_recipes_appear_in_saved_list(self, client, auth_headers):
        client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("Guest Pasta")]},
        )
        listing = client.get("/api/recipes/saved", headers=auth_headers)
        titles = [r["recipe"]["title"] for r in listing.json()["recipes"]]
        assert "Guest Pasta" in titles

    def test_empty_list_returns_zero_counts(self, client, auth_headers):
        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": []},
        )
        assert response.status_code == 200
        assert response.json() == {"imported": 0, "skipped": 0}


class TestImportValidation:
    def test_over_cap_list_rejected(self, client, auth_headers):
        recipes = [_recipe_payload(f"Recipe {i}") for i in range(101)]
        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": recipes},
        )
        assert response.status_code == 422

    def test_unauthenticated_request_rejected(self, client):
        response = client.post(
            "/api/recipes/import",
            json={"recipes": [_recipe_payload()]},
        )
        assert response.status_code == 401


class TestImportDedupe:
    def test_existing_saved_title_on_account_is_skipped(
        self, client, auth_headers, recipe_factory, user, db_session
    ):
        from app.models import SavedRecipe

        existing = recipe_factory(owner=user, title="Existing Recipe")
        db_session.add(SavedRecipe(user_id=user.id, recipe_id=existing.id))
        db_session.commit()

        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("existing recipe")]},  # different case/whitespace
        )
        assert response.status_code == 200, response.text
        assert response.json() == {"imported": 0, "skipped": 1}

        from app.models import Recipe
        matches = db_session.query(Recipe).filter(Recipe.title == "Existing Recipe").all()
        assert len(matches) == 1  # no duplicate row created

    def test_previously_imported_title_is_skipped_on_second_import(self, client, auth_headers):
        client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("Repeat Recipe")]},
        )
        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("repeat recipe  ")]},
        )
        assert response.json() == {"imported": 0, "skipped": 1}

    def test_duplicate_titles_within_single_request_import_once(self, client, auth_headers):
        response = client.post(
            "/api/recipes/import",
            headers=auth_headers,
            json={"recipes": [_recipe_payload("Same Title"), _recipe_payload("same title")]},
        )
        assert response.json() == {"imported": 1, "skipped": 1}

        listing = client.get("/api/recipes/saved", headers=auth_headers)
        titles = [r["recipe"]["title"] for r in listing.json()["recipes"]]
        assert titles.count("Same Title") == 1
