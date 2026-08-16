"""Tests for /api/shopping-list and the underlying ShoppingListService.

Replaces the old root-level smoke script (backend/test_shopping_list.py) with
real coverage of the consolidation logic.
"""
import pytest

from app.services.shopping_list_service import ShoppingListService


# ---------------------------------------------------------------------------
# Router tests
# ---------------------------------------------------------------------------
class TestShoppingListEndpoints:
    def test_get_empty_list(self, client, auth_headers):
        response = client.get("/api/shopping-list/", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["items"] == []

    def test_get_no_trailing_slash_alias(self, client, auth_headers):
        response = client.get("/api/shopping-list", headers=auth_headers)
        assert response.status_code == 200
        assert "items" in response.json()

    def test_add_recipe_populates_items(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        response = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        names = sorted(item["ingredientName"] for item in body["items"])
        assert names == ["Pasta", "Tomato"]

    def test_add_recipe_camelcase_or_snake_case(self, client, auth_headers, recipe_factory, user):
        """The mobile app sends camelCase; the schema accepts both."""
        recipe = recipe_factory(owner=user)
        response = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipe_id": str(recipe.id)},
        )
        assert response.status_code == 200

    def test_add_unknown_recipe(self, client, auth_headers):
        response = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": "99999"},
        )
        assert response.status_code == 400

    def test_check_off_item(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        item_id = added["items"][0]["id"]

        response = client.put(
            f"/api/shopping-list/items/{item_id}",
            headers=auth_headers,
            json={"itemId": item_id, "isChecked": True},
        )
        assert response.status_code == 200
        assert response.json()["item"]["isChecked"] is True

    def test_check_off_unknown_item(self, client, auth_headers):
        response = client.put(
            "/api/shopping-list/items/99999",
            headers=auth_headers,
            json={"itemId": "99999", "isChecked": True},
        )
        assert response.status_code == 404

    def test_clear_list(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        response = client.delete("/api/shopping-list/clear", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["success"] is True

        empty = client.get("/api/shopping-list/", headers=auth_headers).json()
        assert empty["items"] == []

    def test_remove_recipe_only_removes_its_contribution(
        self, client, auth_headers, recipe_factory, user,
    ):
        r1 = recipe_factory(owner=user, title="Tomato Pasta", ingredients=[
            {"name": "Tomato", "amount": "2", "unit": "", "category": "produce"},
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        r2 = recipe_factory(owner=user, title="Tomato Salad", ingredients=[
            {"name": "Tomato", "amount": "3", "unit": "", "category": "produce"},
        ])
        for r in (r1, r2):
            client.post(
                "/api/shopping-list/add-recipe",
                headers=auth_headers,
                json={"recipeId": str(r.id)},
            )

        # Tomato should be present once (consolidated across both recipes).
        body = client.get("/api/shopping-list/", headers=auth_headers).json()
        tomato = next(i for i in body["items"] if i["ingredientName"] == "Tomato")
        assert len(tomato["recipeBreakdown"]) == 2

        # Removing r2 should leave Tomato (from r1) and Pasta — but only r1's slice of Tomato.
        response = client.delete(f"/api/shopping-list/recipes/{r2.id}", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        tomato = next(i for i in body["items"] if i["ingredientName"] == "Tomato")
        assert len(tomato["recipeBreakdown"]) == 1
        assert tomato["recipeBreakdown"][0]["recipeTitle"] == "Tomato Pasta"

    def test_remove_unknown_recipe(self, client, auth_headers):
        response = client.delete("/api/shopping-list/recipes/99999", headers=auth_headers)
        assert response.status_code == 404

    def test_endpoints_require_auth(self, client):
        for path, method, kwargs in [
            ("/api/shopping-list/", "get", {}),
            ("/api/shopping-list/clear", "delete", {}),
            ("/api/shopping-list/recipes", "get", {}),
            ("/api/shopping-list/checked", "delete", {}),
            ("/api/shopping-list/items/1", "delete", {}),
            ("/api/shopping-list/items/1/quantity", "patch", {"json": {"quantity": "1"}}),
            ("/api/shopping-list/items", "post", {"json": {"ingredientName": "Test"}}),
        ]:
            r = getattr(client, method)(path, **kwargs)
            assert r.status_code == 401, f"{method.upper()} {path}"


class TestDuplicateRecipeGuard:
    def test_duplicate_add_returns_409(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        response = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        assert response.status_code == 409
        assert response.json()["code"] == "recipe_already_added"

    def test_duplicate_add_with_allow_duplicate_succeeds(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user, ingredients=[
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        response = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id), "allowDuplicate": True},
        )
        assert response.status_code == 200
        pasta = next(i for i in response.json()["items"] if i["ingredientName"] == "Pasta")
        assert pasta["consolidatedDisplay"] == "400 g"


class TestNewShoppingListEndpoints:
    def test_get_recipes_lists_contributing_recipes(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user, title="Tomato Pasta")
        client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        )
        response = client.get("/api/shopping-list/recipes", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert len(body) == 1
        assert body[0]["recipeId"] == str(recipe.id)
        assert body[0]["recipeTitle"] == "Tomato Pasta"

    def test_clear_checked_items_leaves_unchecked(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        items = added["items"]
        checked_item = items[0]
        client.put(
            f"/api/shopping-list/items/{checked_item['id']}",
            headers=auth_headers,
            json={"itemId": checked_item["id"], "isChecked": True},
        )

        response = client.delete("/api/shopping-list/checked", headers=auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["removedCount"] == 1
        remaining_names = [i["ingredientName"] for i in body["items"]]
        assert checked_item["ingredientName"] not in remaining_names

        # The recipe association should be pruned once no breakdowns remain for it
        recipes = client.get("/api/shopping-list/recipes", headers=auth_headers).json()
        remaining_ingredient_names = [i["ingredientName"] for i in body["items"]]
        if not remaining_ingredient_names:
            assert recipes == []

    def test_delete_item_removes_it(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user)
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        item_id = added["items"][0]["id"]

        response = client.delete(f"/api/shopping-list/items/{item_id}", headers=auth_headers)
        assert response.status_code == 200
        names = [i["ingredientName"] for i in response.json()["items"]]
        assert added["items"][0]["ingredientName"] not in names

    def test_delete_item_404_for_other_users_item(
        self, client, auth_headers, auth_headers_for, user, user_factory, recipe_factory
    ):
        recipe = recipe_factory(owner=user)
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        item_id = added["items"][0]["id"]

        other_user = user_factory()
        other_headers = auth_headers_for(other_user)

        response = client.delete(f"/api/shopping-list/items/{item_id}", headers=other_headers)
        assert response.status_code == 404

    def test_set_and_clear_quantity_override(self, client, auth_headers, recipe_factory, user):
        recipe = recipe_factory(owner=user, ingredients=[
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        item_id = added["items"][0]["id"]

        response = client.patch(
            f"/api/shopping-list/items/{item_id}/quantity",
            headers=auth_headers,
            json={"quantity": "1 bag"},
        )
        assert response.status_code == 200
        item = response.json()["item"]
        assert item["consolidatedDisplay"] == "1 bag"
        assert item["userQuantityOverride"] == "1 bag"
        assert item["overrideIsStale"] is False

        response = client.patch(
            f"/api/shopping-list/items/{item_id}/quantity",
            headers=auth_headers,
            json={"quantity": None},
        )
        assert response.status_code == 200
        item = response.json()["item"]
        assert item["userQuantityOverride"] is None
        assert item["consolidatedDisplay"] == "200 g"

    def test_override_flips_stale_on_new_recipe_contribution(self, client, auth_headers, recipe_factory, user):
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
        ])
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(r1.id)},
        ).json()
        item_id = added["items"][0]["id"]

        client.patch(
            f"/api/shopping-list/items/{item_id}/quantity",
            headers=auth_headers,
            json={"quantity": "1 bag"},
        )

        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(r2.id)},
        ).json()
        pasta = next(i for i in added["items"] if i["ingredientName"] == "Pasta")
        assert pasta["overrideIsStale"] is True
        assert pasta["autoConsolidatedDisplay"] == "500 g"
        assert pasta["consolidatedDisplay"] == "1 bag"

    def test_manual_item_add_and_merge(self, client, auth_headers, user):
        response = client.post(
            "/api/shopping-list/items",
            headers=auth_headers,
            json={"ingredientName": "Paper Towels", "quantity": "1 roll", "category": "household"},
        )
        assert response.status_code == 200
        item = response.json()["item"]
        assert item["source"] == "manual"
        assert item["consolidatedDisplay"] == "1 roll"

        response = client.post(
            "/api/shopping-list/items",
            headers=auth_headers,
            json={"ingredientName": "Paper Towels", "quantity": "2 rolls", "category": "household"},
        )
        assert response.status_code == 200
        merged = response.json()["item"]
        assert merged["id"] == item["id"]

    def test_manual_item_survives_recipe_removal_after_merge(self, client, auth_headers, recipe_factory, user):
        """A manual item that later gets a recipe merged into it must survive
        removal of that recipe, because it still holds manual quantity data."""
        manual = client.post(
            "/api/shopping-list/items",
            headers=auth_headers,
            json={"ingredientName": "Anchovies", "quantity": "1 tin", "category": "chilled"},
        ).json()["item"]

        recipe = recipe_factory(owner=user, ingredients=[
            {"name": "Anchovies", "amount": "5", "unit": "", "category": "chilled"},
        ])
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        anchovy_item = next(i for i in added["items"] if i["ingredientName"] == "Anchovies")
        assert anchovy_item["id"] == manual["id"]
        assert len(anchovy_item["recipeBreakdown"]) == 1

        response = client.delete(f"/api/shopping-list/recipes/{recipe.id}", headers=auth_headers)
        assert response.status_code == 200
        names = [i["ingredientName"] for i in response.json()["items"]]
        assert "Anchovies" in names

    def test_recipe_ingredient_merges_into_manual_item_and_sums(self, client, auth_headers, recipe_factory, user):
        client.post(
            "/api/shopping-list/items",
            headers=auth_headers,
            json={"ingredientName": "Pasta", "quantity": "100 g", "category": "dry-goods"},
        )
        recipe = recipe_factory(owner=user, ingredients=[
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        added = client.post(
            "/api/shopping-list/add-recipe",
            headers=auth_headers,
            json={"recipeId": str(recipe.id)},
        ).json()
        pasta = next(i for i in added["items"] if i["ingredientName"] == "Pasta")
        assert pasta["consolidatedDisplay"] == "300 g"


# ---------------------------------------------------------------------------
# ShoppingListService — direct unit tests of the consolidation logic
# ---------------------------------------------------------------------------
class TestConsolidation:
    def test_two_recipes_same_ingredient_same_unit_sums(self, db_session, user, recipe_factory):
        """Two recipes call for "200 g pasta" + "300 g pasta" → "500 g"."""
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Pasta", "amount": "200", "unit": "g", "category": "dry-goods"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
        ])

        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(user.id, r2.id)

        pasta = next(i for i in result.items if i.ingredient_name == "Pasta")
        assert pasta.consolidated_display == "500 g"
        assert len(pasta.recipe_breakdown) == 2

    def test_mixed_compatible_volume_units_are_converted_and_summed(self, db_session, user, recipe_factory):
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Olive Oil", "amount": "2", "unit": "tbsp", "category": "pantry"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Olive Oil", "amount": "60", "unit": "ml", "category": "pantry"},
        ])

        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(user.id, r2.id)

        oil = next(i for i in result.items if i.ingredient_name == "Olive Oil")
        # tbsp and ml are compatible (both volume) — should be combined into a
        # single display, not concatenated with "+"
        assert "+" not in oil.consolidated_display

    def test_incompatible_units_fall_back_to_concatenation(self, db_session, user, recipe_factory):
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Garlic", "amount": "2", "unit": "cloves", "category": "produce"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Garlic", "amount": "1", "unit": "tsp", "category": "produce"},
        ])

        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(user.id, r2.id)

        garlic = next(i for i in result.items if i.ingredient_name == "Garlic")
        # cloves (dimensionless) and tsp (volume) are NOT compatible
        assert "+" in garlic.consolidated_display

    def test_to_taste_amount_is_preserved(self, db_session, user, recipe_factory):
        r = recipe_factory(owner=user, ingredients=[
            {"name": "Salt", "amount": "to taste", "unit": "N/A", "category": "spices"},
        ])
        svc = ShoppingListService(db_session)
        result = svc.add_recipe_to_shopping_list(user.id, r.id)
        salt = next(i for i in result.items if i.ingredient_name == "Salt")
        assert salt.consolidated_display == "to taste"

    def test_to_taste_mixed_with_real_quantity_falls_back_to_concatenation(self, db_session, user, recipe_factory):
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Pepper", "amount": "to taste", "unit": "N/A", "category": "spices"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Pepper", "amount": "1", "unit": "tsp", "category": "spices"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(user.id, r2.id)
        pepper = next(i for i in result.items if i.ingredient_name == "Pepper")
        assert "to taste" in pepper.consolidated_display
        assert "+" in pepper.consolidated_display

    def test_weight_conversion_steps_to_kg_in_metric(self, db_session, user, recipe_factory):
        r1 = recipe_factory(owner=user, title="A", ingredients=[
            {"name": "Flour", "amount": "600", "unit": "g", "category": "dry-goods"},
        ])
        r2 = recipe_factory(owner=user, title="B", ingredients=[
            {"name": "Flour", "amount": "500", "unit": "g", "category": "dry-goods"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(user.id, r2.id)
        flour = next(i for i in result.items if i.ingredient_name == "Flour")
        assert flour.consolidated_display == "1.1 kg"

    def test_weight_conversion_steps_to_lb_in_imperial(self, db_session, user_factory, recipe_factory):
        imperial_user = user_factory(units="imperial")
        r1 = recipe_factory(owner=imperial_user, title="A", ingredients=[
            {"name": "Beef", "amount": "300", "unit": "g", "category": "butchery"},
        ])
        r2 = recipe_factory(owner=imperial_user, title="B", ingredients=[
            {"name": "Beef", "amount": "300", "unit": "g", "category": "butchery"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(imperial_user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(imperial_user.id, r2.id)
        beef = next(i for i in result.items if i.ingredient_name == "Beef")
        assert beef.consolidated_display.endswith("lb")

    def test_volume_conversion_in_imperial_uses_cup(self, db_session, user_factory, recipe_factory):
        imperial_user = user_factory(units="imperial")
        r1 = recipe_factory(owner=imperial_user, title="A", ingredients=[
            {"name": "Milk", "amount": "200", "unit": "ml", "category": "chilled"},
        ])
        r2 = recipe_factory(owner=imperial_user, title="B", ingredients=[
            {"name": "Milk", "amount": "200", "unit": "ml", "category": "chilled"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(imperial_user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(imperial_user.id, r2.id)
        milk = next(i for i in result.items if i.ingredient_name == "Milk")
        assert milk.consolidated_display.endswith("cup")

    def test_fraction_quantities_are_parsed_and_summed(self, db_session, user_factory, recipe_factory):
        imperial_user = user_factory(units="imperial")
        r1 = recipe_factory(owner=imperial_user, title="A", ingredients=[
            {"name": "Butter", "amount": "1/2", "unit": "cup", "category": "chilled"},
        ])
        r2 = recipe_factory(owner=imperial_user, title="B", ingredients=[
            {"name": "Butter", "amount": "1/2", "unit": "cup", "category": "chilled"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(imperial_user.id, r1.id)
        result = svc.add_recipe_to_shopping_list(imperial_user.id, r2.id)
        butter = next(i for i in result.items if i.ingredient_name == "Butter")
        assert butter.consolidated_display == "1 cup"

    def test_ingredients_in_different_categories_stay_separate(self, db_session, user, recipe_factory):
        """Same name + different category should NOT consolidate (e.g. fresh vs dried)."""
        r = recipe_factory(owner=user, ingredients=[
            {"name": "Basil", "amount": "1", "unit": "bunch", "category": "produce"},
            {"name": "Basil", "amount": "1", "unit": "tbsp", "category": "spices"},
        ])
        svc = ShoppingListService(db_session)
        result = svc.add_recipe_to_shopping_list(user.id, r.id)
        basil_items = [i for i in result.items if i.ingredient_name == "Basil"]
        assert len(basil_items) == 2

    def test_clear_removes_everything(self, db_session, user, recipe_factory):
        r = recipe_factory(owner=user)
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r.id)
        assert svc.clear_shopping_list(user.id) is True

        from app.models import ShoppingListItem, ShoppingListRecipeAssociation
        assert db_session.query(ShoppingListItem).count() == 0
        assert db_session.query(ShoppingListRecipeAssociation).count() == 0

    def test_remove_recipe_when_only_source_deletes_item(self, db_session, user, recipe_factory):
        r = recipe_factory(owner=user, ingredients=[
            {"name": "Anchovies", "amount": "5", "unit": "", "category": "chilled"},
        ])
        svc = ShoppingListService(db_session)
        svc.add_recipe_to_shopping_list(user.id, r.id)
        result = svc.remove_recipe_from_shopping_list(user.id, r.id)
        names = [i.ingredient_name for i in result.items]
        assert "Anchovies" not in names
