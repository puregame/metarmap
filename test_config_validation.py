"""Tests for config file validation."""

import unittest
from unittest.mock import MagicMock, patch
import sys

# Mock hardware modules before importing runmap
sys.modules["board"] = MagicMock()
sys.modules["adafruit_ssd1306"] = MagicMock()
sys.modules["rpi_ws281x"] = MagicMock()
sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()
sys.modules["PIL.ImageDraw"] = MagicMock()
sys.modules["PIL.ImageFont"] = MagicMock()
sys.modules["astral"] = MagicMock()
sys.modules["astral.sun"] = MagicMock()
sys.modules["astral.LocationInfo"] = MagicMock()

from runmap import validate_config


class TestValidateConfigValid(unittest.TestCase):
    """Test that valid configs pass validation."""

    def test_minimal_valid_config(self):
        """A config with just airports passes."""
        data = {"airports": ["CYYZ"]}
        validate_config(data)

    def test_full_valid_config(self):
        """A complete config with all fields passes."""
        data = {
            "airports": ["CYYZ", "CYTZ", "CYOW"],
            "home": "CYYZ",
            "colors": {"VFR": [0, 140, 0], "MVFR": [0, 0, 140]},
            "dim_colors": {"VFR": [0, 45, 0]},
            "num_leds": 100,
            "led_cycle": ["CYYZ", "CYTZ", "", "CYOW"],
        }
        validate_config(data)

    def test_home_missing_is_ok(self):
        """Missing home field does not cause error."""
        data = {"airports": ["CYYZ", "CYTZ"]}
        validate_config(data)

    def test_colors_missing_is_ok(self):
        """Missing colors field does not cause error."""
        data = {"airports": ["CYYZ"]}
        validate_config(data)

    def test_dim_colors_missing_is_ok(self):
        """Missing dim_colors field does not cause error."""
        data = {"airports": ["CYYZ"]}
        validate_config(data)

    def test_num_leds_missing_is_ok(self):
        """Missing num_leds field does not cause error."""
        data = {"airports": ["CYYZ"]}
        validate_config(data)

    def test_led_cycle_missing_is_ok(self):
        """Missing led_cycle field does not cause error."""
        data = {"airports": ["CYYZ"]}
        validate_config(data)

    def test_empty_string_in_led_cycle(self):
        """Empty strings in led_cycle are valid."""
        data = {
            "airports": ["CYYZ"],
            "led_cycle": ["", "", "CYYZ", ""],
        }
        validate_config(data)

    def test_numeric_icao_codes(self):
        """Numeric ICAO codes like K123 are valid."""
        data = {"airports": ["K123", "K001"]}
        validate_config(data)

    def test_mixed_alphanumeric_icao(self):
        """Mixed alphanumeric ICAO codes are valid."""
        data = {"airports": ["K1A2"]}
        validate_config(data)

    def test_all_color_categories_valid(self):
        """All standard color categories with valid values pass."""
        data = {
            "airports": ["CYYZ"],
            "colors": {
                "VFR": [0, 140, 0],
                "MVFR": [0, 0, 140],
                "IFR": [140, 0, 0],
                "LIFR": [120, 0, 80],
                "UNK": [100, 100, 100],
            },
            "dim_colors": {
                "VFR": [0, 45, 0],
                "MVFR": [0, 0, 45],
                "IFR": [45, 0, 0],
                "LIFR": [64, 0, 64],
                "UNK": [50, 50, 50],
            },
        }
        validate_config(data)

    def test_boundary_color_values(self):
        """Color values at boundaries (0 and 255) are valid."""
        data = {
            "airports": ["CYYZ"],
            "colors": {"VFR": [0, 0, 0], "MVFR": [255, 255, 255]},
        }
        validate_config(data)

    def test_num_leds_boundary(self):
        """num_leds = 1 is valid."""
        data = {"airports": ["CYYZ"], "num_leds": 1}
        validate_config(data)

    def test_large_num_leds(self):
        """Large num_leds values are valid."""
        data = {"airports": ["CYYZ"], "num_leds": 10000}
        validate_config(data)


