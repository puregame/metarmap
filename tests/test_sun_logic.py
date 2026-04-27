"""Tests for home_airport_get_sun — astral mocked via sys.modules."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from metar_api import home_airport_get_sun


class TestHomeAirportSun(unittest.TestCase):
    def setUp(self):
        self._mock_astral = MagicMock()
        sys.modules["astral"] = self._mock_astral

    def tearDown(self):
        sys.modules.pop("astral", None)

    @patch("metar_api.get_metar_json")
    def test_success_extracts_coords(self, mock_fetch):
        mock_fetch.return_value = [{"lat": 43.65, "lon": -79.38, "icaoId": "CYYZ"}]
        mock_loc = MagicMock()
        mock_loc.name = "CYYZ"
        mock_loc.latitude = 43.65
        self._mock_astral.LocationInfo.return_value = mock_loc
        result = home_airport_get_sun("CYYZ")
        self.assertEqual(result.name, "CYYZ")
        self.assertEqual(result.latitude, 43.65)

    @patch("metar_api.get_metar_json")
    def test_failure_falls_back_to_defaults(self, mock_fetch):
        mock_fetch.return_value = []
        mock_loc = MagicMock()
        self._mock_astral.LocationInfo.return_value = mock_loc
        home_airport_get_sun("CYYZ")
        kwargs = self._mock_astral.LocationInfo.call_args[1]
        self.assertEqual(kwargs["latitude"], 43.65)
        self.assertEqual(kwargs["longitude"], -79.38)


if __name__ == "__main__":
    unittest.main()
