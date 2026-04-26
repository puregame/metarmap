"""Shared mutable application state accessed by all modules."""

import threading
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

LED_COUNT: int = 100
current_airports: List[str] = []
strip: Any = None          # PixelStrip instance set by main() after hardware init
strip_needs_reinit: bool = False  # set True when LED_COUNT changes; main loop reinits
home_location: Any = None  # astral LocationInfo, set by main() for sun calculations
categories: Dict[str, str] = {}  # airport -> VFR/MVFR/IFR/LIFR/UNK
is_night: bool = False
refresh_event: threading.Event = threading.Event()

# Colors as (R, G, B) tuples; converted to Color objects by led_control
COLOR_MAP: Dict[str, Tuple[int, int, int]] = {
    "VFR":  (0, 140, 0),
    "MVFR": (0, 0, 140),
    "IFR":  (140, 0, 0),
    "LIFR": (120, 0, 80),
    "UNK":  (100, 100, 100),
}

COLOR_MAP_DIM: Dict[str, Tuple[int, int, int]] = {
    "VFR":  (0, 45, 0),
    "MVFR": (0, 0, 45),
    "IFR":  (45, 0, 0),
    "LIFR": (64, 0, 64),
    "UNK":  (50, 50, 50),
}

status_display: Dict = {
    "ip_address":       "Disconnected",
    "rssi":             None,
    "time":             datetime.now(),
    "last_metar":       None,
    "other_text":       None,
    "home_airport":     None,
    "home_wind_text":   "WIND --/--",
    "home_ceiling":     None,
    "home_visibility":  None,
    "cycle_time":       0,
    "timezone":         None,
}
