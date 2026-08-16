"""Direct unit tests for the service layer.

Bypasses the HTTP layer to exercise the LLM and OpenAI service helpers
that the routers rely on.
"""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.schemas import RecipeGenerationRequest, RecipeIdeaGenerationRequest
from app.services.llm_service import llm_service, check_llm_service_status
from app.services.openai_service import openai_service, RecipeRequestRefused

from tests.conftest import (
    SAMPLE_IDEAS_JSON, SAMPLE_RECIPE_JSON, FakeOpenAIClient, make_chat_completion,
)


# ---------------------------------------------------------------------------
# OpenAIService — prompt construction & validation
# ---------------------------------------------------------------------------
class TestSystemPromptConstruction:
    def test_recipe_system_prompt_includes_categories(self):
        prompt = openai_service.create_recipe_system_prompt(
            user_categories=["produce", "dairy", "pantry"]
        )
        assert "produce, dairy, pantry" in prompt
        assert "JSON" in prompt

    def test_recipe_system_prompt_requires_categories(self):
        with pytest.raises(ValueError, match="grocery categories"):
            openai_service.create_recipe_system_prompt(user_categories=None)

        with pytest.raises(ValueError, match="grocery categories"):
            openai_service.create_recipe_system_prompt(user_categories=[])

    def test_modification_system_prompt_requires_categories(self):
        with pytest.raises(ValueError, match="grocery categories"):
            openai_service.create_recipe_modification_system_prompt(user_categories=None)

    def test_ideas_system_prompt_does_not_require_categories(self):
        prompt = openai_service.create_recipe_ideas_system_prompt()
        assert "JSON" in prompt
        assert "ideas" in prompt.lower()


class TestPreferenceContextFromRequest:
    def test_compiles_all_preference_fields(self):
        ctx = openai_service._generate_preference_context_from_request({
            "units": "imperial",
            "defaultServings": 2,
            "preferredDifficulty": "easy",
            "maxCookTime": 30,
            "maxPrepTime": 15,
            "dietaryRestrictions": ["vegan"],
            "allergens": ["soy"],
            "dislikes": ["mushrooms"],
            "additionalPreferences": "low sodium please",
        })
        assert "imperial" in ctx
        assert "vegan" in ctx
        assert "soy" in ctx.lower()
        assert "mushrooms" in ctx
        assert "low sodium please" in ctx
        # Additional preferences section present
        assert "Additional preferences" in ctx
        assert ctx.startswith("\n\n## USER PROFILE")

    def test_empty_preferences_returns_empty_string(self):
        assert openai_service._generate_preference_context_from_request({}) == ""


class TestRecipeValidation:
    def test_valid_recipe_passes(self):
        ok, err = openai_service._validate_recipe_data(SAMPLE_RECIPE_JSON)
        assert ok and err == ""

    def test_missing_top_level_keys_fails(self):
        ok, err = openai_service._validate_recipe_data({"recipe": {}})
        assert not ok and err == "format"

    def test_missing_recipe_title_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"instructions": ["x"]},
            "ingredients": [{"name": "x", "amount": "1", "category": "y"}],
        })
        assert not ok and err == "format"

    def test_empty_ingredients_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "x", "instructions": ["y"]},
            "ingredients": [],
        })
        assert not ok and err == "format"

    def test_ingredient_missing_field_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "x", "instructions": ["y"]},
            "ingredients": [{"name": "x"}],  # missing amount + category
        })
        assert not ok and err == "format"


class TestJsonFix:
    def test_strips_markdown_fences(self):
        raw = "```json\n{\"a\":1}\n```"
        assert openai_service._simple_json_fix(raw) == '{"a":1}'

    def test_extracts_json_from_surrounding_text(self):
        raw = "Here you go:\n{\"recipe\": 1}\nEnjoy!"
        assert openai_service._simple_json_fix(raw) == '{"recipe": 1}'

    def test_passthrough_when_already_clean(self):
        raw = '{"a": 1}'
        assert openai_service._simple_json_fix(raw) == raw


