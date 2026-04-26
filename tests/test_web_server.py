"""Tests for web server — no hardware mocks required."""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import state
from web_server import (
    get_status_json,
    handle_clear_leds,
    handle_flash_led,
    handle_save_config,
    load_template,
    start_web_server,
)


# ── Status JSON ───────────────────────────────────────────────────────────────

class TestStatusJson(unittest.TestCase):
    def setUp(self):
        state.current_airports.clear()
        state.current_airports.extend(["CYYZ", "CYTZ"])
        state.status_display["home_airport"] = "CYYZ"
        state.status_display["timezone"] = "America/Toronto"
        state.status_display["last_metar"] = None
        state.status_display["ip_address"] = "192.168.1.100"
        state.LED_COUNT = 100

    def test_keys_present(self):
        for key in ("airports", "home", "timezone", "last_metar", "ip_address", "led_count"):
            self.assertIn(key, get_status_json())

    def test_airports(self):
        self.assertEqual(get_status_json()["airports"], ["CYYZ", "CYTZ"])

    def test_led_count(self):
        state.LED_COUNT = 42
        self.assertEqual(get_status_json()["led_count"], 42)

    def test_home(self):
        self.assertEqual(get_status_json()["home"], "CYYZ")

    def test_last_metar_none(self):
        self.assertIsNone(get_status_json()["last_metar"])

    def test_last_metar_iso(self):
        from datetime import datetime, timezone
        state.status_display["last_metar"] = datetime(2024, 4, 19, 14, 0, tzinfo=timezone.utc)
        self.assertIn("2024-04-19", get_status_json()["last_metar"])


# ── Template ──────────────────────────────────────────────────────────────────

class TestLoadTemplate(unittest.TestCase):
    def test_is_string(self):
        t = load_template()
        self.assertIsInstance(t, str)
        self.assertGreater(len(t), 100)

    def test_title(self):
        self.assertIn("METAR Map", load_template())

    def test_api_status_endpoint(self):
        self.assertIn("/api/status", load_template())

    def test_api_config_endpoint(self):
        self.assertIn("/api/config", load_template())

    def test_api_leds_clear_endpoint(self):
        self.assertIn("/api/leds/clear", load_template())

    def test_valid_html(self):
        t = load_template()
        self.assertIn("<!DOCTYPE html>", t)
        self.assertIn("</html>", t)

    def test_has_home_tab(self):
        self.assertIn("tab-home", load_template())

    def test_has_config_tab(self):
        self.assertIn("tab-config", load_template())


# ── LED clear ─────────────────────────────────────────────────────────────────

class TestHandleClearLeds(unittest.TestCase):
    def test_no_strip_returns_error(self):
        state.strip = None
        result = handle_clear_leds()
        self.assertIn("error", result)

    def test_calls_led_clear(self):
        mock_strip = MagicMock()
        mock_strip.numPixels.return_value = 5
        state.strip = mock_strip
        result = handle_clear_leds()
        self.assertTrue(result.get("ok"))
        mock_strip.show.assert_called()
        state.strip = None


# ── LED flash ─────────────────────────────────────────────────────────────────

class TestHandleFlashLed(unittest.TestCase):
    def setUp(self):
        self.mock_strip = MagicMock()
        self.mock_strip.numPixels.return_value = 10
        state.strip = self.mock_strip

    def tearDown(self):
        state.strip = None

    @patch("web_server.time.sleep")
    def test_flash_returns_ok(self, _sleep):
        result = handle_flash_led(3)
        self.assertTrue(result.get("ok"))

    @patch("web_server.time.sleep")
    def test_flash_calls_set_pixel(self, _sleep):
        handle_flash_led(3)
        self.assertGreater(self.mock_strip.setPixelColor.call_count, 0)

    @patch("web_server.time.sleep")
    def test_flash_targets_correct_led(self, _sleep):
        handle_flash_led(7)
        indices = [call[0][0] for call in self.mock_strip.setPixelColor.call_args_list]
        self.assertTrue(all(i == 7 for i in indices))

    def test_out_of_range_returns_error(self):
        result = handle_flash_led(99)
        self.assertIn("error", result)

    def test_no_strip_returns_error(self):
        state.strip = None
        result = handle_flash_led(0)
        self.assertIn("error", result)


