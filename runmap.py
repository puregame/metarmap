"""LED METAR Map - v3.2 (ceiling-based category)
================================================
The AviationWeather.gov JSON feed no longer includes `flight_category`.
This version derives VFR/MVFR/IFR/LIFR from the **cloud ceiling** in each
METAR:

* **Ceiling** = lowest `BKN` or `OVC` layer. If none, treat as clear.  
* **Category rules**  (FAA/NOAA standard):
  * VFR ≥ 3 000 ft
  * MVFR 1000 - 2 999 ft
  * IFR 500 - 999 ft
  * LIFR < 500 ft

Everything else in v3.0 (mock mode, `--dry-run`, logging, JSON airport
list) remains unchanged.

Run examples
────────────
```bash
# Real LEDs on Pi
sudo python3 led_metar_map.py

# Laptop test
python3 led_metar_map.py --dry-run
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
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from functools import partial

from datetime import datetime, timezone

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
parser.add_argument("--cycle_airports", action="store_true", help="Cycle airports one at a time, flash the LED and show code on OLED Display")
args = parser.parse_args()
SIMULATION = args.dry_run or not HARDWARE_AVAILABLE

# ───────────────────── LED Config ───────────────────────────────────────────────
LED_COUNT = 30
LED_PIN = 18
LED_FREQ_HZ = 800_000
LED_DMA = 10
LED_BRIGHTNESS = 65
LED_INVERT = False
LED_CHANNEL = 0

AIRPORT_FILE = Path(__file__).with_name("airports.json")
LOG_FILE = Path(__file__).with_name("metar_led.log")
UPDATE_INTERVAL = 60 # refresh data every 60 seconds

COLOR_MAP: Dict[str, Color] = { #NOTE: colors are in GRB format!!
    "VFR": Color(140, 0, 0),
    "MVFR": Color(0, 0, 140),
    "IFR": Color(0, 140, 0),
    "LIFR": Color(0, 120, 80),
    "UNK": Color(100, 100, 100),
}

COLOR_MAP_DIM: Dict[str, Color] = {
    "VFR": Color(45, 0, 0),
    "MVFR": Color(0, 0, 45),
    "IFR": Color(0, 45, 0),
    "LIFR": Color(0, 64, 64),
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
logger.setLevel(logging.INFO)
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
for h in (logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)):
    h.setFormatter(fmt)
    logger.addHandler(h)
logger.info("hardware available: %s", HARDWARE_AVAILABLE)
logger.info("Simulation mode: %s", SIMULATION)


# ───────────────────── Global Vars ──────────────────────────────────────────────
status_display = {'ip_address': 'Disconnected',
                  'rssi': 'None',
                  'time': datetime.now(),
                  'last_metar': 'ERROR'}

# ───────────────────── Helpers ──────────────────────────────────────────────

def load_airports() -> Tuple[List[str], str]:
    try:
        data = json.loads(AIRPORT_FILE.read_text())
        airports = data.get("airports", [])
        home = data.get('home', '')
        if not airports:
            raise ValueError("No airports in JSON")
        return airports, home
    except Exception as exc:
        logger.exception("Problem loading %s: %s", AIRPORT_FILE, exc)
        raise


def ceiling_category(clouds: List[dict]) -> str:
    """Return flight‐rules category from cloud layers list."""
    ceiling: Optional[int] = None  # feet
    for layer in clouds:
        cover = layer.get("cover")
        base = layer.get("base")
        if cover in ("BKN", "OVC") and isinstance(base, (int, float)):
            ceiling = base if ceiling is None or base < ceiling else ceiling
    if ceiling is None:
        return "VFR"
    if ceiling < 500:
        return "LIFR"
    if ceiling < 1000:
        return "IFR"
    if ceiling < 3000:
        return "MVFR"
    return "VFR"


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
        # logger.info("Requested URL: %s", response.url)
        # logger.info("HTTP Status: %s", response.status_code)
        # logger.info("Response Content: %s", response.text[:500])  # truncate to avoid spam
        response.raise_for_status()
        data = response.json()
        reports = data if isinstance(data, list) else data.get("data", [])
        return reports
    except Exception as e:
        logger.error("METAR fetch error: %s", e)
        return []


def parse_metar_statuses(reports: List[dict], airports: List[str]) -> Dict[str, str]:
    cats = {a: "UNK" for a in airports}
    for rpt in reports:
        icao = next((rpt.get(k) for k in ("icaoId", "station_id", "station", "icao", "id") if rpt.get(k)), None)
        if not icao:
            continue
        icao = icao.upper()
        cat = ceiling_category(rpt.get("clouds", []))
        if icao in cats:
            cats[icao] = cat
    return cats


def category_to_color(cat: str, night_mode = False) -> Color:
    if night_mode:
        return COLOR_MAP_DIM.get(cat, COLOR_MAP_DIM["UNK"])
    return COLOR_MAP.get(cat, COLOR_MAP["UNK"])


def led_update(strip: PixelStrip, airports: List[str], cats: Dict[str, str], night=False):
    for i, icao in enumerate(airports):
        if i >= strip.numPixels():
            break
        strip.setPixelColor(i, category_to_color(cats.get(icao, "UNK"), night_mode=night))
        logger.info("%s > %s", icao, cats.get(icao, "UNK"))
    strip.show()


def led_clear(strip: PixelStrip):
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def led_set_single(strip: PixelStrip, number: int, color:Color):
    strip.setPixelColor(number, color)
    strip.show()


def display_update(oled: adafruit_ssd1306.SSD1306_I2C, display_data: dict):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)

    # Extract RSSI
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

    # Bar dimensions and position
    bar_x = oled.width - 20
    bar_y_base = 12
    bar_width = 2
    bar_spacing = 3
    bar_max_height = 12

    # Draw WiFi bars
    for i in range(4):
        bar_height = (i + 1) * 3
        x = bar_x + i * bar_spacing
        y = bar_y_base - bar_height
        fill = 255 if i < bar_count else 0
        draw.rectangle([x, y, x + bar_width, bar_y_base], fill=fill)

    # If RSSI is None, draw a diagonal line through bars
    if rssi is None:
        x1 = bar_x - 2
        x2 = bar_x + (3 * bar_spacing) + bar_width + 2
        y1 = bar_y_base
        y2 = bar_y_base - bar_max_height
        draw.line([x1, y1, x2, y2], fill=255, width=1)
        draw.line([x1, y2, x2, y1], fill=255, width=1)

    # Draw text
    wx_time = display_data['last_metar'].astimezone(timezone.utc).strftime('%H:%M') if display_data['last_metar'] else 'N/A'
    now_time = display_data['time'].astimezone(timezone.utc).strftime('%H:%M')

    wx_text = f"WX: {wx_time}z"
    now_text = f"{now_time}z"
    # wifi_text = f"WiFi: {rssi if rssi is not None else 'N/A'}dB"
    wifi_text = f"{display_data['ip_address']}"

    # Draw WX time top left-justified
    draw.text((0, 0), wx_text, font=font_large, fill=255)
    # Draw NOW time bottom left-justified
    draw.text((0, 16), now_text, font=font_large, fill=255)

    # Draw Wifi text and bottom-right justify it
    bbox = draw.textbbox((0, 0), wifi_text, font=font)
    wifi_text_width = bbox[2] - bbox[0]
    draw.text((oled.width - wifi_text_width, 20), wifi_text, font=font, fill=255)

    oled.image(image)
    oled.show()


def display_show_airport(oled: adafruit_ssd1306, airport:str):
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
    draw.text((0, 0), airport, font=font_large, fill=255)
    oled.image(image)
    oled.show()


def cleanup(oled, strip, signum, frame):
    logger.info("Turning off all LEDs and clearing OLED screen")
    led_clear(strip)
    oled.fill(0)
    oled.show()
    sys.exit(0)


def home_airport_get_sun(airport:str) -> LocationInfo:
    airport_data = get_metar_json([airport])[0]
    # Create Astral Location
    return LocationInfo(name=airport, region="Airport", timezone="UTC", latitude=airport_data['lat'], longitude=airport_data['lon']) 


def get_is_night(location: LocationInfo) -> bool:
    now = datetime.now(timezone.utc)
    sun_times = sun(location.observer, date=now.date(), tzinfo=timezone.utc)
    logger.debug(f"home dawn: {sun_times['dawn']}")
    logger.debug(f"home dusk: {sun_times['dusk']}")
    logger.debug(f"now: {now}")
    return now < sun_times["dawn"] or now > sun_times["dusk"]


def is_wifi_connected():
    try:
        # Check if IP address assigned (non-empty output means connected)
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


# ───────────────────── Main ────────────────────────────────────────────────

def main():
    # Setup LED Strip and OLED Display
    strip = PixelStrip(LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL)
    strip.begin()

    oled = adafruit_ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, board.I2C(), addr=0x3C)
    font = ImageFont.load_default()

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

        status_test = {'ip_address': 'N/A',
                       'rssi': None,
                       'time': datetime.now(),
                       'last_metar': None}
        
        status_test['time'] = datetime.now()
        status_test['ip_address'], status_test['rssi'] = get_wifi_status()
        display_update(oled, status_test)
        return

    airports, home = load_airports()

    if args.cycle_airports:
        while True:
            for num, airport in enumerate(airports):
                led_clear(strip)
                led_set_single(strip, num, Color(140,0,0))
                display_show_airport(oled, f"{num} - {airport}")
                time.sleep(3)

    logger.info("Monitoring: %s", ", ".join(airports))

    wait_for_wifi(oled)

    # get home location so we can calculate night time 
    home_location = home_airport_get_sun(home)

    try:
        while True:
            logger.info(f"Night Mode: {'True' if get_is_night(home_location) else 'False'}")
            metars = []
            tries = 0
            while metars == []:
                print("getting metars")
                metars = get_metar_json(airports)
                tries = tries + 1
                if tries > 5:
                    raise Exception("Can't get METAR List")

            with open('latest_metars.json', "w") as f:
                json.dump(metars, f, indent=4)

            status_display['last_metar'] = datetime.strptime(metars[0]['reportTime'], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

            cats = parse_metar_statuses(metars, airports)
            led_update(strip, airports, cats, night=get_is_night(home_location))

            status_display['time'] = datetime.now()
            status_display['ip_address'], status_display['rssi'] = get_wifi_status()
            display_update(oled, status_display)
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        logger.info("Shutting down, clearing LEDs and display…")
        cleanup(oled, strip)
    except Exception as ee: # handle all other exceptions
        logger.error("other error")
        logger.exception(ee)
        
        led_clear(strip)
        image = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
        draw.text((0, 0), f"ERROR", font=font_large, fill=255)
        draw.text((0, 20), f"{type(ee).__name__}", font=font, fill=255)
        oled.fill(0)
        oled.show()

if __name__ == "__main__":
    main()
