"""Pure utility functions — no hardware dependencies."""

import logging
import re
import socket
import subprocess
import time
from datetime import datetime
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger("metar_led")


def utc_to_local(dt_utc: Optional[datetime], tz_str: Optional[str] = None) -> Optional[datetime]:
    """Convert a UTC datetime to local time based on timezone string."""
    if dt_utc is None:
        return None
    if not tz_str:
        return dt_utc
    try:
        return dt_utc.astimezone(ZoneInfo(tz_str))
    except Exception:
        logger.warning("Invalid timezone '%s', using UTC", tz_str)
        return dt_utc


def ceiling_category(clouds: list) -> str:
    """Return flight-rules category derived from cloud layers (VFR/MVFR/IFR/LIFR)."""
    ceiling: Optional[int] = None
    for layer in clouds:
        cover = layer.get("cover")
        base = layer.get("base")
        if cover in ("BKN", "OVC") and isinstance(base, (int, float)):
            ceiling = base if ceiling is None or base < ceiling else ceiling
    if ceiling is None:
        return "VFR"
    if ceiling <= 500:
        return "LIFR"
    if ceiling <= 1000:
        return "IFR"
    if ceiling <= 3000:
        return "MVFR"
    return "VFR"


def get_ceiling_text(clouds: list) -> str:
    """Return ceiling height as a display-friendly string."""
    ceiling: Optional[int] = None
    for layer in clouds:
        cover = layer.get("cover")
        base = layer.get("base")
        if cover in ("BKN", "OVC") and isinstance(base, (int, float)):
            ceiling = base if ceiling is None or base < ceiling else ceiling
    if ceiling is None:
        return "CEIL CLR"
    if ceiling >= 10000:
        return f"CEIL {int(ceiling / 100)}"
    return f"CEIL {int(ceiling)}"


def get_visibility_text(vis_statute_miles: Optional[float]) -> str:
    """Return visibility as a display-friendly string."""
    if vis_statute_miles is None:
        return "VIS --"
    if vis_statute_miles >= 10:
        return "VIS 10+"
    if vis_statute_miles < 1:
        return f"VIS {int(vis_statute_miles * 5280)}"
    return f"VIS {int(vis_statute_miles)}"


def parse_wind_speed_direction(
    wind_speed: Optional[float], wind_direction: Optional[float]
) -> str:
    """Format wind speed and direction as a display string."""
    if wind_speed is None or wind_direction is None:
        return "WIND --/--"
    speed = int(wind_speed)
    direction = int(wind_direction)
    if speed == 0:
        return "WIND CALM"
    return f"WIND {direction:03d}/{speed:02d}"


def get_wifi_status() -> Tuple[str, Optional[int]]:
    """Return (ip_address, rssi_dbm) for current WiFi connection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "Disconnected"

    rssi: Optional[int] = None
    try:
        output = subprocess.check_output(["iwconfig"], stderr=subprocess.DEVNULL).decode()
        match = re.search(r"Signal level=(-?\d+)\s*dBm", output)
        if match:
            rssi = int(match.group(1))
    except Exception:
        pass
    return ip, rssi


def is_wifi_connected() -> bool:
    try:
        result = subprocess.check_output(["hostname", "-I"]).decode().strip()
        return bool(result)
    except Exception:
        return False


def get_hostname() -> str:
    """Return system hostname, 'unknown' on failure."""
    try:
        result = subprocess.check_output(["hostname"], stderr=subprocess.DEVNULL).decode().strip()
        return result or "unknown"
    except Exception:
        return "unknown"


def wait_for_wifi(oled) -> None:
    while not is_wifi_connected():
        print("Waiting for WiFi...")
        oled.fill(0)
        oled.text("WiFi Connecting", 0, 0, 1)
        oled.show()
        time.sleep(10)
