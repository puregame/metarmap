import unittest
from unittest.mock import MagicMock
import sys

# Mocking hardware modules before importing runmap
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

from runmap import ceiling_category

class TestMetarParsing(unittest.TestCase):
    def test_clear_sky(self):
        self.assertEqual(ceiling_category([]), "VFR")

    def test_vfr_high_ceiling(self):
        layers = [{"cover": "BKN", "base": 4000}]
        self.assertEqual(ceiling_category(layers), "VFR")

    def test_mvfr(self):
        layers = [{"cover": "OVC", "base": 2000}]
        self.assertEqual(ceiling_category(layers), "MVFR")

    def test_ifr(self):
        layers = [{"cover": "BKN", "base": 800}]
        self.assertEqual(ceiling_category(layers), "IFR")

    def test_lifr(self):
        layers = [{"cover": "OVC", "base": 300}]
        self.assertEqual(ceiling_category(layers), "LIFR")

    def test_lowest_layer_wins(self):
        layers = [
            {"cover": "BKN", "base": 5000},
            {"cover": "OVC", "base": 1500}
        ]
        self.assertEqual(ceiling_category(layers), "MVFR")

    def test_ignore_non_ceiling_layers(self):
        layers = [{"cover": "SCT", "base": 200}]
        self.assertEqual(ceiling_category(layers), "VFR")

if __name__ == "__main__":
    unittest.main()
