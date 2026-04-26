import unittest
from unittest.mock import patch, MagicMock
import sys
from datetime import datetime, timezone

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

from runmap import get_is_night

class TestNightDetection(unittest.TestCase):
    @patch('runmap.sun')
    @patch('runmap.datetime')
    def test_night_time(self, mock_datetime, mock_sun):
        # Mock a time that is clearly at night (between dusk and dawn)
        mock_now = datetime(2024, 4, 19, 2, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        
        mock_observer = MagicMock()
        mock_sun.return_value = {
            'dawn': datetime(2024, 4, 19, 6, 0, 0, tzinfo=timezone.utc),
            'dusk': datetime(2024, 4, 19, 20, 0, 0, tzinfo=timezone.utc)
        }
        
        mock_location = MagicMock()
        mock_location.observer = mock_observer
        
        result = get_is_night(mock_location)
        self.assertTrue(result, "Should be night at 2 AM")

    @patch('runmap.sun')
    @patch('runmap.datetime')
    def test_day_time(self, mock_datetime, mock_sun):
        # Mock a time that is clearly during the day
        mock_now = datetime(2024, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
        mock_datetime.now.return_value = mock_now
        
        mock_observer = MagicMock()
        mock_sun.return_value = {
            'dawn': datetime(2024, 4, 19, 6, 0, 0, tzinfo=timezone.utc),
            'dusk': datetime(2024, 4, 19, 20, 0, 0, tzinfo=timezone.utc)
        }
        
        mock_location = MagicMock()
        mock_location.observer = mock_observer
        
        result = get_is_night(mock_location)
        self.assertFalse(result, "Should be day at 12 PM")

if __name__ == "__main__":
    unittest.main()