# ── Save config ───────────────────────────────────────────────────────────────

class TestHandleSaveConfig(unittest.TestCase):
    def _make_body(self, airports):
        return json.dumps({"airports": airports}).encode()

    @patch("web_server.AIRPORT_FILE")
    def test_saves_valid_airports(self, mock_path):
        mock_path.read_text.return_value = json.dumps({"airports": ["CYYZ"]})
        result = handle_save_config(self._make_body(["CYYZ", "NONE", "KJFK"]))
        self.assertTrue(result.get("ok"))
        mock_path.write_text.assert_called_once()

    @patch("web_server.AIRPORT_FILE")
    def test_updates_state_current_airports(self, mock_path):
        mock_path.read_text.return_value = json.dumps({"airports": []})
        new_airports = ["CYYZ", "NONE", "KJFK"]
        handle_save_config(self._make_body(new_airports))
        self.assertEqual(state.current_airports, new_airports)

    def test_invalid_json_returns_error(self):
        result = handle_save_config(b"not json{")
        self.assertIn("error", result)

    def test_non_list_airports_returns_error(self):
        result = handle_save_config(json.dumps({"airports": "CYYZ"}).encode())
        self.assertIn("error", result)

    @patch("web_server.AIRPORT_FILE")
    def test_invalid_icao_returns_error(self, mock_path):
        mock_path.read_text.return_value = json.dumps({"airports": []})
        result = handle_save_config(self._make_body(["bad_icao"]))
        self.assertIn("error", result)
        mock_path.write_text.assert_not_called()

    @patch("web_server.AIRPORT_FILE")
    def test_preserves_other_config_fields(self, mock_path):
        existing = {"airports": ["CYYZ"], "home": "CYYZ", "num_leds": 50}
        mock_path.read_text.return_value = json.dumps(existing)
        handle_save_config(self._make_body(["CYYZ", "KJFK"]))
        written = json.loads(mock_path.write_text.call_args[0][0])
        self.assertEqual(written["home"], "CYYZ")
        self.assertEqual(written["num_leds"], 50)
        self.assertEqual(written["airports"], ["CYYZ", "KJFK"])


# ── Server startup ────────────────────────────────────────────────────────────

class TestWebServerStart(unittest.TestCase):
    @patch("web_server.HTTPServer")
    @patch("web_server.threading.Thread")
    def test_creates_daemon_thread(self, mock_thread_cls, mock_server_cls):
        mock_server_cls.return_value = MagicMock()
        start_web_server(8080)
        self.assertTrue(mock_thread_cls.call_args[1].get("daemon", False))

    @patch("web_server.HTTPServer")
    @patch("web_server.threading.Thread")
    def test_returns_server(self, _thread, mock_server_cls):
        server = MagicMock()
        mock_server_cls.return_value = server
        self.assertIs(start_web_server(8080), server)


# ── NONE code handling (integration) ─────────────────────────────────────────

class TestNoneCode(unittest.TestCase):
    def test_validate_allows_none_in_airports(self):
        from config import validate_config
        validate_config({"airports": ["CYYZ", "NONE", "CYTZ"], "home": "CYYZ"})

    def test_parse_metar_skips_none(self):
        from metar_api import parse_metar_statuses
        reports = [
            {"icaoId": "CYYZ", "clouds": [{"cover": "SCT", "base": 5000}]},
            {"icaoId": "NONE", "clouds": [{"cover": "OVC", "base": 200}]},
        ]
        cats = parse_metar_statuses(reports, ["CYYZ", "NONE"])
        self.assertEqual(cats["CYYZ"], "VFR")
        self.assertEqual(cats["NONE"], "UNK")

    def test_led_update_turns_off_none(self):
        from hardware import Color
        from led_control import led_update
        strip = MagicMock()
        strip.numPixels.return_value = 100
        led_update(strip, ["CYYZ", "NONE"], {"CYYZ": "VFR", "NONE": "UNK"})
        strip.setPixelColor.assert_any_call(0, Color(*state.COLOR_MAP["VFR"]))
        strip.setPixelColor.assert_any_call(1, Color(0, 0, 0))


if __name__ == "__main__":
    unittest.main()
