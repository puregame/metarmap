import unittest
from unittest.mock import MagicMock
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

from runmap import parse_wind_speed_direction

class TestWindParsing(unittest.TestCase):
    def test_normal_wind(self):
        # Normal wind: direction 250, speed 15
        result = parse_wind_speed_direction(15.0, 250.0)
        self.assertEqual(result, "WIND 250/15")

    def test_calm_wind(self):
        # Calm wind: speed 0
        result = parse_wind_speed_direction(0.0, 0.0)
        self.assertEqual(result, "WIND CALM")

    def test_missing_speed(self):
        # Missing wind speed
        result = parse_wind_speed_direction(None, 250.0)
        self.assertEqual(result, "WIND --/--")

    def test_missing_direction(self):
        # Missing wind direction
        result = parse_wind_speed_direction(15.0, None)
        self.assertEqual(result, "WIND --/--")

    def test_missing_both(self):
        # Both missing
        result = parse_wind_speed_direction(None, None)
        self.assertEqual(result, "WIND --/--")

    def test_high_speed(self):
        # High wind speed
        result = parse_wind_speed_direction(45.0, 320.0)
        self.assertEqual(result, "WIND 320/45")

    def test_single_digit_speed(self):
        # Single digit speed should be zero-padded
        result = parse_wind_speed_direction(5.0, 180.0)
        self.assertEqual(result, "WIND 180/05")

if __name__ == "__main__":
    unittest.main()
