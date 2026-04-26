"""Tests for get_is_night — requires PIL and astral mocks."""

import sys
import unittest
from datetime import datetime, timedelta, timezone
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
    def test_west_of_utc_day(self, mock_dt, mock_sun):
        # Reproduces the CYSB/Sudbury bug: LocationInfo timezone="UTC" causes
        # astral to report dusk (00:58 UTC) BEFORE dawn (09:43 UTC) on the same
        # UTC calendar date. At 14:37 UTC the old code returned True (night).
        now = datetime(2026, 4, 26, 14, 37, tzinfo=timezone.utc)
        mock_dt.now.return_value = now

        # Simulate astral output for UTC-anchored location:
        # dusk always falls just after midnight UTC (prev evening local),
        # dawn falls mid-morning UTC.
        def make_times(date):
            return {
                "dawn": datetime(date.year, date.month, date.day, 9, 43, tzinfo=timezone.utc),
                "dusk": datetime(date.year, date.month, date.day, 0, 58, tzinfo=timezone.utc),
            }

        mock_sun.side_effect = lambda obs, date, tzinfo: make_times(date)
        self.assertFalse(get_is_night(MagicMock()))  # 14:37 UTC is daytime

    @patch("oled_display.sun")
    @patch("oled_display.datetime")
    def test_west_of_utc_night_after_dusk(self, mock_dt, mock_sun):
        # 01:30 UTC April 27 = 9:30 PM EDT April 26, after civil dusk (~01:00 UTC)
        now = datetime(2026, 4, 27, 1, 30, tzinfo=timezone.utc)
        mock_dt.now.return_value = now

        def make_times(date):
            return {
                "dawn": datetime(date.year, date.month, date.day, 9, 43, tzinfo=timezone.utc),
                "dusk": datetime(date.year, date.month, date.day, 1,  0, tzinfo=timezone.utc),
            }

        mock_sun.side_effect = lambda obs, date, tzinfo: make_times(date)
        self.assertTrue(get_is_night(MagicMock()))   # after dusk → night

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
