"""LED METAR Map - v5.0
===========================================================================
Derives VFR/MVFR/IFR/LIFR from cloud ceiling in each METAR report.

Run examples
────────────
    # Real LEDs on Pi
    sudo python3 runmap.py

    # Laptop / dry-run simulation
    python3 runmap.py --dry-run

    # With web UI (http://<pi-ip>:8080)
    python3 runmap.py --web
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from pathlib import Path

import board
import adafruit_ssd1306
from PIL import ImageFont

import state
from hardware import HARDWARE_AVAILABLE, Color, PixelStrip
from config import load_config
from utils import (
    get_ceiling_text,
    get_hostname,
    get_visibility_text,
    get_wifi_status,
    parse_wind_speed_direction,
    wait_for_wifi,
)
from metar_api import get_metar_json, home_airport_get_sun, parse_metar_statuses
from led_control import category_to_color, led_clear, led_set_all, led_update
from oled_display import cleanup, display_show_status, get_is_night, update_display_normal
from web_server import start_web_server
from config import _is_none_code

# ─── CLI args ────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser(description="LED METAR Map")
parser.add_argument("--dry-run", action="store_true", help="Force simulation mode")
parser.add_argument("--test_displays", action="store_true", help="Show test colour pattern")
parser.add_argument("--web", action="store_true", help="Enable web server on port 8080")
args = parser.parse_args()

SIMULATION = args.dry_run or not HARDWARE_AVAILABLE

# ─── Hardware constants ───────────────────────────────────────────────────────
LED_PIN = 18
LED_FREQ_HZ = 800_000
LED_DMA = 10
LED_BRIGHTNESS = 65
LED_INVERT = False
LED_CHANNEL = 0

OLED_WIDTH = 128
OLED_HEIGHT = 32
BUTTON_PIN = 23

LOG_FILE = Path(__file__).with_name("metar_led.log")
UPDATE_INTERVAL = 60  # seconds between METAR refreshes
DISPLAY_INTERVAL = 1  # seconds between OLED display updates

# ─── Logging ─────────────────────────────────────────────────────────────────
logger = logging.getLogger("metar_led")
logger.setLevel(logging.DEBUG)
_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
for _h in (logging.FileHandler(LOG_FILE), logging.StreamHandler(sys.stdout)):
    _h.setFormatter(_fmt)
    logger.addHandler(_h)
logger.info("hardware available: %s", HARDWARE_AVAILABLE)
logger.info("Simulation mode: %s", SIMULATION)

# ─── Button / GPIO ────────────────────────────────────────────────────────────

_gpio_available = False


def _gpio_setup() -> None:
    global _gpio_available
    try:
        import RPi.GPIO as _gpio  # type: ignore

        _gpio.setwarnings(False)
        _gpio.setmode(_gpio.BCM)
        _gpio.setup(BUTTON_PIN, _gpio.IN, pull_up_down=_gpio.PUD_UP)
        _gpio.add_event_detect(
            BUTTON_PIN, _gpio.FALLING, callback=_button_callback, bouncetime=200
        )
        _gpio_available = True
        logger.info("Button on GPIO %d enabled", BUTTON_PIN)
    except ImportError:
        logger.debug("RPi.GPIO not available — button disabled")
        _gpio_available = False
    except Exception as exc:
        logger.warning("Button init failed (%s) — continuing without button", exc)
        _gpio_available = False


def _button_callback(channel):
    """GPIO interrupt handler — just wakes the main loop."""
    state.refresh_event.set()


def _gpio_cleanup() -> None:
    if _gpio_available:
        try:
            import RPi.GPIO as _gpio  # type: ignore

            _gpio.remove_event_detect(BUTTON_PIN)
            _gpio.cleanup(BUTTON_PIN)
        except Exception:
            pass
        _gpio_available = False


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    airports, home, tz_str = load_config()
    logger.info("Timezone: %s", tz_str or "UTC")

    strip = PixelStrip(
        state.LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
    )
    strip.begin()
    state.strip = strip  # expose to web server for LED control endpoints

    oled = adafruit_ssd1306.SSD1306_I2C(OLED_WIDTH, OLED_HEIGHT, board.I2C(), addr=0x3C)
    oled_font = ImageFont.load_default()

    def _signal_handler(signum, frame):
        _gpio_cleanup()
        cleanup(oled, strip)

    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)

    oled.fill(0)
    oled.show()

    _gpio_setup()

    if args.test_displays:
        _run_display_test(strip, oled)
        return

    logger.info("Monitoring: %s", ", ".join(airports))

    if args.web:
        start_web_server(8080)

    wait_for_wifi(oled)
    home_location = home_airport_get_sun(home)
    state.home_location = home_location

    state.status_display["hostname"] = get_hostname()
    state.status_display["timezone"] = tz_str
    show_status = False
    last_metar_fetch = 0.0

    try:
        while True:
            now = time.time()
            display_now = datetime.now()

            # ── Display update (every 1 second) ────────────────────────────
            state.status_display["time"] = display_now
            state.status_display["cycle_time"] = now
            state.status_display["ip_address"], state.status_display["rssi"] = get_wifi_status()

            # Check button: if held, toggle screen and wait for release
            if _gpio_available:
                try:
                    import RPi.GPIO as _gpio  # type: ignore

                    if not _gpio.input(BUTTON_PIN):
                        show_status = not show_status
                        time.sleep(0.2)
                        while not _gpio.input(BUTTON_PIN):
                            time.sleep(0.05)
                except Exception:
                    pass

            if show_status:
                display_show_status(oled, state.status_display)
            else:
                update_display_normal(oled, state.status_display)

            # ── METAR fetch + LED update (every 60 seconds) ────────────────
            if now - last_metar_fetch >= UPDATE_INTERVAL:
                last_metar_fetch = now

                if state.strip_needs_reinit:
                    logger.info("Reinitializing LED strip with %d pixels", state.LED_COUNT)
                    led_clear(strip)
                    strip = PixelStrip(
                        state.LED_COUNT, LED_PIN, LED_FREQ_HZ, LED_DMA, LED_INVERT, LED_BRIGHTNESS, LED_CHANNEL
                    )
                    strip.begin()
                    state.strip = strip
                    state.strip_needs_reinit = False
                    logger.info("LED strip reinitialized")

                airports = state.current_airports  # picks up any saves from the web UI
                night = get_is_night(home_location)
                state.is_night = night  # update regardless of METAR fetch success
                logger.info("Night Mode: %s", night)
                metars = _fetch_metars_with_retry(airports, strip, oled)
                if metars is None:
                    continue

                with open("latest_metars.json", "w") as f:
                    json.dump(metars, f, indent=4)

                _update_report_time(metars)
                _update_home_metar(metars, home)

                cats = parse_metar_statuses(metars, airports)
                led_update(strip, airports, cats, night=night)

                state.categories = cats

            state.refresh_event.wait(timeout=DISPLAY_INTERVAL)
            state.refresh_event.clear()

    except KeyboardInterrupt:
        logger.info("Shutting down")
        cleanup(oled, strip)
    except Exception as ee:
        logger.exception("Unexpected error: %s", ee)
        led_clear(strip)
        _show_error_screen(oled, oled_font, ee)
    finally:
        _gpio_cleanup()


def _fetch_metars_with_retry(airports, strip, oled):
    """Fetch METARs with exponential back-off. Returns None if all retries fail."""
    metars = []
    tries = 0
    max_retries = 5
    base_delay = 2

    while not metars:
        print("getting metars")
        metars = get_metar_json(airports)
        tries += 1

        if tries > max_retries:
            last_metar = state.status_display.get("last_metar")
            if last_metar and last_metar > datetime.now(timezone.utc) - timedelta(minutes=60):
                logger.error("No METARs after %d retries", max_retries)
                led_set_all(strip, category_to_color("UNK"))
                state.status_display["other_text"] = "API ERROR"
                update_display_normal(oled, state.status_display)

            time.sleep(UPDATE_INTERVAL)
            state.status_display["other_text"] = None
            return None

        if not metars:
            delay = min(base_delay * (2 ** (tries - 1)), 30)
            logger.info("METAR fetch failed, retrying in %ds (%d/%d)", delay, tries, max_retries)
            time.sleep(delay)

    return metars


def _update_report_time(metars: list) -> None:
    report_time_str = metars[0].get("reportTime")
    if not report_time_str:
        logger.warning("No reportTime in METAR data")
        return
    if report_time_str.endswith("Z"):
        report_time_str = report_time_str[:-1]
    state.status_display["last_metar"] = datetime.fromisoformat(report_time_str).replace(
        tzinfo=timezone.utc
    )


def _update_home_metar(metars: list, home: str) -> None:
    home_metar = None
    if home and not _is_none_code(home):
        home_metar = next((m for m in metars if m.get("icaoId") == home), None)
        if home_metar is None:
            logger.warning("No METAR for home airport %s, using first report", home)

    if home_metar is None:
        home_metar = metars[0] if metars else None

    if home_metar:
        state.status_display["home_wind_text"] = parse_wind_speed_direction(
            home_metar.get("windSpeed"), home_metar.get("windDirection")
        )
        state.status_display["home_airport"] = home
        state.status_display["home_ceiling"] = get_ceiling_text(home_metar.get("clouds", []))
        state.status_display["home_visibility"] = get_visibility_text(home_metar.get("visibility"))
        logger.info("Home airport=%s wind=%s", home, state.status_display["home_wind_text"])


def _run_display_test(strip, oled) -> None:
    for i, cat in enumerate(["VFR", "MVFR", "IFR", "LIFR", "UNK"]):
        strip.setPixelColor(i, Color(*state.COLOR_MAP[cat]))
        strip.setPixelColor(i + 5, Color(*state.COLOR_MAP_DIM[cat]))
    strip.show()

    test_data = {
        "ip_address": "N/A",
        "rssi": None,
        "time": datetime.now(),
        "last_metar": None,
        "other_text": None,
        "timezone": None,
    }
    test_data["ip_address"], test_data["rssi"] = get_wifi_status()
    update_display_normal(oled, test_data)


def _show_error_screen(oled, oled_font, exc: Exception) -> None:
    from PIL import Image, ImageDraw, ImageFont as _ImageFont
    image = Image.new("1", (OLED_WIDTH, OLED_HEIGHT))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, OLED_WIDTH, OLED_HEIGHT), outline=0, fill=0)
    draw.text((0, 0), "ERROR", font=_ImageFont.load_default(size=16), fill=255)
    draw.text((0, 20), type(exc).__name__, font=oled_font, fill=255)
    oled.fill(0)
    oled.show()


if __name__ == "__main__":
    main()
