"""LED METAR Map - v5.0 (ceiling-based category + web UI + LED cycle + guided configure)
=================================================================================
The AviationWeather.gov JSON feed no longer includes `flight_category`.
This version derives VFR/MVFR/IFR/LIFR from the **cloud ceiling** in each
METAR:

* **Ceiling** = lowest `BKN` or `OVC` layer. If none, treat as clear.
* **Category rules**  (FAA/NOAA standard):
  * VFR >= 3 000 ft
  * MVFR 1000 - 2 999 ft
  * IFR 500 - 999 ft
  * LIFR < 500 ft

Everything else in v4.0 remains unchanged, plus new features:

* `--web` flag enables built-in web server on port 8080
* LED Cycle feature maps each LED to any airport code
* Guided LED Configure: start from web UI, flashes LEDs sequentially,
  user types airport code for each flashing LED, config saves immediately
* Local timezone support for OLED and web display

Run examples
────────────
```bash
# Real LEDs on Pi
sudo python3 runmap.py

# Laptop test
python3 runmap.py --dry-run

# With web UI (access at http://<pi-ip>:8080)
python3 runmap.py --web
```
"""

from __future__ import annotations

import argparse
import socket
import json
import logging
import sys
import subprocess
import signal
import re
import time
import threading
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from functools import partial
from http.server import HTTPServer, BaseHTTPRequestHandler

from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import requests

# ─────────── Imports for display ───────────
import board
from PIL import Image, ImageDraw, ImageFont
import adafruit_ssd1306

from astral.sun import sun
from astral import LocationInfo

# ─────────── Try importing real LED driver, else fall back to mock ───────────
HARDWARE_AVAILABLE = False
try:
    from rpi_ws281x import PixelStrip, Color  # type: ignore
    HARDWARE_AVAILABLE = True
except (ModuleNotFoundError, RuntimeError):
    class Color(tuple):
        def __new__(cls, r: int, g: int, b: int):
            return super().__new__(cls, (r, g, b))
        def __repr__(self):
            return f"Color(r={self[0]}, g={self[1]}, b={self[2]})"

    class PixelStrip:  # mock
        def __init__(self, num: int, *args, **kwargs):
            self._num = num
            self._pixels: List[Tuple[int, int, int]] = [(0, 0, 0)] * num
        def numPixels(self):
            return self._num
        def setPixelColor(self, i: int, color: Color):
            if 0 <= i < self._num:
                self._pixels[i] = color
        def show(self):
            print("LEDs:", " ".join(f"{i}:{c}" for i, c in enumerate(self._pixels)))
        def begin(self):
            print("[MOCK] PixelStrip initialised with", self._num, "pixels")

# ─────────── Cmd‑line args ──────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="LED METAR Map")
parser.add_argument("--dry-run", action="store_true", help="Force simulation mode even on non‑Pi")
parser.add_argument("--test_displays", action="store_true", help="Output alternating colors on LEDs")
parser.add_argument("--web", action="store_true", help="Enable built-in web server on port 8080")
args = parser.parse_args()
SIMULATION = args.dry_run or not HARDWARE_AVAILABLE

# ───────────────────── LED Config ───────────────────────────────────────────────
LED_COUNT = 100
LED_PIN = 18
LED_FREQ_HZ = 800_000
LED_DMA = 10
LED_BRIGHTNESS = 65
LED_INVERT = False
LED_CHANNEL = 0

AIRPORT_FILE = Path(__file__).with_name("config.json")
LOG_FILE = Path(__file__).with_name("metar_led.log")
UPDATE_INTERVAL = 60  # refresh data every 60 seconds

# ───────────────────── Global State ─────────────────────────────────────────────
led_cycle_map: List[str] = []
led_cycle_lock = threading.Lock()
current_airports: List[str] = []

# Configure mode globals
configure_mode = False
configure_lock = threading.Lock()

COLOR_MAP: Dict[str, Color] = {  # NOTE: colors are in RGB format!!
    "VFR": Color(0, 140, 0),
    "MVFR": Color(0, 0, 140),
    "IFR": Color(140, 0, 0),
    "LIFR": Color(120, 0, 80),
    "UNK": Color(100, 100, 100),
}

COLOR_MAP_DIM: Dict[str, Color] = {
    "VFR": Color(0, 45, 0),
    "MVFR": Color(0, 0, 45),
    "IFR": Color(45, 0, 0),
    "LIFR": Color(64, 0, 64),
    "UNK": Color(50, 50, 50),
}

# ───────────────────── Display Config ───────────────────────────────────────────────
OLED_WIDTH = 128
OLED_HEIGHT = 32

# Load font for display
font = ImageFont.load_default(size=11)
font_large = ImageFont.load_default(size=16)

