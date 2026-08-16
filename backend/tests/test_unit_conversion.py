"""Pure function tests for app.services.unit_conversion."""
import pytest

from app.services import unit_conversion


class TestParseQuantity:
    def test_parses_plain_amount_and_unit(self):
        pq = unit_conversion.parse_quantity("200 g")
        assert pq.amount == 200
        assert pq.unit == "g"

    def test_parses_bare_number(self):
        pq = unit_conversion.parse_quantity("2")
        assert pq.amount == 2
        assert pq.unit is None

    def test_parses_simple_fraction(self):
        pq = unit_conversion.parse_quantity("1/2 cup")
        assert pq.amount == 0.5
        assert pq.unit == "cup"

    def test_parses_mixed_fraction(self):
        pq = unit_conversion.parse_quantity("1 1/2 cups")
        assert pq.amount == 1.5
        assert pq.unit == "cup"

    def test_returns_none_for_to_taste(self):
        assert unit_conversion.parse_quantity("to taste") is None

    def test_returns_none_for_pinch(self):
        assert unit_conversion.parse_quantity("pinch") is None

    def test_returns_none_for_empty_string(self):
        assert unit_conversion.parse_quantity("") is None

    @pytest.mark.parametrize("alias,expected", [
        ("tsp", "tsp"), ("teaspoon", "tsp"), ("teaspoons", "tsp"),
        ("tbsp", "tbsp"), ("tablespoon", "tbsp"), ("tablespoons", "tbsp"),
        ("cup", "cup"), ("cups", "cup"),
        ("ml", "ml"), ("milliliter", "ml"), ("millilitre", "ml"),
        ("l", "l"), ("liter", "l"), ("litre", "l"),
        ("fl oz", "floz"), ("fluid ounce", "floz"),
        ("g", "g"), ("gram", "g"), ("grams", "g"),
        ("kg", "kg"), ("kilogram", "kg"),
        ("oz", "oz"), ("ounce", "oz"), ("ounces", "oz"),
        ("lb", "lb"), ("lbs", "lb"), ("pound", "lb"), ("pounds", "lb"),
    ])
    def test_unit_aliases_normalize(self, alias, expected):
        pq = unit_conversion.parse_quantity(f"1 {alias}")
        assert pq.unit == expected


class TestSumQuantities:
    def test_same_unit_weight_sums_metric(self):
        result = unit_conversion.sum_quantities(["200 g", "300 g"], unit_system="metric")
        assert result == "500 g"

    def test_same_unit_weight_sums_imperial_converts_to_lb(self):
        # 500 g is above the 16 oz (453.6 g) step threshold, so imperial mode
        # renders it in lb rather than g.
        result = unit_conversion.sum_quantities(["200 g", "300 g"], unit_system="imperial")
        assert result.endswith("lb")

    def test_weight_steps_to_kg_in_metric(self):
        result = unit_conversion.sum_quantities(["600 g", "500 g"], unit_system="metric")
        assert result == "1.1 kg"

    def test_weight_stays_g_below_threshold_in_metric(self):
        result = unit_conversion.sum_quantities(["400 g", "500 g"], unit_system="metric")
        assert result == "900 g"

    def test_weight_steps_to_lb_in_imperial(self):
        result = unit_conversion.sum_quantities(["300 g", "300 g"], unit_system="imperial")
        assert result.endswith("lb")

    def test_weight_stays_oz_below_threshold_in_imperial(self):
        result = unit_conversion.sum_quantities(["50 g"], unit_system="imperial")
        assert result.endswith("oz")

    def test_volume_steps_to_l_in_metric(self):
        result = unit_conversion.sum_quantities(["600 ml", "500 ml"], unit_system="metric")
        assert result == "1.1 l"

    def test_volume_stays_ml_below_threshold_in_metric(self):
        result = unit_conversion.sum_quantities(["200 ml", "300 ml"], unit_system="metric")
        assert result == "500 ml"

    def test_volume_uses_cup_in_imperial(self):
        result = unit_conversion.sum_quantities(["200 ml", "200 ml"], unit_system="imperial")
        assert result.endswith("cup")

    def test_volume_uses_tsp_for_small_amounts_in_imperial(self):
        result = unit_conversion.sum_quantities(["1 tsp"], unit_system="imperial")
        assert result.endswith("tsp")

    def test_mixed_compatible_volume_units_combine(self):
        result = unit_conversion.sum_quantities(["2 tbsp", "60 ml"], unit_system="metric")
        assert "+" not in result

    def test_incompatible_units_concatenate(self):
        result = unit_conversion.sum_quantities(["2 cloves", "1 tsp"], unit_system="metric")
        assert "+" in result
        assert "2 cloves" in result

    def test_to_taste_mixed_with_real_quantity_concatenates(self):
        result = unit_conversion.sum_quantities(["to taste", "1 tsp"], unit_system="metric")
        assert "to taste" in result
        assert "+" in result

    def test_fraction_quantities_sum(self):
        result = unit_conversion.sum_quantities(["1/2 cup", "1/2 cup"], unit_system="imperial")
        assert result == "1 cup"

    def test_strips_trailing_zeros_from_numeric_portion_only(self):
        result = unit_conversion.sum_quantities(["2500 g"], unit_system="metric")
        assert result == "2.5 kg"

    def test_all_unparseable_falls_back_to_original_text(self):
        result = unit_conversion.sum_quantities(["to taste", "pinch"], unit_system="metric")
        assert result == "to taste + pinch"
