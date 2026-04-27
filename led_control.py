"""LED strip control functions."""

import logging
from typing import Dict, List

import state
from config import _is_none_code
from hardware import Color, PixelStrip

logger = logging.getLogger("metar_led")


def category_to_color(cat: str, night_mode: bool = False) -> Color:
    """Return the Color for a flight category, dimmed at night."""
    color_map = state.COLOR_MAP_DIM if night_mode else state.COLOR_MAP
    return Color(*color_map.get(cat, color_map["UNK"]))


def led_update(
    strip: PixelStrip,
    airports: List[str],
    cats: Dict[str, str],
    night: bool = False,
) -> None:
    """Set every LED to the color matching each airport's METAR category."""
    for i, icao in enumerate(airports):
        if i >= strip.numPixels():
            break
        if not icao or _is_none_code(icao):
            strip.setPixelColor(i, Color(0, 0, 0))
        else:
            strip.setPixelColor(i, category_to_color(cats.get(icao, "UNK"), night_mode=night))
            logger.info("%s > %s", icao, cats.get(icao, "UNK"))
    strip.show()


def led_clear(strip: PixelStrip) -> None:
    """Turn off all LEDs."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()


def led_set_single(strip: PixelStrip, number: int, color: Color) -> None:
    """Set a single LED to the given color."""
    strip.setPixelColor(number, color)
    strip.show()


def led_set_all(strip: PixelStrip, color: Color) -> None:
    """Set every LED to the same color."""
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, color)
    strip.show()