# ───────────────────── Logger ───────────────────────────────────────────────
logger = logging.getLogger("metar_led")
logger.setLevel(logging.DEBUG)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
for h in (logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)):
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.info("hardware available: %s", HARDWARE_AVAILABLE)
logger.info("Simulation mode: %s", SIMULATION)

# ───────────────────── Global Vars ──────────────────────────────────────────────
status_display = {
    'ip_address': 'Disconnected',
    'rssi': None,
    'time': datetime.now(),
    'last_metar': None,
    'other_text': None,
    'home_airport': None,
    'home_wind_text': 'WIND --/--',
    'home_ceiling': None,
    'home_visibility': None,
    'cycle_time': 0,
    'timezone': None
}  # for display on OLED

# ───────────────────── Helpers ──────────────────────────────────────────────

_ICAO_RE = re.compile(r'^[A-Z0-9]{4}$')


def _is_valid_icao(code: str) -> bool:
    return isinstance(code, str) and bool(_ICAO_RE.match(code))


def _is_none_code(code: str) -> bool:
    return isinstance(code, str) and code.upper() == "NONE"


def validate_config(data: dict) -> None:
    errors: List[str] = []

    airports = data.get("airports")
    if not isinstance(airports, list):
        errors.append("'airports' must be a list of ICAO codes")
    else:
        if len(airports) == 0:
            errors.append("'airports' must contain at least one airport")
        for i, ap in enumerate(airports):
            if not _is_valid_icao(ap) and not _is_none_code(ap):
                errors.append(f"'airports[{i}]' is '{ap}', expected a valid 4-character ICAO code (e.g. CYYZ) or 'NONE'")

    home = data.get("home")
    if home:
        if not _is_valid_icao(home) and not _is_none_code(home):
            errors.append(f"'home' is '{home}', expected a valid 4-character ICAO code or 'NONE'")
        elif isinstance(airports, list) and home and home.upper() != "NONE" and home not in airports:
            errors.append(f"'home' ({home}) not found in airports list")

    colors = data.get("colors")
    if colors is not None:
        if not isinstance(colors, dict):
            errors.append("'colors' must be a dictionary")
        else:
            for key, val in colors.items():
                if not isinstance(val, (list, tuple)) or len(val) != 3:
                    errors.append(f"'colors.{key}' must be an array of 3 values, got {val!r}")
                else:
                    for vi, v in enumerate(val):
                        if not isinstance(v, int) or v < 0 or v > 255:
                            errors.append(f"'colors.{key}[{vi}]' is {v!r}, expected integer 0-255")

    dim_colors = data.get("dim_colors")
    if dim_colors is not None:
        if not isinstance(dim_colors, dict):
            errors.append("'dim_colors' must be a dictionary")
        else:
            for key, val in dim_colors.items():
                if not isinstance(val, (list, tuple)) or len(val) != 3:
                    errors.append(f"'dim_colors.{key}' must be an array of 3 values, got {val!r}")
                else:
                    for vi, v in enumerate(val):
                        if not isinstance(v, int) or v < 0 or v > 255:
                            errors.append(f"'dim_colors.{key}[{vi}]' is {v!r}, expected integer 0-255")

    num_leds = data.get("num_leds")
    if num_leds is not None:
        if not isinstance(num_leds, int) or num_leds <= 0:
            errors.append(f"'num_leds' is {num_leds!r}, expected a positive integer")

    led_cycle = data.get("led_cycle")
    if led_cycle is not None:
        if not isinstance(led_cycle, list):
            errors.append("'led_cycle' must be a list")
        else:
            for i, entry in enumerate(led_cycle):
                if entry != "" and not _is_valid_icao(entry) and not _is_none_code(entry):
                    errors.append(f"'led_cycle[{i}]' is '{entry}', expected empty string, 'NONE', or valid 4-character ICAO code")

    if errors:
        formatted = "\n".join(f"  - {e}" for e in errors)
        raise ValueError(f"Configuration errors:\n{formatted}")