class TestIdeasValidation:
    def test_valid_ideas_pass(self):
        ok, err = openai_service._validate_ideas_data(
            {"ideas": [{"title": "T1", "description": "D1"},
                       {"title": "T2", "description": "D2"}]},
            expected_count=2,
        )
        assert ok

    def test_count_far_off_fails(self):
        ok, err = openai_service._validate_ideas_data(
            {"ideas": [{"title": "T", "description": "D"}]},
            expected_count=10,
        )
        assert not ok and err == "count"

    def test_missing_field_fails(self):
        ok, err = openai_service._validate_ideas_data(
            {"ideas": [{"title": "T"}]},
            expected_count=1,
        )
        assert not ok and err == "format"


# ---------------------------------------------------------------------------
# OpenAIService.generate_recipe — end-to-end with mocked client
# ---------------------------------------------------------------------------
class TestGenerateRecipe:
    async def test_happy_path_returns_parsed_recipe(self, monkeypatch, user_factory):
        fake = FakeOpenAIClient()
        monkeypatch.setattr(openai_service, "client", fake)

        user = user_factory()
        request = RecipeGenerationRequest(prompt="creamy pasta")
        result = await openai_service.generate_recipe(request, user)

        assert result["recipe_data"]["recipe"]["title"] == "Creamy Chicken Pasta"
        assert result["model"] == openai_service.default_model
        assert result["retry_count"] == 0

    async def test_retries_then_succeeds(self, monkeypatch, user_factory):
        """First attempt returns invalid JSON; second returns a valid recipe."""
        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return make_chat_completion("not valid json")
            return make_chat_completion(json.dumps(SAMPLE_RECIPE_JSON))

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        user = user_factory()
        request = RecipeGenerationRequest(prompt="any prompt")
        result = await openai_service.generate_recipe(request, user)

        assert attempts["n"] == 2
        assert result["recipe_data"]["recipe"]["title"] == "Creamy Chicken Pasta"
        assert result["retry_count"] == 1

    async def test_all_attempts_invalid_returns_padded_final_attempt(
        self, monkeypatch, user_factory,
    ):
        """If all 3 attempts produce invalid recipes, the service still
        returns the last one with defaults filled in (so the client gets
        *something* rather than a hard 500 from the LLM service itself —
        the router decides what status to return)."""
        bad = {"recipe": {"title": "Just Title"}, "ingredients": [{"name": "x"}]}
        fake = FakeOpenAIClient()
        fake.chat.completions.create = lambda **kw: make_chat_completion(json.dumps(bad))
        monkeypatch.setattr(openai_service, "client", fake)

        result = await openai_service.generate_recipe(
            RecipeGenerationRequest(prompt="anything"), user_factory(),
        )
        # Defaults filled in
        recipe = result["recipe_data"]["recipe"]
        assert recipe["title"] == "Just Title"
        assert recipe.get("instructions") == ["Follow recipe steps"]
        assert recipe.get("difficulty") == "medium"

    async def test_persistent_json_decode_failure_raises(self, monkeypatch, user_factory):
        fake = FakeOpenAIClient()
        fake.chat.completions.create = lambda **kw: make_chat_completion("totally not json")
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RuntimeError):
            await openai_service.generate_recipe(
                RecipeGenerationRequest(prompt="any prompt"), user_factory(),
            )


class TestGenerateIdeas:
    async def test_happy_path_assigns_uuids(self, monkeypatch):
        fake = FakeOpenAIClient()
        monkeypatch.setattr(openai_service, "client", fake)

        result = await openai_service.generate_recipe_ideas(
            "spring salads", count=3, user_preferences=None,
        )
        assert len(result["ideas"]) == 3
        assert all("id" in idea for idea in result["ideas"])
        # IDs should be unique
        assert len({idea["id"] for idea in result["ideas"]}) == 3


