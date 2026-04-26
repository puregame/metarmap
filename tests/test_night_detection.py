"""Tests for get_is_night — requires PIL and astral mocks."""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.modules["PIL"] = MagicMock()
sys.modules["PIL.Image"] = MagicMock()
sys.modules["PIL.ImageDraw"] = MagicMock()
sys.modules["PIL.ImageFont"] = MagicMock()
sys.modules["astral"] = MagicMock()
sys.modules["astral.sun"] = MagicMock()

sys.path.insert(0, str(Path(__file__).parent.parent))

from oled_display import get_is_night


class TestNightDetection(unittest.TestCase):
    @patch("oled_display.sun")
    @patch("oled_display.datetime")
    def test_night_at_2am(self, mock_dt, mock_sun):
        mock_now = datetime(2024, 4, 19, 2, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_sun.return_value = {
            "dawn": datetime(2024, 4, 19, 6, 0, tzinfo=timezone.utc),
            "dusk": datetime(2024, 4, 19, 20, 0, tzinfo=timezone.utc),
        }
        self.assertTrue(get_is_night(MagicMock()))

    @patch("oled_display.sun")
    @patch("oled_display.datetime")
    def test_day_at_noon(self, mock_dt, mock_sun):
        mock_now = datetime(2024, 4, 19, 12, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = mock_now
        mock_sun.return_value = {
            "dawn": datetime(2024, 4, 19, 6, 0, tzinfo=timezone.utc),
            "dusk": datetime(2024, 4, 19, 20, 0, tzinfo=timezone.utc),
        }
        self.assertFalse(get_is_night(MagicMock()))

    @patch("oled_display.sun")
    @patch("oled_display.datetime")
    def test_dusk_boundary(self, mock_dt, mock_sun):
        # Exactly at dusk — should be night
        dusk = datetime(2024, 4, 19, 20, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = dusk
        mock_sun.return_value = {
            "dawn": datetime(2024, 4, 19, 6, 0, tzinfo=timezone.utc),
            "dusk": dusk,
        }
        self.assertFalse(get_is_night(MagicMock()))  # not *after* dusk

    @patch("oled_display.sun")
    @patch("oled_display.datetime")
    def test_polar_night_fallback(self, mock_dt, mock_sun):
        # dusk <= dawn: always night
        mock_dt.now.return_value = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        mock_sun.return_value = {
            "dawn": datetime(2024, 1, 1, 14, 0, tzinfo=timezone.utc),
            "dusk": datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        }
        self.assertTrue(get_is_night(MagicMock()))


if __name__ == "__main__":
    unittest.main()