def load_config() -> Tuple[List[str], str, Optional[str]]:
    global led_cycle_map, current_airports
    try:
        data = json.loads(AIRPORT_FILE.read_text())
        validate_config(data)
        airports = data.get("airports", [])
        home = data.get('home', '')
        timezone_str = data.get('timezone', None)
        if data.get("num_leds"):
            global LED_COUNT
            LED_COUNT = data["num_leds"]
        if data.get("colors"):
            global COLOR_MAP
            logger.debug("old colors: %s", COLOR_MAP)
            COLOR_MAP = {k: Color(*v) for k, v in data["colors"].items()}
            logger.debug("Loading colors from config: %s", COLOR_MAP)
        if data.get("dim_colors"):
            global COLOR_MAP_DIM
            logger.debug("old dim colors: %s", COLOR_MAP_DIM)
            COLOR_MAP_DIM = {k: Color(*v) for k, v in data["dim_colors"].items()}
            logger.debug("Loading dim colors from config: %s", COLOR_MAP_DIM)
        led_cycle = data.get("led_cycle", [])
        if led_cycle:
            with led_cycle_lock:
                led_cycle_map = led_cycle[:LED_COUNT]
            logger.info("Loaded led_cycle with %d entries from config", len(led_cycle_map))
        else:
            with led_cycle_lock:
                led_cycle_map = airports[:LED_COUNT] + [""] * (LED_COUNT - len(airports[:LED_COUNT]))
            logger.info("Initialized led_cycle from airports list (%d entries)", len(led_cycle_map))
        current_airports = airports
        if not airports:
            raise ValueError("No airports in JSON")
        return airports, home, timezone_str
    except Exception as exc:
        logger.exception("Problem loading %s: %s", AIRPORT_FILE, exc)
        raise


def utc_to_local(dt_utc: datetime, tz_str: Optional[str] = None) -> datetime:
    """Convert a UTC datetime to local time based on timezone string."""
    if dt_utc is None:
        return dt_utc
    if not tz_str:
        return dt_utc
    try:
        tz = ZoneInfo(tz_str)
        return dt_utc.astimezone(tz)
    except (KeyError, Exception):
        logger.warning("Invalid timezone '%s', using UTC", tz_str)
        return dt_utc


def ceiling_category(clouds: List[dict]) -> str:
    """Return flight‑rules category from cloud layers list."""
    ceiling: Optional[int] = None  # feet
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


def get_ceiling_text(clouds: List[dict]) -> str:
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
        return f"CEIL {int(ceiling/100)}"
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


def get_wifi_status() -> Tuple[str, Optional[int]]:
    # Get IP address
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
    except Exception:
        ip = "Disconnected"

    # Get RSSI (signal strength)
    rssi = None
    try:
        output = subprocess.check_output(["iwconfig"], stderr=subprocess.DEVNULL).decode()
        match = re.search(r"Signal level=(-?\d+)\s*dBm", output)
        if match:
            rssi = int(match.group(1))
    except Exception:
        pass
    return ip, rssi


def get_metar_json(airports: List[str]) -> List[dict]:
    url = "https://aviationweather.gov/api/data/metar"
    params = {
        "ids": ",".join(airports),
        "format": "json",
        "taf": "false",
    }
    try:
        response = requests.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            reports = data
        elif isinstance(data, dict) and "data" in data:
            reports = data["data"]
        else:
            reports = []
        return reports
    except Exception as e:
        logger.error("METAR fetch error: %s", e)
        return []


def home_airport_get_sun(airport: str) -> LocationInfo:
    airport_reports = get_metar_json([airport])
    if not airport_reports:
        logger.error("No METAR data available for home airport %s, using default coordinates", airport)
        return LocationInfo(name=airport, region="Airport", timezone="UTC", latitude=43.65, longitude=-79.38)

    airport_data = airport_reports[0]
    return LocationInfo(
        name=airport,
        region="Airport",
        timezone="UTC",
        latitude=airport_data.get('lat', 43.65),
        longitude=airport_data.get('lon', -79.38)
    )


def parse_wind_speed_direction(wind_speed: Optional[float], wind_direction: Optional[float]) -> str:
    """Parse wind speed and direction into a display-friendly string."""
    if wind_speed is None or wind_direction is None:
        return "WIND --/--"

    speed = int(wind_speed)
    direction = int(wind_direction)

    if speed == 0:
        return "WIND CALM"

    return f"WIND {direction:03d}/{speed:02d}"


def parse_metar_statuses(reports: List[dict], airports: List[str]) -> Dict[str, str]:
    cats = {a: "UNK" for a in airports}
    for rpt in reports:
        icao = next((rpt.get(k) for k in ("icaoId", "station_id", "station", "icao", "id") if rpt.get(k)), None)
        if not icao:
            continue
        icao = icao.upper()
        if _is_none_code(icao):
            continue
        cat = ceiling_category(rpt.get("clouds", []))
        if icao in cats:
            cats[icao] = cat
    return cats


def category_to_color(cat: str, night_mode: bool = False) -> Color:
    if night_mode:
        return COLOR_MAP_DIM.get(cat, COLOR_MAP_DIM["UNK"])
    return COLOR_MAP.get(cat, COLOR_MAP["UNK"])


