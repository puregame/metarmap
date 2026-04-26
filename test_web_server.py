"""Tests for web server API endpoints."""

import unittest
from unittest.mock import MagicMock, patch
import sys
import json
import io
import threading

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

from runmap import (
    current_airports,
    LED_COUNT,
    status_display,
    get_status_json,
    start_web_server,
    HTML_TEMPLATE,
)
from http.server import HTTPServer


class TestStatusJson(unittest.TestCase):
    """Test get_status_json function."""

    def setUp(self):
        current_airports.clear()
        current_airports.extend(["CYYZ", "CYTZ"])
        status_display['home_airport'] = "CYYZ"
        status_display['timezone'] = "America/Toronto"
        status_display['last_metar'] = None
        status_display['ip_address'] = "192.168.1.100"

    def test_status_json_structure(self):
        """get_status_json returns expected keys."""
        result = get_status_json()
        self.assertIn("airports", result)
        self.assertIn("home", result)
        self.assertIn("timezone", result)
        self.assertIn("last_metar", result)
        self.assertIn("ip_address", result)
        self.assertIn("led_count", result)

    def test_status_json_airports(self):
        """get_status_json returns correct airports list."""
        result = get_status_json()
        self.assertEqual(result["airports"], ["CYYZ", "CYTZ"])

    def test_status_json_led_count(self):
        """get_status_json returns LED_COUNT."""
        result = get_status_json()
        self.assertEqual(result["led_count"], LED_COUNT)


class TestHtmlTemplate(unittest.TestCase):
    """Test HTML template content."""

    def test_template_exists(self):
        """HTML_TEMPLATE is a non-empty string."""
        self.assertIsInstance(HTML_TEMPLATE, str)
        self.assertTrue(len(HTML_TEMPLATE) > 100)

    def test_template_has_required_elements(self):
        """HTML template contains required UI elements."""
        self.assertIn("METAR Map Control", HTML_TEMPLATE)
        self.assertIn("/api/status", HTML_TEMPLATE)


class TestWebServerStart(unittest.TestCase):
    """Test web server startup."""

    @patch("runmap.HTTPServer")
    @patch("runmap.threading.Thread")
    def test_start_web_server_creates_thread(self, mock_thread_cls, mock_server_cls):
        """start_web_server creates and starts a daemon thread."""
        mock_server_instance = MagicMock()
        mock_server_cls.return_value = mock_server_instance

        start_web_server(8080)

        mock_server_cls.assert_called_once()
        mock_thread_cls.assert_called_once()
        # Check daemon=True was passed
        kwargs = mock_thread_cls.call_args[1]
        self.assertTrue(kwargs.get('daemon', False))


class TestNoneCode(unittest.TestCase):
    """Test NONE code handling in airports."""

    def test_is_none_code(self):
        """_is_none_code returns True for NONE."""
        import runmap
        self.assertTrue(runmap._is_none_code("NONE"))
        self.assertTrue(runmap._is_none_code("none"))
        self.assertTrue(runmap._is_none_code("None"))

    def test_is_none_code_not_icao(self):
        """_is_none_code returns False for valid ICAO codes."""
        import runmap
        self.assertFalse(runmap._is_none_code("CYYZ"))
        self.assertFalse(runmap._is_none_code("KJFK"))

    def test_is_none_code_not_empty(self):
        """_is_none_code returns False for empty string."""
        import runmap
        self.assertFalse(runmap._is_none_code(""))

    def test_validate_allows_none_in_airports(self):
        """validate_config allows NONE in airports list."""
        import runmap
        valid_config = {
            "airports": ["CYYZ", "NONE", "CYTZ"],
            "home": "CYYZ",
        }
        # Should not raise
        runmap.validate_config(valid_config)

    def test_parse_metar_skips_none(self):
        """parse_metar_statuses skips NONE entries."""
        import runmap
        reports = [
            {"icaoId": "CYYZ", "clouds": [{"cover": "SCT", "base": 5000}]},
            {"icaoId": "NONE", "clouds": [{"cover": "OVC", "base": 200}]},
        ]
        cats = runmap.parse_metar_statuses(reports, ["CYYZ", "NONE"])
        self.assertEqual(cats["CYYZ"], "VFR")
        self.assertEqual(cats["NONE"], "UNK")

    def test_led_update_turns_off_none(self):
        """led_update turns off LEDs with NONE code."""
        import runmap
        from unittest.mock import MagicMock
        strip = MagicMock()
        strip.numPixels.return_value = 100
        cats = {"CYYZ": "VFR", "NONE": "UNK"}
        runmap.led_update(strip, ["CYYZ", "NONE", "CYTZ"], cats)
        strip.setPixelColor.assert_any_call(0, runmap.Color(0, 140, 0))  # VFR = green
        strip.setPixelColor.assert_any_call(1, runmap.Color(0, 0, 0))  # NONE = off
        strip.setPixelColor.assert_any_call(2, runmap.Color(100, 100, 100))  # UNK = grey


if __name__ == "__main__":
    unittest.main()
