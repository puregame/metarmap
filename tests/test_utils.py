"""Tests for utils module — no hardware mocks required."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import (
    ceiling_category,
    get_ceiling_text,
    get_hostname,
    get_visibility_text,
    is_wifi_connected,
    parse_wind_speed_direction,
    utc_to_local,
)


class TestCeilingCategory(unittest.TestCase):
    def test_clear_sky(self):
        self.assertEqual(ceiling_category([]), "VFR")

    def test_vfr_high_ceiling(self):
        self.assertEqual(ceiling_category([{"cover": "BKN", "base": 4000}]), "VFR")

    def test_mvfr(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 2000}]), "MVFR")

    def test_ifr(self):
        self.assertEqual(ceiling_category([{"cover": "BKN", "base": 800}]), "IFR")

    def test_lifr(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 300}]), "LIFR")

    def test_exact_boundary_500(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 500}]), "LIFR")

    def test_exact_boundary_1000(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 1000}]), "IFR")

    def test_exact_boundary_3000(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 3000}]), "MVFR")

    def test_exact_boundary_3001(self):
        self.assertEqual(ceiling_category([{"cover": "OVC", "base": 3001}]), "VFR")

    def test_lowest_layer_wins(self):
        layers = [{"cover": "BKN", "base": 5000}, {"cover": "OVC", "base": 1500}]
        self.assertEqual(ceiling_category(layers), "MVFR")

    def test_sct_layer_ignored(self):
        self.assertEqual(ceiling_category([{"cover": "SCT", "base": 200}]), "VFR")

    def test_skc_layer_ignored(self):
        self.assertEqual(ceiling_category([{"cover": "SKC", "base": 0}]), "VFR")


class TestGetCeilingText(unittest.TestCase):
    def test_clear(self):
        self.assertEqual(get_ceiling_text([]), "CEIL CLR")

    def test_low_ceiling(self):
        self.assertEqual(get_ceiling_text([{"cover": "OVC", "base": 800}]), "CEIL 800")

    def test_high_ceiling_compressed(self):
        self.assertEqual(get_ceiling_text([{"cover": "OVC", "base": 12000}]), "CEIL 120")

    def test_exactly_10000(self):
        self.assertEqual(get_ceiling_text([{"cover": "OVC", "base": 10000}]), "CEIL 100")

    def test_sct_ignored(self):
        self.assertEqual(get_ceiling_text([{"cover": "SCT", "base": 1000}]), "CEIL CLR")

    def test_lowest_bkn_selected(self):
        layers = [{"cover": "OVC", "base": 5000}, {"cover": "BKN", "base": 2000}]
        self.assertEqual(get_ceiling_text(layers), "CEIL 2000")


class TestGetVisibilityText(unittest.TestCase):
    def test_none(self):
        self.assertEqual(get_visibility_text(None), "VIS --")

    def test_ten_plus(self):
        self.assertEqual(get_visibility_text(10), "VIS 10+")

    def test_ten_plus_string(self):
        self.assertEqual(get_visibility_text("10+"), "VIS 10+")

    def test_above_ten(self):
        self.assertEqual(get_visibility_text(15), "VIS 10+")

    def test_normal(self):
        self.assertEqual(get_visibility_text(5), "VIS 5")

    def test_sub_mile(self):
        self.assertEqual(get_visibility_text(0.5), f"VIS {int(0.5 * 5280)}")

    def test_exactly_one(self):
        self.assertEqual(get_visibility_text(1), "VIS 1")


class TestWindParsing(unittest.TestCase):
    def test_normal_wind(self):
        self.assertEqual(parse_wind_speed_direction(15.0, 250.0), "WIND 250/15")

    def test_calm_wind(self):
        self.assertEqual(parse_wind_speed_direction(0.0, 0.0), "WIND CALM")

    def test_missing_speed(self):
        self.assertEqual(parse_wind_speed_direction(None, 250.0), "WIND --/--")

    def test_missing_direction(self):
        self.assertEqual(parse_wind_speed_direction(15.0, None), "WIND --/--")

    def test_missing_both(self):
        self.assertEqual(parse_wind_speed_direction(None, None), "WIND --/--")

    def test_high_speed(self):
        self.assertEqual(parse_wind_speed_direction(45.0, 320.0), "WIND 320/45")

    def test_single_digit_zero_padded(self):
        self.assertEqual(parse_wind_speed_direction(5.0, 180.0), "WIND 180/05")


class TestUtcToLocal(unittest.TestCase):
    def test_no_tz(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, None), dt)

    def test_utc_tz(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, "UTC").hour, 14)

    def test_est(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, "America/Toronto").hour, 10)

    def test_pst(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, "America/Vancouver").hour, 7)

    def test_invalid_tz_returns_utc(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, "Invalid/Zone"), dt)

    def test_none_input(self):
        self.assertIsNone(utc_to_local(None, "America/Toronto"))

    def test_night_crosses_midnight(self):
        dt = datetime(2024, 4, 19, 2, 30, tzinfo=timezone.utc)
        self.assertEqual(utc_to_local(dt, "America/Toronto").hour, 22)


class TestIsWifiConnected(unittest.TestCase):
    @patch("utils.subprocess.check_output", return_value=b"192.168.1.100 \n")
    def test_connected(self, _):
        self.assertTrue(is_wifi_connected())

    @patch("utils.subprocess.check_output", return_value=b"")
    def test_disconnected_empty(self, _):
        self.assertFalse(is_wifi_connected())

    @patch("utils.subprocess.check_output", side_effect=Exception("no wifi"))
    def test_disconnected_exception(self, _):
        self.assertFalse(is_wifi_connected())


class TestGetHostname(unittest.TestCase):
    @patch("utils.subprocess.check_output", return_value=b"metarmap\n")
    def test_normal_hostname(self, _):
        self.assertEqual(get_hostname(), "metarmap")

    @patch("utils.subprocess.check_output", return_value=b"metarmap")
    def test_no_trailing_newline(self, _):
        self.assertEqual(get_hostname(), "metarmap")

    @patch("utils.subprocess.check_output", return_value=b"")
    def test_empty_hostname_returns_unknown(self, _):
        self.assertEqual(get_hostname(), "unknown")

    @patch("utils.subprocess.check_output", side_effect=Exception("no hostname"))
    def test_exception_returns_unknown(self, _):
        self.assertEqual(get_hostname(), "unknown")


if __name__ == "__main__":
    unittest.main()
