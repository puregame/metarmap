"""Config file loading and validation."""

import json
import logging
import re
from pathlib import Path
from typing import List, Optional, Tuple

import state

logger = logging.getLogger("metar_led")

AIRPORT_FILE = Path(__file__).with_name("config.json")

_ICAO_RE = re.compile(r"^[A-Z0-9]{4}$")


def _is_valid_icao(code: str) -> bool:
    return isinstance(code, str) and bool(_ICAO_RE.match(code))


def _is_none_code(code: str) -> bool:
    return isinstance(code, str) and code.upper() == "NONE"


def validate_config(data: dict) -> None:
    """Validate config dict, raising ValueError listing all problems found."""
    errors: List[str] = []

    airports = data.get("airports")
    if not isinstance(airports, list):
        errors.append("'airports' must be a list of ICAO codes")
    else:
        if len(airports) == 0:
            errors.append("'airports' must contain at least one airport")
        for i, ap in enumerate(airports):
            if not _is_valid_icao(ap) and not _is_none_code(ap):
                errors.append(
                    f"'airports[{i}]' is '{ap}', expected a valid 4-character ICAO code (e.g. CYYZ) or 'NONE'"
                )

    home = data.get("home")
    if home:
        if not _is_valid_icao(home) and not _is_none_code(home):
            errors.append(f"'home' is '{home}', expected a valid 4-character ICAO code or 'NONE'")
        elif isinstance(airports, list) and home and home.upper() != "NONE" and home not in airports:
            errors.append(f"'home' ({home}) not found in airports list")

    def _check_color_dict(field: str, colors: object) -> None:
        if not isinstance(colors, dict):
            errors.append(f"'{field}' must be a dictionary")
            return
        for key, val in colors.items():
            if not isinstance(val, (list, tuple)) or len(val) != 3:
                errors.append(f"'{field}.{key}' must be an array of 3 values, got {val!r}")
            else:
                for vi, v in enumerate(val):
                    if not isinstance(v, int) or v < 0 or v > 255:
                        errors.append(f"'{field}.{key}[{vi}]' is {v!r}, expected integer 0-255")

    if (colors := data.get("colors")) is not None:
        _check_color_dict("colors", colors)
    if (dim_colors := data.get("dim_colors")) is not None:
        _check_color_dict("dim_colors", dim_colors)

    num_leds = data.get("num_leds")
    if num_leds is not None:
        if not isinstance(num_leds, int) or num_leds <= 0:
            errors.append(f"'num_leds' is {num_leds!r}, expected a positive integer")

    if errors:
        formatted = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"Configuration errors:\n{formatted}")


def load_config() -> Tuple[List[str], str, Optional[str]]:
    """Load, validate, and apply config.json; updates shared state globals."""
    try:
        data = json.loads(AIRPORT_FILE.read_text())
        validate_config(data)
        airports = data.get("airports", [])
        home = data.get("home", "")
        timezone_str = data.get("timezone", None)
        if data.get("num_leds"):
            state.LED_COUNT = data["num_leds"]
        if data.get("colors"):
            logger.debug("Loading colors from config")
            state.COLOR_MAP = {k: tuple(v) for k, v in data["colors"].items()}
        if data.get("dim_colors"):
            logger.debug("Loading dim colors from config")
            state.COLOR_MAP_DIM = {k: tuple(v) for k, v in data["dim_colors"].items()}
        state.current_airports = airports
        if not airports:
            raise ValueError("No airports in JSON")
        return airports, home, timezone_str
    except Exception as exc:
        logger.exception("Problem loading %s: %s", AIRPORT_FILE, exc)
        raise
