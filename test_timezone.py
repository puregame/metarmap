"""Tests for utc_to_local timezone conversion."""

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

from datetime import datetime, timezone
from runmap import utc_to_local

class TestTimezoneConversion(unittest.TestCase):
    def test_utc_to_local_no_tz(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, None)
        self.assertEqual(result, dt)

    def test_utc_to_local_utc(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, "UTC")
        self.assertEqual(result.hour, 14)

    def test_utc_to_local_est(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, "America/Toronto")
        self.assertEqual(result.hour, 10)

    def test_utc_to_local_pst(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, "America/Vancouver")
        self.assertEqual(result.hour, 7)

    def test_utc_to_local_invalid_tz(self):
        dt = datetime(2024, 4, 19, 14, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, "Invalid/Zone")
        self.assertEqual(result, dt)

    def test_utc_to_local_none(self):
        result = utc_to_local(None, "America/Toronto")
        self.assertIsNone(result)

    def test_utc_to_local_night(self):
        dt = datetime(2024, 4, 19, 2, 30, tzinfo=timezone.utc)
        result = utc_to_local(dt, "America/Toronto")
        self.assertEqual(result.hour, 22)

if __name__ == "__main__":
    unittest.main()
