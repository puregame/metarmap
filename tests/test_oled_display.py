"""Tests for display_show_status — requires PIL mock."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()
sys.modules["PIL.ImageDraw"] = MagicMock()
sys.modules["PIL.ImageFont"] = MagicMock()
sys.modules["astral"] = MagicMock()
sys.modules["astral.sun"] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent))

from oled_display import display_show_status


class TestDisplayShowStatus(unittest.TestCase):
    def setUp(self):
        self.mock_oled = MagicMock()
        self.mock_oled.width = 128
        self.mock_oled.height = 32

    def test_calls_image_and_show(self):
        display_data = {
            "ip_address": "192.168.1.50",
            "rssi": -55,
            "hostname": "metarmap",
        }
        display_show_status(self.mock_oled, display_data)
        self.mock_oled.image.assert_called_once()
        self.mock_oled.show.assert_called_once()

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_ip_line(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "192.168.1.50",
            "rssi": -55,
            "hostname": "metarmap",
        }
        display_show_status(self.mock_oled, display_data)

        # First text call: IP at (0, 0) in large font
        first_call = mock_draw.text.call_args_list[0]
        self.assertEqual(first_call[0][0], (0, 0))
        self.assertEqual(first_call[0][1], "192.168.1.50")

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_hostname_wifi_line(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "192.168.1.50",
            "rssi": -55,
            "hostname": "metarmap",
        }
        display_show_status(self.mock_oled, display_data)

        # Second text call: hostname + WiFi at (0, 16)
        second_call = mock_draw.text.call_args_list[1]
        self.assertEqual(second_call[0][0], (0, 16))
        self.assertIn("metarmap", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_wifi_bars_strong(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "10.0.0.1",
            "rssi": -45,
            "hostname": "pi",
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("####", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_wifi_bars_medium(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "10.0.0.1",
            "rssi": -65,
            "hostname": "pi",
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("### ", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_wifi_bars_weak(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "10.0.0.1",
            "rssi": -75,
            "hostname": "pi",
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("##  ", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_draws_wifi_bars_terrible(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "10.0.0.1",
            "rssi": -90,
            "hostname": "pi",
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("#   ", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_no_rssi_shows_no_wifi(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "10.0.0.1",
            "rssi": None,
            "hostname": "pi",
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("No WiFi", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_defaults_hostname_unknown(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "192.168.1.1",
            "rssi": -60,
        }
        display_show_status(self.mock_oled, display_data)

        second_call = mock_draw.text.call_args_list[1]
        self.assertIn("unknown", second_call[0][1])

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_clears_screen_first(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "192.168.1.1",
            "rssi": -60,
            "hostname": "test",
        }
        display_show_status(self.mock_oled, display_data)

        mock_draw.rectangle.assert_called_once()

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_two_text_lines(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "192.168.1.1",
            "rssi": -60,
            "hostname": "test",
        }
        display_show_status(self.mock_oled, display_data)

        # Should have exactly 2 text calls: IP, hostname+WiFi
        self.assertEqual(len(mock_draw.text.call_args_list), 2)

    @patch("oled_display.Image")
    @patch("oled_display.ImageDraw")
    @patch("oled_display.ImageFont")
    def test_disconnected_ip(self, mock_font, mock_imagedraw, mock_image):
        mock_image.new.return_value = MagicMock()
        mock_draw = MagicMock()
        mock_imagedraw.Draw.return_value = mock_draw

        display_data = {
            "ip_address": "Disconnected",
            "rssi": None,
            "hostname": "metarmap",
        }
        display_show_status(self.mock_oled, display_data)

        first_call = mock_draw.text.call_args_list[0]
        self.assertEqual(first_call[0][1], "Disconnected")


if __name__ == "__main__":
    unittest.main()
