"""METAR data fetching and parsing from AviationWeather.gov."""

import logging
from typing import Dict, List

import requests

from config import _is_none_code
from utils import ceiling_category

logger = logging.getLogger("metar_led")

_METAR_URL = "https://aviationweather.gov/api/data/metar"


def get_metar_json(airports: List[str]) -> List[dict]:
    """Fetch METAR JSON reports for the given airport list."""
    valid_airports = [a for a in airports if a and not _is_none_code(a)]
    params = {"ids": ",".join(valid_airports), "format": "json", "taf": "false"}
    logger.debug("METAR API request: %s params=%s", _METAR_URL, params)
    try:
        response = requests.get(_METAR_URL, params=params, timeout=15)
        logger.debug("METAR API response status: %d", response.status_code)
        logger.debug("METAR API response body (first 500 chars): %s", response.text[:500])
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            reports = data
        elif isinstance(data, dict) and "data" in data:
            reports = data["data"]
        else:
            reports = []
        logger.debug("METAR API returned %d reports", len(reports))
        return reports
    except Exception as e:
        logger.error("METAR fetch error: %s", e)
        return []


def parse_metar_statuses(reports: List[dict], airports: List[str]) -> Dict[str, str]:
    """Map each airport code to its flight category derived from METAR reports."""
    cats = {a: "UNK" for a in airports}
    for rpt in reports:
        icao = next(
            (rpt.get(k) for k in ("icaoId", "station_id", "station", "icao", "id") if rpt.get(k)),
            None,
        )
        if not icao:
            continue
        icao = icao.upper()
        if _is_none_code(icao):
            continue
        cat = ceiling_category(rpt.get("clouds", []))
        if icao in cats:
            cats[icao] = cat
    return cats


def home_airport_get_sun(airport: str):
    """Fetch a METAR for the home airport and return its LocationInfo for sun calculations."""
    from astral import LocationInfo  # lazy import — astral only needed at runtime on Pi

    airport_reports = get_metar_json([airport])
    if not airport_reports:
        logger.error(
            "No METAR data for home airport %s, using default coordinates", airport
        )
        return LocationInfo(
            name=airport, region="Airport", timezone="UTC", latitude=43.65, longitude=-79.38
        )
    data = airport_reports[0]
    return LocationInfo(
        name=airport,
        region="Airport",
        timezone="UTC",
        latitude=data.get("lat", 43.65),
        longitude=data.get("lon", -79.38),
    )
