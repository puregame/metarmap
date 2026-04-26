# Metarmap — Agent Notes

## Project Structure

```
runmap.py           Entry point: CLI args, main(), hardware init
state.py            Shared mutable state (airports, colors, status_display, LED_COUNT)
hardware.py         rpi_ws281x with mock fallbacks (Color, PixelStrip)
config.py           Config validation (validate_config) and loading (load_config)
utils.py            Pure helpers: ceiling_category, wind/visibility text, timezone, wifi
metar_api.py        AviationWeather.gov API: get_metar_json, parse_metar_statuses, home_airport_get_sun
led_control.py      LED strip operations: led_update, led_clear, led_set_all, led_set_single
oled_display.py     SSD1306 rendering: update_display_normal, get_is_night, display_show_airport
web_server.py       HTTPServer: WebHandler, get_status_json, start_web_server, load_template
templates/
  index.html        Web UI (dark theme, auto-refreshes status every 60s)
tests/
  test_config_validation.py   validate_config — no mocks needed
  test_utils.py               ceiling_category, wind/vis text, timezone, wifi — no mocks needed
  test_web_server.py          web server endpoints and template — no mocks needed
  test_led_control.py         LED operations — uses hardware fallback classes, no mocks needed
  test_metar_api.py           METAR API fetch and parse — mocks requests; home_airport_get_sun mocks astral
  test_sun_logic.py           home_airport_get_sun — mocks astral via sys.modules
  test_night_detection.py     get_is_night — mocks PIL + astral via sys.modules
```

## Running Tests

Tests must be run as individual scripts (not `unittest discover`):

```bash
python3 tests/test_config_validation.py
python3 tests/test_utils.py
python3 tests/test_web_server.py
python3 tests/test_led_control.py
python3 tests/test_metar_api.py
python3 tests/test_sun_logic.py
python3 tests/test_night_detection.py
```

Run all at once:

```bash
for t in tests/test_config_validation.py tests/test_utils.py tests/test_web_server.py tests/test_led_control.py tests/test_metar_api.py tests/test_sun_logic.py tests/test_night_detection.py; do python3 "$t"; done
```

Total: 158 tests (all passing).

## Hardware mocking

Only `oled_display.py` and (for `home_airport_get_sun`) `metar_api.py` require library mocks:
- `oled_display.py` — mock `PIL.*` and `astral*` via `sys.modules` before import
- `metar_api.home_airport_get_sun` — mock `astral` via `sys.modules` in setUp/tearDown

All other modules (`config`, `utils`, `metar_api` fetch/parse, `led_control`, `web_server`) are importable with no mocks on a dev machine.

## Web API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Main UI (tabbed: Home / Config) |
| GET | `/api/status` | JSON: airports, home, timezone, last_metar, ip_address, led_count |
| POST | `/api/leds/clear` | Turn off all LEDs |
| POST | `/api/leds/<n>/flash` | Flash LED n three times (synchronous, ~1.2s) |
| POST | `/api/config` | `{"airports": [...]}` — validates, writes config.json, updates live state |

## New in v5.0

- `--cycle_airports` CLI flag removed (configure mode moved to web UI)
- Config tab: editable LED→airport table, Flash buttons, Save, Clear LEDs
- Main loop reads `state.current_airports` each iteration so web UI saves take effect immediately
- `state.strip` exposed so web server can drive LEDs without touching the main loop
