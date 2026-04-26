"""Tests for METAR API fetching and parsing.

Only home_airport_get_sun needs astral; get_metar_json and parse_metar_statuses
are pure HTTP/dict logic and need no library mocks.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from metar_api import get_metar_json, parse_metar_statuses


class TestGetMetarJson(unittest.TestCase):
    @patch("metar_api.requests.get")
    def test_returns_list_response(self, mock_get):
        reports = [{"icaoId": "CYYZ", "clouds": []}]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = reports
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = "[]"
        self.assertEqual(get_metar_json(["CYYZ"]), reports)

    @patch("metar_api.requests.get")
    def test_returns_dict_data_response(self, mock_get):
        reports = [{"icaoId": "CYYZ"}]
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"data": reports}
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = "{}"
        self.assertEqual(get_metar_json(["CYYZ"]), reports)

    @patch("metar_api.requests.get", side_effect=Exception("timeout"))
    def test_returns_empty_on_error(self, _):
        self.assertEqual(get_metar_json(["CYYZ"]), [])

    @patch("metar_api.requests.get")
    def test_none_airports_excluded_from_query(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = "[]"
        get_metar_json(["CYYZ", "NONE"])
        call_params = mock_get.call_args[1]["params"]
        self.assertNotIn("NONE", call_params["ids"])
        self.assertIn("CYYZ", call_params["ids"])

    @patch("metar_api.requests.get")
    def test_empty_airports_excluded(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = []
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = "[]"
        get_metar_json(["CYYZ", ""])
        self.assertEqual(mock_get.call_args[1]["params"]["ids"], "CYYZ")

    @patch("metar_api.requests.get")
    def test_unknown_response_format_returns_empty(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {"unexpected": True}
        mock_get.return_value.raise_for_status = MagicMock()
        mock_get.return_value.text = "{}"
        self.assertEqual(get_metar_json(["CYYZ"]), [])


class TestParseMetarStatuses(unittest.TestCase):
    def test_vfr_airport(self):
        reports = [{"icaoId": "CYYZ", "clouds": [{"cover": "BKN", "base": 5000}]}]
        self.assertEqual(parse_metar_statuses(reports, ["CYYZ"])["CYYZ"], "VFR")

    def test_lifr_airport(self):
        reports = [{"icaoId": "CYYZ", "clouds": [{"cover": "OVC", "base": 200}]}]
        self.assertEqual(parse_metar_statuses(reports, ["CYYZ"])["CYYZ"], "LIFR")

    def test_unknown_when_not_in_reports(self):
        self.assertEqual(parse_metar_statuses([], ["CYYZ"])["CYYZ"], "UNK")

    def test_none_icao_skipped(self):
        reports = [{"icaoId": "NONE", "clouds": [{"cover": "OVC", "base": 100}]}]
        cats = parse_metar_statuses(reports, ["CYYZ", "NONE"])
        self.assertEqual(cats["NONE"], "UNK")

    def test_icao_uppercased(self):
        reports = [{"icaoId": "cyyz", "clouds": []}]
        self.assertEqual(parse_metar_statuses(reports, ["CYYZ"])["CYYZ"], "VFR")

    def test_alternate_icao_field_names(self):
        for key in ("station_id", "station", "icao", "id"):
            with self.subTest(key=key):
                reports = [{"clouds": [], key: "CYYZ"}]
                self.assertEqual(parse_metar_statuses(reports, ["CYYZ"])["CYYZ"], "VFR")

    def test_airport_absent_from_reports_stays_unk(self):
        reports = [{"icaoId": "KJFK", "clouds": []}]
        cats = parse_metar_statuses(reports, ["CYYZ", "KJFK"])
        self.assertEqual(cats["CYYZ"], "UNK")
        self.assertEqual(cats["KJFK"], "VFR")

    def test_multiple_airports(self):
        reports = [
            {"icaoId": "CYYZ", "clouds": [{"cover": "OVC", "base": 800}]},
            {"icaoId": "KJFK", "clouds": []},
        ]
        cats = parse_metar_statuses(reports, ["CYYZ", "KJFK"])
        self.assertEqual(cats["CYYZ"], "IFR")
        self.assertEqual(cats["KJFK"], "VFR")


class TestHomeAirportGetSun(unittest.TestCase):
    """These tests need astral available (mocked via sys.modules)."""

    def setUp(self):
        self._mock_astral = MagicMock()
        sys.modules["astral"] = self._mock_astral

    def tearDown(self):
        sys.modules.pop("astral", None)

    @patch("metar_api.get_metar_json")
    def test_success_uses_metar_coords(self, mock_fetch):
        from metar_api import home_airport_get_sun
        mock_fetch.return_value = [{"lat": 43.65, "lon": -79.38, "icaoId": "CYYZ"}]
        mock_loc = MagicMock()
        self._mock_astral.LocationInfo.return_value = mock_loc
        result = home_airport_get_sun("CYYZ")
        self.assertIs(result, mock_loc)
        kwargs = self._mock_astral.LocationInfo.call_args[1]
        self.assertEqual(kwargs["latitude"], 43.65)
        self.assertEqual(kwargs["longitude"], -79.38)

    @patch("metar_api.get_metar_json")
    def test_failure_uses_default_coords(self, mock_fetch):
        from metar_api import home_airport_get_sun
        mock_fetch.return_value = []
        mock_loc = MagicMock()
        self._mock_astral.LocationInfo.return_value = mock_loc
        home_airport_get_sun("CYYZ")
        kwargs = self._mock_astral.LocationInfo.call_args[1]
        self.assertEqual(kwargs["latitude"], 43.65)
        self.assertEqual(kwargs["longitude"], -79.38)

    @patch("metar_api.get_metar_json")
    def test_metar_missing_coords_uses_defaults(self, mock_fetch):
        from metar_api import home_airport_get_sun
        mock_fetch.return_value = [{"icaoId": "CYYZ", "clouds": []}]
        mock_loc = MagicMock()
        self._mock_astral.LocationInfo.return_value = mock_loc
        home_airport_get_sun("CYYZ")
        kwargs = self._mock_astral.LocationInfo.call_args[1]
        self.assertEqual(kwargs["latitude"], 43.65)
        self.assertEqual(kwargs["longitude"], -79.38)


if __name__ == "__main__":
    unittest.main()