# ---------------------------------------------------------------------------
# LLMService — wraps openai_service with a connection pre-check
# ---------------------------------------------------------------------------
class TestLLMService:
    async def test_convert_to_api_response_shapes_payload(self):
        result = llm_service.convert_to_api_response(
            recipe_data=SAMPLE_RECIPE_JSON,
            original_prompt="creamy pasta",
            generation_metadata={"model": "gpt-4o-mini", "generation_time_ms": 100,
                                 "token_count": 200, "prompt_tokens": 100,
                                 "retry_count": 0},
        )
        assert result["recipe"]["title"] == "Creamy Chicken Pasta"
        assert len(result["ingredients"]) == 5
        assert result["userPrompt"] == "creamy pasta"
        # Each ingredient gets a stable position-based id
        assert result["ingredients"][0]["id"] == "0"

    async def test_convert_to_api_response_includes_retry_metadata(self):
        result = llm_service.convert_to_api_response(
            recipe_data=SAMPLE_RECIPE_JSON,
            original_prompt="x",
            generation_metadata={"model": "m", "generation_time_ms": 1,
                                 "token_count": 1, "prompt_tokens": 1,
                                 "retry_count": 2,
                                 "retry_message": "Adjusting the recipe format..."},
        )
        assert result["retryCount"] == 2
        assert result["retryMessage"] == "Adjusting the recipe format..."

    async def test_generate_recipe_with_fallback_propagates_503(self, monkeypatch, user_factory):
        async def fail(self):
            return False
        monkeypatch.setattr(
            llm_service.__class__, "check_llm_connection", fail,
        )
        with pytest.raises(ConnectionError):
            await llm_service.generate_recipe_with_fallback(
                RecipeGenerationRequest(prompt="anything"), user_factory(),
            )

    async def test_check_llm_service_status_connected(self, monkeypatch):
        fake = FakeOpenAIClient()
        monkeypatch.setattr(openai_service, "client", fake)
        status = await check_llm_service_status()
        assert status["status"] == "connected"
        assert status["service"] == "openai"
        assert "default_model" in status

    async def test_check_llm_service_status_disconnected(self, monkeypatch):
        async def fail(self):
            return False
        monkeypatch.setattr(
            llm_service.__class__, "check_llm_connection", fail,
        )
        status = await check_llm_service_status()
        assert status["status"] == "disconnected"


# ---------------------------------------------------------------------------
# _split_preferences
# ---------------------------------------------------------------------------
class TestSplitPreferences:
    def test_separates_hard_and_soft(self):
        split = openai_service._split_preferences({
            "allergens": ["peanut"],
            "dietaryRestrictions": ["vegan"],
            "preferredDifficulty": "easy",
            "defaultServings": 2,
            "maxCookTime": 30,
            "maxPrepTime": 10,
            "units": "metric",
            "dislikes": ["mushrooms"],
            "additionalPreferences": "low sodium",
        })
        assert split["hard_allergens"] == ["peanut"]
        assert split["hard_dietary"] == ["vegan"]
        assert split["soft_difficulty"] == "easy"
        assert split["soft_servings"] == 2
        assert split["soft_max_cook_time"] == 30
        assert split["soft_max_prep_time"] == 10
        assert split["soft_units"] == "metric"
        assert split["soft_dislikes"] == ["mushrooms"]
        assert split["override_notes"] == "low sodium"

    def test_empty_preferences_all_falsy(self):
        split = openai_service._split_preferences({})
        assert split["hard_allergens"] == []
        assert split["hard_dietary"] == []
        assert split["override_notes"] is None

    def test_none_lists_become_empty(self):
        split = openai_service._split_preferences({"allergens": None, "dislikes": None})
        assert split["hard_allergens"] == []
        assert split["soft_dislikes"] == []

    def test_blank_additional_preferences_becomes_none(self):
        split = openai_service._split_preferences({"additionalPreferences": "   "})
        assert split["override_notes"] is None