class TestValidateConfigAirports(unittest.TestCase):
    """Test airports validation."""

    def test_empty_airports_list(self):
        """Empty airports list raises error."""
        data = {"airports": []}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("at least one airport", str(ctx.exception))

    def test_airports_not_a_list(self):
        """Non-list airports raises error."""
        data = {"airports": "CYYZ"}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("must be a list", str(ctx.exception))

    def test_airports_too_short(self):
        """ICAO code with fewer than 4 chars fails."""
        data = {"airports": ["CYY"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("CYY", str(ctx.exception))

    def test_airports_too_long(self):
        """ICAO code with more than 4 chars fails."""
        data = {"airports": ["CYYZA"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("CYYZA", str(ctx.exception))

    def test_airports_lowercase(self):
        """Lowercase ICAO codes fail."""
        data = {"airports": ["cyyz"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("cyyz", str(ctx.exception))

    def test_airports_with_spaces(self):
        """ICAO codes with spaces fail."""
        data = {"airports": ["CY YZ"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("CY YZ", str(ctx.exception))

    def test_airports_with_special_chars(self):
        """ICAO codes with special characters fail."""
        data = {"airports": ["CYYZ-1"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("CYYZ-1", str(ctx.exception))

    def test_airports_with_numbers(self):
        """ICAO codes with numbers pass (e.g. K123)."""
        data = {"airports": ["K123"]}
        validate_config(data)

    def test_multiple_invalid_airports(self):
        """Multiple invalid airports all reported."""
        data = {"airports": ["CYYZ", "INVALID", "TOOLONG", ""]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        err = str(ctx.exception)
        self.assertIn("INVALID", err)
        self.assertIn("TOOLONG", err)


class TestValidateConfigHome(unittest.TestCase):
    """Test home airport validation."""

    def test_home_not_in_airports(self):
        """Home not in airports list raises error."""
        data = {"airports": ["CYYZ", "CYTZ"], "home": "CYOW"}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("not found in airports", str(ctx.exception))

    def test_home_valid(self):
        """Valid home airport passes."""
        data = {"airports": ["CYYZ", "CYTZ"], "home": "CYYZ"}
        validate_config(data)

    def test_home_invalid_format(self):
        """Invalid home format raises error."""
        data = {"airports": ["CYYZ"], "home": "YYZ"}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("ICAO", str(ctx.exception))

    def test_home_empty_string(self):
        """Empty string home is treated as missing."""
        data = {"airports": ["CYYZ"], "home": ""}
        validate_config(data)

    def test_home_none(self):
        """None home is treated as missing."""
        data = {"airports": ["CYYZ"], "home": None}
        validate_config(data)


class TestValidateConfigColors(unittest.TestCase):
    """Test colors validation."""

    def test_color_wrong_length(self):
        """Color with wrong number of values fails."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": [0, 140]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("3 values", str(ctx.exception))

    def test_color_negative_value(self):
        """Negative color value fails."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": [0, -1, 0]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("-1", str(ctx.exception))

    def test_color_over_255(self):
        """Color value over 255 fails."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": [0, 256, 0]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("256", str(ctx.exception))

    def test_color_float_value(self):
        """Float color value fails."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": [0, 140.5, 0]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("140.5", str(ctx.exception))

    def test_color_string_value(self):
        """String color value fails."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": [0, "140", 0]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("140", str(ctx.exception))

    def test_colors_not_dict(self):
        """Non-dict colors raises error."""
        data = {"airports": ["CYYZ"], "colors": [0, 140, 0]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("dictionary", str(ctx.exception))

    def test_dim_color_errors(self):
        """dim_colors same validation rules apply."""
        data = {"airports": ["CYYZ"], "dim_colors": {"VFR": [0, 300, 0]}}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("300", str(ctx.exception))

    def test_color_tuple_accepted(self):
        """Tuples are accepted as color values."""
        data = {"airports": ["CYYZ"], "colors": {"VFR": (0, 140, 0)}}
        validate_config(data)


class TestValidateConfigNumLeds(unittest.TestCase):
    """Test num_leds validation."""

    def test_num_leds_zero(self):
        """num_leds = 0 fails."""
        data = {"airports": ["CYYZ"], "num_leds": 0}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("positive integer", str(ctx.exception))

    def test_num_leds_negative(self):
        """Negative num_leds fails."""
        data = {"airports": ["CYYZ"], "num_leds": -5}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("-5", str(ctx.exception))

    def test_num_leds_float(self):
        """Float num_leds fails."""
        data = {"airports": ["CYYZ"], "num_leds": 100.5}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("100.5", str(ctx.exception))

    def test_num_leds_string(self):
        """String num_leds fails."""
        data = {"airports": ["CYYZ"], "num_leds": "100"}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("'100'", str(ctx.exception))


class TestValidateConfigLedCycle(unittest.TestCase):
    """Test led_cycle validation."""

    def test_led_cycle_invalid_icao(self):
        """Invalid ICAO in led_cycle fails."""
        data = {"airports": ["CYYZ"], "led_cycle": ["cyyz"]}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("cyyz", str(ctx.exception))

    def test_led_cycle_not_list(self):
        """Non-list led_cycle fails."""
        data = {"airports": ["CYYZ"], "led_cycle": "CYYZ"}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        self.assertIn("must be a list", str(ctx.exception))

    def test_led_cycle_empty_string_ok(self):
        """Empty string in led_cycle passes."""
        data = {"airports": ["CYYZ"], "led_cycle": [""]}
        validate_config(data)

    def test_led_cycle_valid_icao_ok(self):
        """Valid ICAO in led_cycle passes."""
        data = {"airports": ["CYYZ"], "led_cycle": ["CYYZ", "CYTZ"]}
        validate_config(data)

    def test_led_cycle_mixed_valid(self):
        """Mixed valid entries in led_cycle pass."""
        data = {"airports": ["CYYZ"], "led_cycle": ["CYYZ", "", "CYTZ", ""]}
        validate_config(data)


class TestValidateConfigMultipleErrors(unittest.TestCase):
    """Test that multiple validation errors are reported together."""

    def test_multiple_errors_reported(self):
        """All errors are reported, not just the first."""
        data = {
            "airports": [],
            "home": "CYYZ",
            "colors": "not_a_dict",
            "num_leds": -1,
        }
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        err = str(ctx.exception)
        self.assertIn("at least one airport", err)
        self.assertIn("not found in airports", err)
        self.assertIn("dictionary", err)
        self.assertIn("positive integer", err)

    def test_missing_all_required(self):
        """Empty config produces meaningful errors."""
        data = {}
        with self.assertRaises(ValueError) as ctx:
            validate_config(data)
        err = str(ctx.exception)
        self.assertIn("must be a list", err)
        self.assertIn("ICAO", err)


if __name__ == "__main__":
    unittest.main()
