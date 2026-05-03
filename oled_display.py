"""SSD1306 OLED display rendering functions.

Tests that import this module must mock PIL and astral via sys.modules before import.
"""

import logging
import sys
import time
from datetime import datetime, timedelta, timezone

from astral import LocationInfo
from astral.sun import sun
from PIL import Image, ImageDraw, ImageFont

from utils import utc_to_local

logger = logging.getLogger("metar_led")

font = ImageFont.load_default(size=11)
font_med = ImageFont.load_default(size=12)
font_big = ImageFont.load_default(size=14)
font_large = ImageFont.load_default(size=16)


def display_show_airport(oled, airport: str) -> None:
    """Show a single airport code full-screen on the OLED."""
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
    draw.text((0, 0), airport, font=font_large, fill=255)
    oled.image(image)
    oled.show()


def get_is_night(location: LocationInfo) -> bool:
    """Return True if the current UTC time is outside the civil daylight window.

    LocationInfo is stored with timezone="UTC" so astral computes sun times
    anchored to UTC calendar dates. For locations west of UTC (e.g. North
    America) the evening dusk of a local day falls on the NEXT UTC date, making
    dusk appear before dawn on the same UTC date. We handle this by looking at
    yesterday, today, and tomorrow to find the dawn/dusk pair that brackets now.
    """
    now = datetime.now(timezone.utc)
    today = now.date()

    def _sun(d):
        return sun(location.observer, date=d, tzinfo=timezone.utc)

    try:
        t_prev  = _sun(today - timedelta(days=1))
        t_today = _sun(today)
        t_next  = _sun(today + timedelta(days=1))
    except Exception:
        return True  # assume night if astral fails

    # If today's dawn has already passed we are in today's solar day.
    # Dusk for that solar day may fall on the next UTC date (west-of-UTC locs).
    if t_today["dawn"] <= now:
        dawn = t_today["dawn"]
        dusk = t_today["dusk"] if t_today["dusk"] > dawn else t_next["dusk"]
    else:
        # Before today's dawn — still in yesterday's solar day.
        dawn = t_prev["dawn"]
        dusk = t_prev["dusk"] if t_prev["dusk"] > dawn else t_today["dusk"]

    logger.debug("home dawn: %s", dawn)
    logger.debug("home dusk: %s", dusk)
    logger.debug("now:       %s", now)

    if dusk <= dawn:
        return True  # polar edge-case: sun never rises or never sets
    return now < dawn or now > dusk


def display_show_status(oled, display_data: dict) -> None:
    """Render the system status screen: IP, hostname, WiFi RSSI."""
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)

    ip_text = str(display_data.get("ip_address", "Disconnected"))
    hostname = str(display_data.get("hostname", "unknown"))
    rssi = display_data.get("rssi")

    # IP big and readable on top half
    draw.text((0, 0), ip_text, font=font_large, fill=255)

    # hostname + WiFi indicator on bottom half
    if rssi is not None:
        if rssi >= -60:
            bars = "####"
        elif rssi >= -70:
            bars = "### "
        elif rssi >= -80:
            bars = "##  "
        else:
            bars = "#   "
        wifi_text = f"{rssi}dBm {bars}"
    else:
        wifi_text = "No WiFi"

    draw.text((0, 16), f"{hostname}  {wifi_text}", font=font, fill=255)

    oled.image(image)
    oled.show()


def update_display_normal(oled, display_data: dict) -> None:
    """Render the main status screen: WiFi bars, METAR time, home airport info."""
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
    bar_y_base = 10
    bar_width = 2
    bar_spacing = 3
    bar_max_height = 10

    for i in range(4):
        bar_height = (i + 1) * 2
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

    tz_str = display_data.get("timezone")
    wx_local = (
        utc_to_local(display_data["last_metar"], tz_str) if display_data.get("last_metar") else None
    )
    now_local = utc_to_local(display_data["time"], tz_str)

    wx_text = f"WX: {wx_local.strftime('%H:%M') if wx_local else 'N/A'}"
    now_text = now_local.strftime("%H:%M") if now_local else "N/A"

    cycle_time = display_data.get("cycle_time", 0)
    cycle_index = int(cycle_time) // 5 % 4 if cycle_time else 0

    if display_data.get("other_text"):
        top_text = display_data["other_text"]
    else:
        home = display_data.get("home_airport", "")
        top_texts = [
            f"HOME: {home}",
            display_data.get("home_wind_text") or "WIND --/--",
            display_data.get("home_ceiling")   or "CEIL --",
            display_data.get("home_visibility") or "VIS --",
        ]
        top_text = top_texts[cycle_index % len(top_texts)]

    draw.text((0, 0), top_text, font=font_large, fill=255)

    bbox_now = draw.textbbox((0, 0), now_text, font=font_big)
    now_width = bbox_now[2] - bbox_now[0]
    draw.text((oled.width - now_width - 2, 18), now_text, font=font_big, fill=255)
    draw.text((2, 18), wx_text, font=font_big, fill=255)

    oled.image(image)
    oled.show()


def display_show_connecting(oled, remaining: int) -> None:
    """Show WiFi connecting countdown on OLED."""
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
    draw.text((0, 0),  "WiFi Connecting", font=font,     fill=255)
    draw.text((0, 14), f"{remaining}s...", font=font_med, fill=255)
    oled.image(image)
    oled.show()


def display_show_ap_mode(oled, ssid: str, ip: str = "10.42.0.1") -> None:
    """Show AP setup mode on OLED: SSID and IP address to connect to."""
    image = Image.new("1", (oled.width, oled.height))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, oled.width, oled.height), outline=0, fill=0)
    draw.text((0, 0),  "WiFi Setup Mode", font=font,     fill=255)
    draw.text((0, 12), ssid,              font=font_med,  fill=255)
    draw.text((0, 23), ip + ":8080",      font=font,      fill=255)
    oled.image(image)
    oled.show()


def cleanup(oled, strip, signum=None, frame=None) -> None:
    """Signal handler: clear LEDs and display, then exit."""
    from led_control import led_clear
    logger.info("Turning off all LEDs and clearing OLED screen")
    led_clear(strip)
    oled.fill(0)
    oled.show()
    sys.exit(0)