def led_update(strip: PixelStrip, airports: List[str], cats: Dict[str, str], night: bool = False):
    for i, icao in enumerate(airports):
        if i >= strip.numPixels():
            break
        if not icao or _is_none_code(icao):
            strip.setPixelColor(i, Color(0, 0, 0))
        else:
            strip.setPixelColor(i, category_to_color(cats.get(icao, "UNK"), night_mode=night))
            logger.info("%s > %s", icao, cats.get(icao, "UNK"))
    strip.show()


def led_clear(strip: PixelStrip):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def led_set_single(strip: PixelStrip, number: int, color: Color):
    strip.setPixelColor(number, color)
    strip.show()


def led_set_all(strip: PixelStrip, color: Color):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
    strip.show()


def display_show_airport(oled, airport: str):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
    draw.text((0, 0), airport, font=font_large, fill=255)
    oled.image(image)
    oled.show()


def cleanup(oled, strip, signum=None, frame=None):
    logger.info("Turning off all LEDs and clearing OLED screen")
    led_clear(strip)
    oled.fill(0)
    oled.show()
    sys.exit(0)


def get_is_night(location: LocationInfo) -> bool:
    now = datetime.now(timezone.utc)
    sun_times = sun(location.observer, date=now.date(), tzinfo=timezone.utc)
    logger.debug("home dawn: %s", sun_times['dawn'])
    logger.debug("home dusk: %s", sun_times['dusk'])
    logger.debug("now: %s", now)

    if sun_times['dusk'] > sun_times['dawn']:
        return now < sun_times['dawn'] or now > sun_times['dusk']

    return True


def is_wifi_connected():
    try:
        result = subprocess.check_output(["hostname", "-I"]).decode().strip()
        return bool(result)
    except Exception:
        return False


def wait_for_wifi(oled):
    while not is_wifi_connected():
        print("Waiting for WiFi...")
        oled.fill(0)
        oled.text("WiFi Connecting", 0, 0, 1)
        oled.show()
        time.sleep(10)


def update_display_normal(oled, display_data: dict):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)

    rssi = display_data.get("rssi")
    bar_count = 0
    if rssi is not None:
        if rssi >= -60:
            bar_count = 4
        elif rssi >= -70:
            bar_count = 3
        elif rssi >= -80:
            bar_count = 2
        else:
            bar_count = 1

    bar_x = oled.width - 20
    bar_y_base = 12
    bar_width = 2
    bar_spacing = 3
    bar_max_height = 12

    for i in range(4):
        bar_height = (i + 1) * 3
        x = bar_x + i * bar_spacing
        y = bar_y_base - bar_height
        fill = 255 if i < bar_count else 0
        draw.rectangle([x, y, x + bar_width, bar_y_base], fill=fill)

    if rssi is None:
        x1 = bar_x - 2
        x2 = bar_x + (3 * bar_spacing) + bar_width + 2
        y1 = bar_y_base
        y2 = bar_y_base - bar_max_height
        draw.line([x1, y1, x2, y2], fill=255, width=1)
        draw.line([x1, y2, x2, y1], fill=255, width=1)

    tz_str = display_data.get('timezone')
    wx_local = utc_to_local(display_data['last_metar'], tz_str) if display_data['last_metar'] else None
    now_local = utc_to_local(display_data['time'], tz_str)
    wx_time = wx_local.strftime('%H:%M') if wx_local else 'N/A'
    now_time = now_local.strftime('%H:%M')

    wx_text = f"WX: {wx_time}"
    now_text = f"{now_time}"
    wifi_text = f"{display_data['ip_address']}"

    cycle_time = display_data.get('cycle_time', 0)
    if cycle_time:
        cycle_index = int(time.time()) % 12 // 3
    else:
        cycle_index = 0

    if display_data.get('other_text'):
        top_text = display_data['other_text']
    else:
        home = display_data.get('home_airport', '')
        home_wind = display_data.get('home_wind_text', 'WIND --/--')
        home_ceiling = display_data.get('home_ceiling', 'CEIL --')
        home_vis = display_data.get('home_visibility', 'VIS --')
        top_texts = [
            f"HOME: {home}",
            home_wind,
            home_ceiling,
            home_vis,
        ]
        top_text = top_texts[cycle_index % len(top_texts)]

    draw.text((0, 0), top_text, font=font_large, fill=255)
    draw.text((0, 11), wx_text, font=font, fill=255)
    draw.text((0, 22), now_text, font=font, fill=255)

    bbox = draw.textbbox((0, 0), wifi_text, font=font)
    wifi_text_width = bbox[2] - bbox[0]
    draw.text((oled.width - wifi_text_width, 22), wifi_text, font=font, fill=255)

    oled.image(image)
    oled.show()