# ---------------------------------------------------------------------------
# _generate_preference_context_from_request — new structured format
# ---------------------------------------------------------------------------
class TestPreferenceContextStructured:
    def test_hard_constraints_section_present(self):
        ctx = openai_service._generate_preference_context_from_request({
            "allergens": ["peanut"],
            "dietaryRestrictions": ["vegan"],
        })
        assert "Hard constraints" in ctx
        assert "peanut" in ctx
        assert "vegan" in ctx

    def test_override_notes_section_present(self):
        ctx = openai_service._generate_preference_context_from_request({
            "additionalPreferences": "extra spicy please",
        })
        assert "Additional preferences" in ctx
        assert "extra spicy please" in ctx

    def test_soft_preferences_section_present(self):
        ctx = openai_service._generate_preference_context_from_request({
            "units": "imperial",
            "defaultServings": 2,
            "preferredDifficulty": "easy",
            "maxCookTime": 30,
            "dislikes": ["mushrooms"],
        })
        assert "Soft preferences" in ctx
        assert "imperial" in ctx
        assert "mushrooms" in ctx

    def test_empty_sections_omitted(self):
        ctx = openai_service._generate_preference_context_from_request({
            "units": "metric",
        })
        assert "Hard constraints" not in ctx
        assert "Additional preferences" not in ctx
        assert "Soft preferences" in ctx

    def test_empty_dict_returns_empty_string(self):
        assert openai_service._generate_preference_context_from_request({}) == ""

    def test_user_profile_header_present_when_nonempty(self):
        ctx = openai_service._generate_preference_context_from_request({"units": "metric"})
        assert ctx.startswith("\n\n## USER PROFILE")


# ---------------------------------------------------------------------------
# _check_preference_compliance
# ---------------------------------------------------------------------------
class TestCheckPreferenceCompliance:
    def _recipe_with_ingredients(self, names):
        return {
            "recipe": {"title": "Test", "instructions": ["Cook"]},
            "ingredients": [{"name": n, "amount": "1", "unit": "cup", "category": "produce"} for n in names],
        }

    def test_no_preferences_returns_none(self):
        recipe = self._recipe_with_ingredients(["chicken breast", "olive oil"])
        assert openai_service._check_preference_compliance(recipe, None) is None

    def test_no_allergens_or_dietary_returns_none(self):
        recipe = self._recipe_with_ingredients(["chicken breast"])
        assert openai_service._check_preference_compliance(recipe, {"units": "metric"}) is None

    def test_vegan_violation_detected(self):
        recipe = self._recipe_with_ingredients(["chicken breast", "olive oil"])
        result = openai_service._check_preference_compliance(
            recipe, {"dietaryRestrictions": ["vegan"]}
        )
        assert result is not None
        assert "chicken" in result.lower()

    def test_allergen_violation_detected(self):
        recipe = self._recipe_with_ingredients(["peanut butter", "jelly"])
        result = openai_service._check_preference_compliance(
            recipe, {"allergens": ["peanut"]}
        )
        assert result is not None
        assert "peanut" in result.lower()

    def test_gluten_free_violation_detected(self):
        recipe = self._recipe_with_ingredients(["wheat flour", "eggs"])
        result = openai_service._check_preference_compliance(
            recipe, {"dietaryRestrictions": ["gluten-free"]}
        )
        assert result is not None
        assert "wheat" in result.lower()

    def test_dairy_free_compliant_passes(self):
        recipe = self._recipe_with_ingredients(["coconut milk", "tofu", "garlic"])
        result = openai_service._check_preference_compliance(
            recipe, {"dietaryRestrictions": ["dairy-free"]}
        )
        assert result is None

    def test_compliance_error_contains_actionable_text(self):
        recipe = self._recipe_with_ingredients(["butter", "garlic"])
        result = openai_service._check_preference_compliance(
            recipe, {"dietaryRestrictions": ["vegan"]}
        )
        assert result is not None
        assert "Remove or substitute" in result


