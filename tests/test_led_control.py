"""Tests for LED control functions — uses hardware fallback classes, no mocks needed."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))

import state
from hardware import Color
from led_control import category_to_color, led_clear, led_set_all, led_set_single, led_update


def _mock_strip(size: int = 10) -> MagicMock:
    strip = MagicMock()
    strip.numPixels.return_value = size
    return strip


class TestCategoryToColor(unittest.TestCase):
    def setUp(self):
        state.COLOR_MAP = {
            "VFR": (0, 140, 0),
            "MVFR": (0, 0, 140),
            "IFR": (140, 0, 0),
            "LIFR": (120, 0, 80),
            "UNK": (100, 100, 100),
        }
        state.COLOR_MAP_DIM = {
            "VFR": (0, 45, 0),
            "MVFR": (0, 0, 45),
            "IFR": (45, 0, 0),
            "LIFR": (64, 0, 64),
            "UNK": (50, 50, 50),
        }

    def test_vfr_day(self):
        self.assertEqual(category_to_color("VFR", night_mode=False), Color(0, 140, 0))

    def test_mvfr_day(self):
        self.assertEqual(category_to_color("MVFR"), Color(0, 0, 140))

    def test_ifr_day(self):
        self.assertEqual(category_to_color("IFR"), Color(140, 0, 0))

    def test_lifr_day(self):
        self.assertEqual(category_to_color("LIFR"), Color(120, 0, 80))

    def test_unk_day(self):
        self.assertEqual(category_to_color("UNK"), Color(100, 100, 100))

    def test_vfr_night(self):
        self.assertEqual(category_to_color("VFR", night_mode=True), Color(0, 45, 0))

    def test_ifr_night(self):
        self.assertEqual(category_to_color("IFR", night_mode=True), Color(45, 0, 0))

    def test_unknown_category_falls_back_to_unk(self):
        self.assertEqual(category_to_color("INVALID"), Color(100, 100, 100))

    def test_unknown_category_night_fallback(self):
        self.assertEqual(category_to_color("INVALID", night_mode=True), Color(50, 50, 50))


class TestLedClear(unittest.TestCase):
    def test_all_pixels_set_to_black(self):
        strip = _mock_strip(5)
        led_clear(strip)
        expected = [call(i, Color(0, 0, 0)) for i in range(5)]
        strip.setPixelColor.assert_has_calls(expected, any_order=False)

    def test_show_called_once(self):
        strip = _mock_strip(5)
        led_clear(strip)
        strip.show.assert_called_once()


class TestLedSetAll(unittest.TestCase):
    def test_all_pixels_set_to_color(self):
        strip = _mock_strip(3)
        led_set_all(strip, Color(255, 0, 0))
        expected = [call(i, Color(255, 0, 0)) for i in range(3)]
        strip.setPixelColor.assert_has_calls(expected)

    def test_show_called(self):
        strip = _mock_strip(3)
        led_set_all(strip, Color(0, 255, 0))
        strip.show.assert_called_once()


class TestLedSetSingle(unittest.TestCase):
    def test_sets_correct_pixel(self):
        strip = _mock_strip(10)
        led_set_single(strip, 4, Color(0, 0, 255))
        strip.setPixelColor.assert_called_once_with(4, Color(0, 0, 255))

    def test_show_called(self):
        strip = _mock_strip(10)
        led_set_single(strip, 0, Color(0, 0, 0))
        strip.show.assert_called_once()


class TestLedUpdate(unittest.TestCase):
    def setUp(self):
        state.COLOR_MAP = {"VFR": (0, 140, 0), "UNK": (100, 100, 100)}
        state.COLOR_MAP_DIM = {"VFR": (0, 45, 0), "UNK": (50, 50, 50)}

    def test_vfr_airport_gets_green(self):
        strip = _mock_strip(5)
        led_update(strip, ["CYYZ"], {"CYYZ": "VFR"})
        strip.setPixelColor.assert_any_call(0, Color(0, 140, 0))

    def test_none_airport_gets_black(self):
        strip = _mock_strip(5)
        led_update(strip, ["CYYZ", "NONE"], {"CYYZ": "VFR", "NONE": "UNK"})
        strip.setPixelColor.assert_any_call(1, Color(0, 0, 0))

    def test_empty_string_airport_gets_black(self):
        strip = _mock_strip(5)
        led_update(strip, ["CYYZ", ""], {"CYYZ": "VFR"})
        strip.setPixelColor.assert_any_call(1, Color(0, 0, 0))

    def test_night_mode_uses_dim_colors(self):
        strip = _mock_strip(5)
        led_update(strip, ["CYYZ"], {"CYYZ": "VFR"}, night=True)
        strip.setPixelColor.assert_any_call(0, Color(0, 45, 0))

    def test_stops_at_strip_length(self):
        strip = _mock_strip(2)
        led_update(strip, ["CYYZ", "CYTZ", "CYOW"], {"CYYZ": "VFR", "CYTZ": "VFR", "CYOW": "VFR"})
        self.assertEqual(strip.setPixelColor.call_count, 2)

    def test_show_called(self):
        strip = _mock_strip(3)
        led_update(strip, ["CYYZ"], {"CYYZ": "VFR"})
        strip.show.assert_called_once()


if __name__ == "__main__":
    unittest.main()