# ───────────────────── Web Server ──────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>METAR Map Control</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: monospace; background: #1a1a2e; color: #e0e0e0; padding: 20px; }
h1 { text-align: center; color: #00ff88; margin-bottom: 20px; font-size: 1.5em; }
h2 { color: #00ccff; margin: 15px 0 10px; font-size: 1.2em; border-bottom: 1px solid #333; padding-bottom: 5px; }
#status { background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
#status p { margin: 4px 0; }
#status span { color: #00ff88; }
.config-header { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; flex-wrap: wrap; }
.config-info { color: #00ff88; font-size: 0.9em; }
.btn { display: inline-block; padding: 8px 20px; border: none; border-radius: 5px; font-family: monospace; font-size: 0.9em; cursor: pointer; font-weight: bold; }
.btn-primary { background: #00ff88; color: #1a1a2e; }
.btn-primary:hover { background: #00cc6a; }
.btn-primary:active { background: #00aa55; }
.btn-danger { background: #ff4444; color: #fff; }
.btn-danger:hover { background: #cc3333; }
.btn:disabled { background: #555; color: #888; cursor: not-allowed; }
.led-grid { display: grid; grid-template-columns: repeat(10, 1fr); gap: 6px; max-width: 100%; }
.led-cell { background: #16213e; padding: 4px; border-radius: 4px; text-align: center; }
.led-cell label { display: block; font-size: 0.7em; color: #888; margin-bottom: 2px; }
.led-cell input { width: 100%; background: #0f3460; border: 1px solid #333; color: #e0e0e0; padding: 4px 2px; text-align: center; font-size: 0.8em; font-family: monospace; border-radius: 3px; }
.led-cell input:focus { outline: none; border-color: #00ff88; }
.led-cell.active { border: 2px solid #00ff88; background: #1a3a2e; }
.led-cell.active input { border-color: #00ff88; background: #0a2a1e; }
#save-btn { display: block; margin: 20px auto; padding: 10px 30px; background: #00ff88; color: #1a1a2e; border: none; border-radius: 5px; font-family: monospace; font-size: 1em; cursor: pointer; font-weight: bold; }
#save-btn:hover { background: #00cc6a; }
#save-btn:active { background: #00aa55; }
#msg { text-align: center; margin-top: 10px; min-height: 20px; }
.msg-ok { color: #00ff88; }
.msg-err { color: #ff4444; }
</style>
</head>
<body>
<h1>METAR Map Control</h1>
<h2>Status</h2>
<div id="status">
<p>Loading...</p>
</div>
<h2>LED Cycle</h2>
<div id="configure-controls" style="display:none;">
<div class="config-header">
<span class="config-info" id="configure-info">Configuring...</span>
<button class="btn btn-danger" onclick="stopConfigure()">Cancel Configuration</button>
</div>
</div>
<p style="margin-bottom:10px;font-size:0.85em;color:#888;">Each LED position maps to an airport code. Leave blank to keep LED off.</p>
<div class="led-grid" id="led-grid"></div>
<button id="save-btn" onclick="saveLedCycle()">Save LED Cycle</button>
<div id="msg"></div>
<script>
var LED_COUNT = 100;
var configureActive = false;
var configureIndex = 0;
function setStatus(data) {
    var el = document.getElementById('status');
    if (!data) { el.innerHTML = '<p>Error loading status</p>'; return; }
    var html = '';
    if (data.airports) html += '<p>Airports: <span>' + data.airports.length + '</span></p>';
    if (data.home) html += '<p>Home: <span>' + data.home + '</span></p>';
    if (data.timezone) html += '<p>Timezone: <span>' + data.timezone + '</span></p>';
    if (data.last_metar) html += '<p>Last METAR: <span>' + data.last_metar + '</span></p>';
    if (data.ip_address) html += '<p>IP: <span>' + data.ip_address + '</span></p>';
    if (data.led_count) html += '<p>LEDs: <span>' + data.led_count + '</span></p>';
    el.innerHTML = html;
}
function buildGrid(ledCycle) {
    var grid = document.getElementById('led-grid');
    grid.innerHTML = '';
    for (var i = 0; i < LED_COUNT; i++) {
        var cell = document.createElement('div');
        cell.className = 'led-cell';
        cell.id = 'cell-' + i;
        var label = document.createElement('label');
        label.textContent = 'LED ' + i;
        var inp = document.createElement('input');
        inp.type = 'text';
        inp.maxLength = 4;
        inp.id = 'led-' + i;
        inp.value = (ledCycle[i] || '');
        inp.placeholder = '-----';
        inp.onkeydown = handleConfigKey;
        cell.appendChild(label);
        cell.appendChild(inp);
        grid.appendChild(cell);
    }
}
function startConfigure() {
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/configure/start', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
        if (xhr.status === 200) {
            configureActive = true;
            document.getElementById('configure-controls').style.display = 'block';
            document.getElementById('save-btn').disabled = true;
            focusNextConfigureInput();
        } else {
            showMessage('Failed to start configure', 'err');
        }
    };
    xhr.onerror = function() { showMessage('Network error', 'err'); };
    xhr.send('{}');
}
function stopConfigure() {
    configureActive = false;
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/configure/stop', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
        document.getElementById('configure-controls').style.display = 'none';
        document.getElementById('save-btn').disabled = false;
        clearAllHighlights();
        showMessage('Configuration cancelled', 'ok');
    };
    xhr.onerror = function() { showMessage('Network error', 'err'); };
    xhr.send('{}');
}
function assignAirport() {
    var inp = document.getElementById('led-' + configureIndex);
    var airport = inp.value.trim().toUpperCase();
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/configure/assign', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
        if (xhr.status === 200) {
            showMessage('Assigned ' + (airport || '(blank)') + ' to LED ' + configureIndex, 'ok');
            configureIndex++;
            if (configureIndex >= LED_COUNT) {
                stopConfigure();
            } else {
                focusNextConfigureInput();
            }
        } else {
            showMessage('Error assigning airport', 'err');
        }
    };
    xhr.onerror = function() { showMessage('Network error', 'err'); };
    xhr.send(JSON.stringify({index: configureIndex, airport: airport}));
}
function handleConfigKey(e) {
    if (e.key === 'Enter' && configureActive) {
        e.preventDefault();
        assignAirport();
    }
}
function focusNextConfigureInput() {
    clearAllHighlights();
    if (configureIndex < LED_COUNT) {
        var inp = document.getElementById('led-' + configureIndex);
        var cell = document.getElementById('cell-' + configureIndex);
        if (inp) {
            inp.focus();
            inp.select();
        }
        if (cell) {
            cell.classList.add('active');
        }
        updateConfigureInfo();
    }
}
function clearAllHighlights() {
    for (var i = 0; i < LED_COUNT; i++) {
        var cell = document.getElementById('cell-' + i);
        if (cell) cell.classList.remove('active');
    }
}
function updateConfigureInfo() {
    var info = document.getElementById('configure-info');
    if (info) {
        info.textContent = 'LED ' + configureIndex + ' of ' + LED_COUNT + ': enter airport code and press Enter';
    }
}
function saveLedCycle() {
    var map = [];
    for (var i = 0; i < LED_COUNT; i++) {
        var v = document.getElementById('led-' + i).value.trim().toUpperCase();
        map.push(v);
    }
    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/led_cycle', true);
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onload = function() {
        var msg = document.getElementById('msg');
        if (xhr.status === 200) {
            msg.textContent = 'Saved!';
            msg.className = 'msg-ok';
        } else {
            msg.textContent = 'Error saving';
            msg.className = 'msg-err';
        }
    };
    xhr.onerror = function() {
        var msg = document.getElementById('msg');
        msg.textContent = 'Network error';
        msg.className = 'msg-err';
    };
    xhr.send(JSON.stringify({led_cycle: map}));
}
function refreshStatus() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/status', true);
    xhr.onload = function() {
        if (xhr.status === 200) setStatus(JSON.parse(xhr.responseText));
    };
    xhr.send();
}
function loadLedCycle() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/led_cycle', true);
    xhr.onload = function() {
        if (xhr.status === 200) {
            var data = JSON.parse(xhr.responseText);
            LED_COUNT = data.led_count || 100;
            buildGrid(data.led_cycle || []);
        }
    };
    xhr.send();
}
function showMessage(text, type) {
    var msg = document.getElementById('msg');
    msg.textContent = text;
    msg.className = 'msg-' + type;
}
loadLedCycle();
refreshStatus();
setInterval(refreshStatus, 60000);
</script>
</body>
</html>
"""


def get_status_json() -> dict:
    with led_cycle_lock:
        lc = list(led_cycle_map)
    with configure_lock:
        cfg_active = configure_mode
    return {
        "airports": current_airports,
        "home": status_display.get("home_airport"),
        "timezone": status_display.get("timezone"),
        "last_metar": status_display['last_metar'].isoformat() if status_display.get('last_metar') else None,
        "ip_address": status_display.get("ip_address"),
        "led_count": LED_COUNT,
        "led_cycle": lc,
    }


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_html(HTML_TEMPLATE)
        elif self.path == '/api/status':
            self.send_json(get_status_json())
        elif self.path == '/api/led_cycle':
            with led_cycle_lock:
                lc = list(led_cycle_map)
            with configure_lock:
                cfg_active = configure_mode
            self.send_json({"led_cycle": lc, "led_count": LED_COUNT, "configure_active": cfg_active})
        elif self.path == '/api/configure':
            with configure_lock:
                cfg_active = configure_mode
            self.send_json({"active": cfg_active})
        else:
            self.send_error(404)

    def do_POST(self):
        global led_cycle_map, configure_mode
        if self.path == '/api/led_cycle':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            new_map = data.get("led_cycle", [])
            if not isinstance(new_map, list):
                self.send_error(400, "led_cycle must be an array")
                return
            with led_cycle_lock:
                led_cycle_map = new_map[:LED_COUNT]
            try:
                config = json.loads(AIRPORT_FILE.read_text())
                config["led_cycle"] = led_cycle_map
                AIRPORT_FILE.write_text(json.dumps(config, indent=2) + "\n")
            except Exception as e:
                logger.error("Failed to save led_cycle to config.json: %s", e)
                self.send_error(500, "Failed to save config")
                return
            self.send_json({"status": "ok"})

        elif self.path == '/api/configure/start':
            with configure_lock:
                configure_mode = True
            logger.info("Configure mode started")
            self.send_json({"status": "ok"})

        elif self.path == '/api/configure/stop':
            with configure_lock:
                configure_mode = False
            logger.info("Configure mode stopped")
            self.send_json({"status": "ok"})

        elif self.path == '/api/configure/assign':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
            except json.JSONDecodeError:
                self.send_error(400, "Invalid JSON")
                return
            idx = data.get("index")
            airport = data.get("airport", "")
            if not isinstance(idx, int) or idx < 0 or idx >= LED_COUNT:
                self.send_error(400, "Invalid index")
                return
            if not isinstance(airport, str):
                self.send_error(400, "airport must be a string")
                return
            if airport and not _is_valid_icao(airport) and not _is_none_code(airport):
                self.send_error(400, f"Invalid ICAO code: {airport}")
                return
            with led_cycle_lock:
                led_cycle_map[idx] = airport
            try:
                config = json.loads(AIRPORT_FILE.read_text())
                config["led_cycle"] = led_cycle_map
                AIRPORT_FILE.write_text(json.dumps(config, indent=2) + "\n")
            except Exception as e:
                logger.error("Failed to save led_cycle to config.json: %s", e)
                self.send_error(500, "Failed to save config")
                return
            logger.info("Configure assigned LED %d -> %s", idx, airport)
            self.send_json({"status": "ok"})

        else:
            self.send_error(404)

    def send_html(self, html):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(html.encode())

    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        pass


def start_web_server(port=8080):
    server = HTTPServer(('0.0.0.0', port), WebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Web server started on port %d", port)
    return server


# ───────────────────── Main ────────────────────────────────────────────────

def main():
    global led_cycle_map

    airports, home, tz_str = load_config()
    logger.info("Timezone: %s", tz_str or "UTC")

    # Determine LED mapping source
    with led_cycle_lock:
        has_led_cycle = len(led_cycle_map) > 0

    # Setup LED Strip and OLED Display
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    oled = adafruit_ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, board.I2C(), addr=0x3C)
    oled_font = ImageFont.load_default()

    # Setup shutdown call to cleanup function that turns off LEDs and clears display.
    handler = partial(cleanup, oled, strip)
    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    # Initial clear OLED Display
    oled.fill(0)
    oled.show()

    if args.test_displays:
        strip.setPixelColor(0, COLOR_MAP['VFR'])
        strip.setPixelColor(1, COLOR_MAP['MVFR'])
        strip.setPixelColor(2, COLOR_MAP['IFR'])
        strip.setPixelColor(3, COLOR_MAP['LIFR'])
        strip.setPixelColor(4, COLOR_MAP['UNK'])
        strip.setPixelColor(5, COLOR_MAP_DIM['VFR'])
        strip.setPixelColor(6, COLOR_MAP_DIM['MVFR'])
        strip.setPixelColor(7, COLOR_MAP_DIM['IFR'])
        strip.setPixelColor(8, COLOR_MAP_DIM['LIFR'])
        strip.setPixelColor(9, COLOR_MAP_DIM['UNK'])
        strip.show()

        status_test = {
            'ip_address': 'N/A',
            'rssi': None,
            'time': datetime.now(),
            'last_metar': None,
            'other_text': None,
            'timezone': None,
        }

        status_test['time'] = datetime.now()
        status_test['ip_address'], status_test['rssi'] = get_wifi_status()
        update_display_normal(oled, status_test)
        return

    if has_led_cycle:
        logger.info("LED Cycle mode: %d LEDs mapped to airports", len(led_cycle_map))
    else:
        logger.info("Monitoring: %s", ", ".join(airports))

    # Start web server if requested
    if args.web:
        start_web_server(8080)

    wait_for_wifi(oled)

    # get home location so we can calculate night time
    home_location = home_airport_get_sun(home)

    try:
        while True:
            # Check for configure mode
            with configure_lock:
                cfg_active = configure_mode

            if cfg_active:
                with configure_lock:
                    cfg_mode = configure_mode
                if cfg_mode:
                    logger.info("Configure mode active, waiting for assignments...")
                    status_display['other_text'] = "CONFIGURE"
                    update_display_normal(oled, status_display)
                    # Keep OLED showing configure status
                    while True:
                        with configure_lock:
                            cfg_mode = configure_mode
                        if not cfg_mode:
                            break
                        status_display['time'] = datetime.now()
                        update_display_normal(oled, status_display)
                        time.sleep(2)
                    status_display['other_text'] = None
                    logger.info("Configure mode ended")
                continue

            logger.info("Night Mode: %s", get_is_night(home_location))
            metars = []
            tries = 0
            max_retries = 5
            base_delay = 2  # Start with 2 second delay

            while metars == []:
                print("getting metars")
                metars = get_metar_json(airports)
                tries = tries + 1

                if tries > max_retries:
                    if status_display['last_metar'] is not None and status_display['last_metar'] > datetime.now(timezone.utc) - timedelta(minutes=60):
                        logger.error("No METARs received after %d retries, waiting for next update interval.", max_retries)
                        led_set_all(strip, category_to_color('UNK'))
                        status_display['other_text'] = "API ERROR"
                        update_display_normal(oled, status_display)

                    time.sleep(UPDATE_INTERVAL)
                    status_display['other_text'] = None
                    break

                delay = min(base_delay * (2 ** (tries - 1)), 30)
                logger.info("METAR fetch failed, retrying in %d seconds (attempt %d/%d)...", delay, tries, max_retries)
                time.sleep(delay)

            with open('latest_metars.json', "w") as f:
                json.dump(metars, f, indent=4)

            # Parse ISO 8601 format with Zulu time
            report_time_str = metars[0].get('reportTime')
            if report_time_str:
                if report_time_str.endswith('Z'):
                    report_time_str = report_time_str[:-1]
                status_display['last_metar'] = datetime.fromisoformat(report_time_str).replace(tzinfo=timezone.utc)
            else:
                logger.warning("No reportTime found in METAR data, keeping previous value")

            # Parse wind speed and direction from home airport METAR data
            home_metar = None
            if home and not _is_none_code(home):
                for m in metars:
                    if m.get('icaoId') == home:
                        home_metar = m
                        break
            if home_metar is None:
                if home and not _is_none_code(home):
                    logger.warning("No METAR found for home airport %s, falling back to first METAR", home)
                home_metar = metars[0] if metars else None
            if home_metar:
                wind_speed = home_metar.get('windSpeed')
                wind_direction = home_metar.get('windDirection')
                status_display['home_wind_text'] = parse_wind_speed_direction(wind_speed, wind_direction)
                status_display['home_airport'] = home
                status_display['home_ceiling'] = get_ceiling_text(home_metar.get('clouds', []))
                status_display['home_visibility'] = get_visibility_text(home_metar.get('visibility'))
                logger.info("Home airport=%s Wind: direction=%s, speed=%s", home, wind_direction, wind_speed)

            cats = parse_metar_statuses(metars, airports)

            # Use led_cycle_map for LED display if available, otherwise use airports
            if has_led_cycle:
                # Build a dict mapping airport -> category for led_cycle airports
                cats_for_display = {}
                display_airports = []
                for icao in led_cycle_map:
                    if icao and not _is_none_code(icao):
                        cats_for_display[icao] = cats.get(icao, "UNK")
                        display_airports.append(icao)
                    else:
                        display_airports.append("")  # empty string or NONE = LED off
                led_update(strip, display_airports, cats_for_display, night=get_is_night(home_location))
            else:
                led_update(strip, airports, cats, night=get_is_night(home_location))

            status_display['time'] = datetime.now()
            status_display['ip_address'], status_display['rssi'] = get_wifi_status()
            status_display['cycle_time'] = time.time()
            status_display['timezone'] = tz_str
            update_display_normal(oled, status_display)
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Shutting down, clearing LEDs and display...")
        cleanup(oled, strip)
    except Exception as ee:
        logger.error("other error")
        logger.exception(ee)

        led_clear(strip)
        image = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
        draw.text((0, 0), f"ERROR", font=font_large, fill=255)
        draw.text((0, 20), f"{type(ee).__name__}", font=oled_font, fill=255)
        oled.fill(0)
        oled.show()


if __name__ == "__main__":
    main()