# ---------------------------------------------------------------------------
# _validate_recipe_data — tightened checks
# ---------------------------------------------------------------------------
class TestValidateRecipeDataTightened:
    def test_empty_title_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "", "instructions": ["Cook it"]},
            "ingredients": [{"name": "x", "amount": "1", "category": "y"}],
        })
        assert not ok and err == "format"

    def test_empty_instructions_list_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "My Recipe", "instructions": []},
            "ingredients": [{"name": "x", "amount": "1", "category": "y"}],
        })
        assert not ok and err == "format"

    def test_blank_string_instructions_fails(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "My Recipe", "instructions": "   "},
            "ingredients": [{"name": "x", "amount": "1", "category": "y"}],
        })
        assert not ok and err == "format"

    def test_string_instructions_single_step_passes(self):
        ok, err = openai_service._validate_recipe_data({
            "recipe": {"title": "My Recipe", "instructions": "Cook everything"},
            "ingredients": [{"name": "x", "amount": "1", "category": "y"}],
        })
        assert ok and err == ""


# ---------------------------------------------------------------------------
# generate_recipe — compliance retry integration
# ---------------------------------------------------------------------------
class TestGenerateRecipeComplianceRetry:
    async def test_compliance_failure_triggers_retry(self, monkeypatch, user_factory):
        """First attempt has a vegan-violating ingredient; second attempt is clean."""
        vegan_recipe = {
            "recipe": {
                "title": "Pasta",
                "instructions": ["Cook pasta"],
                "description": "",
                "prepTime": 10,
                "cookTime": 20,
                "servings": 4,
                "difficulty": "easy",
                "tips": [],
            },
            "ingredients": [
                {"name": "chicken breast", "amount": "200", "unit": "g", "category": "butchery"},
                {"name": "pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
            ],
        }
        clean_vegan_recipe = {
            "recipe": {
                "title": "Vegan Pasta",
                "instructions": ["Cook pasta"],
                "description": "",
                "prepTime": 10,
                "cookTime": 20,
                "servings": 4,
                "difficulty": "easy",
                "tips": [],
            },
            "ingredients": [
                {"name": "pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
                {"name": "olive oil", "amount": "2", "unit": "tbsp", "category": "pantry"},
            ],
        }

        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            if attempts["n"] == 1:
                return make_chat_completion(json.dumps(vegan_recipe))
            return make_chat_completion(json.dumps(clean_vegan_recipe))

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        from app.schemas import RecipeGenerationRequest
        request = RecipeGenerationRequest(
            prompt="vegan pasta",
            preferences={
                "dietaryRestrictions": ["vegan"],
                "groceryCategories": ["produce", "dry-goods", "pantry", "butchery"],
            },
        )
        result = await openai_service.generate_recipe(request)
        assert attempts["n"] == 2
        assert result["recipe_data"]["recipe"]["title"] == "Vegan Pasta"

    async def test_system_prompt_contains_priority_order(self):
        prompt = openai_service.create_recipe_system_prompt(
            user_categories=["produce", "dairy", "pantry"]
        )
        assert "PRIORITY ORDER" in prompt
        assert "Hard constraints" in prompt or "allergen" in prompt.lower()

    async def test_user_message_has_user_request_header(self, user_factory):
        messages = openai_service.create_recipe_messages(
            "creamy pasta",
            user_preferences=None,
            user_categories=["produce", "pantry"],
        )
        user_msg = next(m["content"] for m in messages if m["role"] == "user")
        assert "## USER REQUEST" in user_msg

    async def test_final_compliance_failure_returns_with_defaults(self, monkeypatch):
        """All 3 attempts fail compliance — recipe should still be returned with defaults applied."""
        non_compliant_recipe = {
            "recipe": {
                "title": "Chicken Pasta",
                "instructions": ["Cook chicken", "Add pasta"],
                # Missing optional fields: description, prepTime, cookTime, tips
            },
            "ingredients": [
                {"name": "chicken breast", "amount": "200", "unit": "g", "category": "meat"},
                {"name": "pasta", "amount": "300", "unit": "g", "category": "dry-goods"},
            ],
        }

        # Every attempt returns the same non-compliant recipe
        fake = FakeOpenAIClient()
        fake.chat.completions.create = lambda **kwargs: make_chat_completion(json.dumps(non_compliant_recipe))
        monkeypatch.setattr(openai_service, "client", fake)

        request = RecipeGenerationRequest(
            prompt="vegan pasta",
            preferences={
                "dietaryRestrictions": ["vegan"],
                "groceryCategories": ["produce", "dry-goods", "pantry", "meat"],
            },
        )
        result = await openai_service.generate_recipe(request)

        # Should return even though compliance failed; defaults should be applied
        assert result["recipe_data"]["recipe"]["title"] == "Chicken Pasta"
        assert result["recipe_data"]["recipe"]["description"] == ""  # Default applied
        assert result["recipe_data"]["recipe"]["servings"] == 4  # Default applied
        assert result["recipe_data"]["recipe"]["difficulty"] == "medium"  # Default applied
        assert isinstance(result["recipe_data"]["recipe"]["instructions"], list)
        assert result["retry_count"] == 2  # 2 retries (total 3 attempts)


# ---------------------------------------------------------------------------
# Two-tier model selection
# ---------------------------------------------------------------------------
class TestModelSelection:
    def test_free_user_resolves_to_model_free(self, user_factory):
        user = user_factory()
        assert openai_service._select_model(user) == openai_service.model_free

    def test_premium_user_resolves_to_model_paid(self, user_factory):
        user = user_factory(premium_expires_at=datetime.now(timezone.utc) + timedelta(days=30))
        assert openai_service._select_model(user) == openai_service.model_paid

    def test_none_user_resolves_to_model_free(self):
        assert openai_service._select_model(None) == openai_service.model_free

    def test_select_model_never_raises(self, monkeypatch, user_factory):
        user = user_factory()
        monkeypatch.setattr(openai_service, "_is_premium_user", lambda u: 1 / 0)
        assert openai_service._select_model(user) == openai_service.default_model

    async def test_generate_recipe_reports_actual_model_used(self, monkeypatch, user_factory):
        fake = FakeOpenAIClient()
        monkeypatch.setattr(openai_service, "client", fake)

        user = user_factory(premium_expires_at=datetime.now(timezone.utc) + timedelta(days=30))
        request = RecipeGenerationRequest(prompt="creamy pasta")
        result = await openai_service.generate_recipe(request, user)

        assert result["model"] == openai_service.model_paid
        assert fake.calls[0]["model"] == openai_service.model_paid


# ---------------------------------------------------------------------------
# Refusal handling (strict-schema refused flag + SDK refusal channel)
# ---------------------------------------------------------------------------
class TestRecipeRefusal:
    async def test_refused_flag_raises_without_retry(self, monkeypatch, user_factory):
        refused_payload = {
            "refused": True,
            "refusal_reason": "Not a legitimate recipe request.",
            "recipe": None,
            "ingredients": None,
        }
        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            return make_chat_completion(json.dumps(refused_payload))

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RecipeRequestRefused):
            await openai_service.generate_recipe(
                RecipeGenerationRequest(prompt="anything"), user_factory(),
            )
        assert attempts["n"] == 1

    async def test_sdk_refusal_channel_raises_without_retry(self, monkeypatch, user_factory):
        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            return make_chat_completion(refusal="I can't help with that.")

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RecipeRequestRefused):
            await openai_service.generate_recipe(
                RecipeGenerationRequest(prompt="anything"), user_factory(),
            )
        assert attempts["n"] == 1

    async def test_missing_refused_key_treated_as_false(self, monkeypatch, user_factory):
        """Old-format fixtures (no `refused` key) must still parse as a success."""
        fake = FakeOpenAIClient()
        monkeypatch.setattr(openai_service, "client", fake)

        result = await openai_service.generate_recipe(
            RecipeGenerationRequest(prompt="anything"), user_factory(),
        )
        assert result["recipe_data"]["recipe"]["title"] == "Creamy Chicken Pasta"

    async def test_modify_refused_flag_raises_without_retry(self, monkeypatch, user_factory):
        refused_payload = {
            "refused": True,
            "refusal_reason": "Not a legitimate recipe request.",
            "recipe": None,
            "ingredients": None,
        }
        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            return make_chat_completion(json.dumps(refused_payload))

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        original_recipe = SimpleNamespace(
            id=1, title="Test", description="d", instructions=["a"],
            prep_time=5, cook_time=5, servings=2, difficulty="easy", tips=[],
        )
        with pytest.raises(RecipeRequestRefused):
            await openai_service.modify_recipe(
                original_recipe, [], "make it dangerous", user_factory(),
            )
        assert attempts["n"] == 1

    async def test_ideas_refused_flag_raises_without_retry(self, monkeypatch):
        refused_payload = {
            "refused": True,
            "refusal_reason": "Not a legitimate recipe request.",
            "ideas": None,
        }
        attempts = {"n": 0}

        def create(**kwargs):
            attempts["n"] += 1
            return make_chat_completion(json.dumps(refused_payload))

        fake = FakeOpenAIClient()
        fake.chat.completions.create = create
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RecipeRequestRefused):
            await openai_service.generate_recipe_ideas("anything", count=3)
        assert attempts["n"] == 1


