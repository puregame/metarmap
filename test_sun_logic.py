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

from runmap import home_airport_get_sun

class TestHomeAirportSun(unittest.TestCase):
    @patch('runmap.get_metar_json')
    def test_home_airport_get_sun_success(self, mock_get_metar):
        # Mock a successful METAR response with real dict to avoid MagicMock attribute issues
        mock_report = {'lat': 43.65, 'lon': -79.38, 'icaoId': 'CYYZ'}
        mock_get_metar.return_value = [mock_report]
        
        # We need to mock the return value of LocationInfo constructor to behave like a real object
        mock_location = MagicMock()
        mock_location.name = "CYYZ"
        mock_location.latitude = 43.65
        mock_location.longitude = -79.38
        mock_location.observer = MagicMock()
        
        with patch('runmap.LocationInfo', return_value=mock_location):
            result = home_airport_get_sun("CYYZ")
            self.assertEqual(result.name, "CYYZ")
            self.assertEqual(result.latitude, 43.65)

    @patch('runmap.get_metar_json')
    @patch('runmap.LocationInfo')
    def test_home_airport_get_sun_failure(self, mock_location_info, mock_get_metar):
        # Mock an empty METAR response - should now return default coordinates instead of crashing
        mock_get_metar.return_value = []
        
        mock_location = MagicMock()
        mock_location.name = "CYYZ"
        mock_location.latitude = 43.65
        mock_location.longitude = -79.38
        mock_location_info.return_value = mock_location
        
        result = home_airport_get_sun("CYYZ")
        # Should use default coordinates (43.65, -79.38) when METAR data is unavailable
        mock_location_info.assert_called_once()
        call_kwargs = mock_location_info.call_args[1]
        self.assertEqual(call_kwargs['latitude'], 43.65)
        self.assertEqual(call_kwargs['longitude'], -79.38)

if __name__ == "__main__":
    unittest.main()





