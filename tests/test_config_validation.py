"""Tests for config file validation — no hardware mocks required."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import validate_config, _is_valid_icao, _is_none_code


class TestValidateConfigValid(unittest.TestCase):
    def test_minimal_valid_config(self):
        validate_config({"airports": ["CYYZ"]})

    def test_full_valid_config(self):
        validate_config({
            "airports": ["CYYZ", "CYTZ", "CYOW"],
            "home": "CYYZ",
            "colors": {"VFR": [0, 140, 0], "MVFR": [0, 0, 140]},
            "dim_colors": {"VFR": [0, 45, 0]},
            "num_leds": 100,
        })

    def test_home_missing_is_ok(self):
        validate_config({"airports": ["CYYZ", "CYTZ"]})

    def test_colors_missing_is_ok(self):
        validate_config({"airports": ["CYYZ"]})

    def test_dim_colors_missing_is_ok(self):
        validate_config({"airports": ["CYYZ"]})

    def test_num_leds_missing_is_ok(self):
        validate_config({"airports": ["CYYZ"]})

    def test_numeric_icao(self):
        validate_config({"airports": ["K123"]})

    def test_color_boundary_values(self):
        validate_config({"airports": ["CYYZ"], "colors": {"VFR": [0, 0, 255]}})

    def test_tuple_color_values(self):
        validate_config({"airports": ["CYYZ"], "colors": {"VFR": (0, 140, 0)}})


class TestValidateConfigAirports(unittest.TestCase):
    def test_empty_airports_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": []})

    def test_non_list_airports_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": "CYYZ"})

    def test_too_short_icao_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYY"]})

    def test_too_long_icao_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZX"]})

    def test_lowercase_icao_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["cyyz"]})

    def test_spaces_in_icao_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CY YZ"]})

    def test_special_chars_in_icao_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CY-Z"]})

    def test_multiple_invalid_airports_all_reported(self):
        with self.assertRaises(ValueError) as ctx:
            validate_config({"airports": ["bad", "CYYZ", "also_bad"]})
        msg = str(ctx.exception)
        self.assertIn("airports[0]", msg)
        self.assertIn("airports[2]", msg)

    def test_none_placeholder_allowed(self):
        validate_config({"airports": ["CYYZ", "NONE", "CYTZ"]})


class TestValidateConfigHome(unittest.TestCase):
    def test_home_not_in_airports_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "home": "KJFK"})

    def test_home_in_airports_passes(self):
        validate_config({"airports": ["CYYZ", "KJFK"], "home": "KJFK"})

    def test_home_invalid_format_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "home": "bad"})

    def test_empty_home_is_ok(self):
        validate_config({"airports": ["CYYZ"], "home": ""})

    def test_none_home_is_ok(self):
        validate_config({"airports": ["CYYZ"], "home": None})

    def test_none_home_value_allowed(self):
        validate_config({"airports": ["CYYZ"], "home": "NONE"})


class TestValidateConfigColors(unittest.TestCase):
    def test_wrong_array_length_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": {"VFR": [0, 255]}})

    def test_negative_value_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": {"VFR": [-1, 0, 0]}})

    def test_over_255_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": {"VFR": [256, 0, 0]}})

    def test_float_value_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": {"VFR": [0.5, 0, 0]}})

    def test_string_value_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": {"VFR": ["red", 0, 0]}})

    def test_non_dict_colors_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "colors": [[0, 140, 0]]})

    def test_dim_colors_same_rules(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "dim_colors": {"VFR": [256, 0, 0]}})


class TestValidateConfigNumLeds(unittest.TestCase):
    def test_zero_num_leds_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "num_leds": 0})

    def test_negative_num_leds_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "num_leds": -1})

    def test_float_num_leds_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "num_leds": 10.5})

    def test_string_num_leds_raises(self):
        with self.assertRaises(ValueError):
            validate_config({"airports": ["CYYZ"], "num_leds": "100"})


class TestValidateConfigMultipleErrors(unittest.TestCase):
    def test_all_errors_reported_at_once(self):
        with self.assertRaises(ValueError) as ctx:
            validate_config({
                "airports": ["bad"],
                "colors": {"VFR": [999, 0, 0]},
                "num_leds": -5,
            })
        msg = str(ctx.exception)
        self.assertIn("airports[0]", msg)
        self.assertIn("colors.VFR", msg)
        self.assertIn("num_leds", msg)

    def test_empty_config_raises(self):
        with self.assertRaises(ValueError):
            validate_config({})


class TestHelpers(unittest.TestCase):
    def test_is_valid_icao_valid(self):
        self.assertTrue(_is_valid_icao("CYYZ"))
        self.assertTrue(_is_valid_icao("KJFK"))
        self.assertTrue(_is_valid_icao("K123"))

    def test_is_valid_icao_invalid(self):
        self.assertFalse(_is_valid_icao("CYY"))    # too short
        self.assertFalse(_is_valid_icao("cyyz"))   # lowercase
        self.assertFalse(_is_valid_icao(""))       # empty
        self.assertTrue(_is_valid_icao("NONE"))    # valid format (handled separately by _is_none_code)

    def test_is_none_code(self):
        self.assertTrue(_is_none_code("NONE"))
        self.assertTrue(_is_none_code("none"))
        self.assertTrue(_is_none_code("None"))

    def test_is_none_code_negative(self):
        self.assertFalse(_is_none_code("CYYZ"))
        self.assertFalse(_is_none_code(""))


if __name__ == "__main__":
    unittest.main()