# ---------------------------------------------------------------------------
# OpenAI moderation pre-filter (fails open)
# ---------------------------------------------------------------------------
class TestModeration:
    def test_flagged_text_raises_refused(self, monkeypatch):
        fake = FakeOpenAIClient()
        fake.moderation_flagged = True
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RecipeRequestRefused):
            openai_service._check_moderation("some text")

    def test_moderation_error_fails_open(self, monkeypatch):
        fake = FakeOpenAIClient()

        def boom(**kwargs):
            raise RuntimeError("moderation service down")
        fake.moderations.create = boom
        monkeypatch.setattr(openai_service, "client", fake)

        # Must not raise
        openai_service._check_moderation("some text")

    async def test_flagged_prompt_blocks_before_chat_call(self, monkeypatch, user_factory):
        fake = FakeOpenAIClient()
        fake.moderation_flagged = True
        monkeypatch.setattr(openai_service, "client", fake)

        with pytest.raises(RecipeRequestRefused):
            await openai_service.generate_recipe(
                RecipeGenerationRequest(prompt="anything"), user_factory(),
            )
        assert len(fake.calls) == 0
        assert len(fake.moderation_calls) == 1

    async def test_moderation_service_outage_allows_generation_to_proceed(self, monkeypatch, user_factory):
        fake = FakeOpenAIClient()

        def boom(**kwargs):
            raise RuntimeError("moderation service down")
        fake.moderations.create = boom
        monkeypatch.setattr(openai_service, "client", fake)

        result = await openai_service.generate_recipe(
            RecipeGenerationRequest(prompt="anything"), user_factory(),
        )
        assert result["recipe_data"]["recipe"]["title"] == "Creamy Chicken Pasta"


# ---------------------------------------------------------------------------
# Job service integration — refusal / moderation failures land as failed jobs
# ---------------------------------------------------------------------------
class TestJobServiceRefusal:
    async def test_moderation_flagged_job_ends_failed_with_clean_message(
        self, monkeypatch, user_factory, db_session,
    ):
        from app.services.job_service import job_service
        from app.models import RecipeJob

        fake = FakeOpenAIClient()
        fake.moderation_flagged = True
        monkeypatch.setattr(openai_service, "client", fake)

        user = user_factory()
        job = RecipeJob(
            id="refusal-job", user_id=user.id, status="pending",
            job_type="generate", prompt="anything", progress=0,
        )
        db_session.add(job)
        db_session.commit()

        await job_service._process_generation_job("refusal-job")

        db_session.expire_all()
        refreshed = db_session.query(RecipeJob).filter_by(id="refusal-job").first()
        assert refreshed.status == "failed"
        assert "server error" not in (refreshed.error_message or "").lower()
        assert len(fake.calls) == 0
