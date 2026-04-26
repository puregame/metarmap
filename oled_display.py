"""SSD1306 OLED display rendering functions.

Tests that import this module must mock PIL and astral via sys.modules before import.
"""

import logging
import sys
import time
from datetime import datetime, timezone

from astral import LocationInfo
from astral.sun import sun
from PIL import Image, ImageDraw, ImageFont

from utils import utc_to_local

logger = logging.getLogger("metar_led")

font = ImageFont.load_default(size=11)
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
    """Return True if the current UTC time is between dusk and dawn at location."""
    now = datetime.now(timezone.utc)
    sun_times = sun(location.observer, date=now.date(), tzinfo=timezone.utc)
    logger.debug("home dawn: %s", sun_times["dawn"])
    logger.debug("home dusk: %s", sun_times["dusk"])
    logger.debug("now: %s", now)
    if sun_times["dusk"] > sun_times["dawn"]:
        return now < sun_times["dawn"] or now > sun_times["dusk"]
    return True


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

    tz_str = display_data.get("timezone")
    wx_local = (
        utc_to_local(display_data["last_metar"], tz_str) if display_data.get("last_metar") else None
    )
    now_local = utc_to_local(display_data["time"], tz_str)

    wx_text = f"WX: {wx_local.strftime('%H:%M') if wx_local else 'N/A'}"
    now_text = now_local.strftime("%H:%M") if now_local else "N/A"
    wifi_text = str(display_data.get("ip_address", ""))

    cycle_time = display_data.get("cycle_time", 0)
    cycle_index = int(time.time()) % 12 // 3 if cycle_time else 0

    if display_data.get("other_text"):
        top_text = display_data["other_text"]
    else:
        home = display_data.get("home_airport", "")
        top_texts = [
            f"HOME: {home}",
            display_data.get("home_wind_text", "WIND --/--"),
            display_data.get("home_ceiling", "CEIL --"),
            display_data.get("home_visibility", "VIS --"),
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


def cleanup(oled, strip, signum=None, frame=None) -> None:
    """Signal handler: clear LEDs and display, then exit."""
    from led_control import led_clear
    logger.info("Turning off all LEDs and clearing OLED screen")
    led_clear(strip)
    oled.fill(0)
    oled.show()
    sys.exit(0)
