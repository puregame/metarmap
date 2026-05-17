"""Built-in HTTP server for status display and LED configuration."""

import json
import logging
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import state
from config import AIRPORT_FILE, validate_config
from utils import AP_SSID as _AP_SSID

_LOG_FILE = Path(__file__).with_name("metar_led.log")

logger = logging.getLogger("metar_led")

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


# ── Template ──────────────────────────────────────────────────────────────────

def load_template() -> str:
    return _TEMPLATE_PATH.read_text()


# ── API handlers (pure functions, easy to unit-test) ─────────────────────────

def _rgb_to_hex(rgb: tuple) -> str:
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def get_status_json() -> dict:
    return {
        "airports":        state.current_airports,
        "home":            state.status_display.get("home_airport"),
        "timezone":        state.status_display.get("timezone"),
        "last_metar":      (
            state.status_display["last_metar"].isoformat()
            if state.status_display.get("last_metar")
            else None
        ),
        "ip_address":      state.status_display.get("ip_address"),
        "led_count":       state.LED_COUNT,
        "categories":      dict(state.categories),
        "is_night":        state.is_night,
        "category_colors": {k: _rgb_to_hex(v) for k, v in state.COLOR_MAP.items()},
        "category_colors_dim": {k: _rgb_to_hex(v) for k, v in state.COLOR_MAP_DIM.items()},
        "ap_mode":             state.ap_mode,
        "ap_mode_ssid":        _AP_SSID if state.ap_mode else None,
    }


def handle_get_config() -> dict:
    """Return the raw contents of config.json."""
    try:
        return json.loads(AIRPORT_FILE.read_text())
    except Exception as exc:
        logger.error("Could not read config: %s", exc)
        return {}


def handle_clear_leds() -> dict:
    """Turn off every LED on the strip."""
    if state.strip is None:
        return {"error": "LED strip not initialised"}
    from led_control import led_clear
    led_clear(state.strip)
    return {"ok": True}


def handle_flash_led(index: int) -> dict:
    """Flash one LED three times so the user can identify it physically."""
    if state.strip is None:
        return {"error": "LED strip not initialised"}
    if index < 0 or index >= state.LED_COUNT:
        return {"error": f"LED index {index} out of range (configured: {state.LED_COUNT})"}
    if index >= state.strip.numPixels():
        return {"error": f"LED {index} not yet active — strip is reinitializing, try again in a moment"}
    from hardware import Color
    from led_control import led_set_single
    for _ in range(3):
        led_set_single(state.strip, index, Color(255, 255, 255))
        time.sleep(0.25)
        led_set_single(state.strip, index, Color(0, 0, 0))
        time.sleep(0.15)
    return {"ok": True}


def handle_get_debug() -> dict:
    """Return raw night-mode calculation values for diagnostics."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    result = {
        "utc_now":          now.isoformat(),
        "is_night":         state.is_night,
        "led_count":        state.LED_COUNT,
        "strip_pixel_count": state.strip.numPixels() if state.strip else None,
        "strip_needs_reinit": state.strip_needs_reinit,
        "home_airport":     state.status_display.get("home_airport"),
    }
    loc = state.home_location
    if loc is not None:
        result["location"] = {
            "name":      loc.name,
            "latitude":  loc.latitude,
            "longitude": loc.longitude,
            "timezone":  loc.timezone,
        }
        try:
            from astral.sun import sun as astral_sun
            sun_times = astral_sun(loc.observer, date=now.date(), tzinfo=timezone.utc)
            result["dawn_utc"]  = sun_times["dawn"].isoformat()
            result["dusk_utc"]  = sun_times["dusk"].isoformat()
            result["is_before_dawn"] = now < sun_times["dawn"]
            result["is_after_dusk"]  = now > sun_times["dusk"]
        except Exception as exc:
            result["sun_error"] = str(exc)
    else:
        result["location"] = None
        result["note"] = "home_location not set — main loop not yet started?"
    return result


def handle_test_colors() -> dict:
    """Light a sequence of LEDs to demonstrate all day+night category colors."""
    if state.strip is None:
        return {"error": "LED strip not initialised"}
    from hardware import Color
    from led_control import led_clear
    cats = ["VFR", "MVFR", "IFR", "LIFR", "UNK"]
    # Day colors on LEDs 0-4, night (dim) colors on LEDs 5-9
    for i, cat in enumerate(cats):
        state.strip.setPixelColor(i,     Color(*state.COLOR_MAP.get(cat, (100, 100, 100))))
        state.strip.setPixelColor(i + 5, Color(*state.COLOR_MAP_DIM.get(cat, (50, 50, 50))))
    state.strip.show()
    return {"ok": True}


def handle_refresh() -> dict:
    """Signal the main loop to fetch METARs immediately."""
    state.refresh_event.set()
    return {"ok": True}


def handle_get_wifi() -> dict:
    from utils import wifi_list_saved
    return {"networks": wifi_list_saved()}


def handle_add_wifi(body: bytes) -> dict:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Invalid JSON"}
    ssid = (data.get("ssid") or "").strip()
    if not ssid:
        return {"error": "ssid is required"}
    password = (data.get("password") or "").strip()
    from utils import wifi_add, wifi_stop_ap
    err = wifi_add(ssid, password)
    if err:
        logger.warning("WiFi add failed for '%s': %s", ssid, err)
        return {"error": err}
    logger.info("WiFi network '%s' saved via web UI", ssid)
    if state.ap_mode:
        # Stop the AP after the response is sent so the client gets the reply
        def _stop():
            import time as _time
            _time.sleep(0.5)
            wifi_stop_ap()
            state.ap_mode = False
            logger.info("AP mode stopped after new network '%s' saved", ssid)
        threading.Thread(target=_stop, daemon=True).start()
        return {"ok": True, "connecting": True}
    return {"ok": True}


def handle_delete_wifi(body: bytes) -> dict:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Invalid JSON"}
    name = (data.get("name") or "").strip()
    if not name:
        return {"error": "name is required"}
    from utils import wifi_delete
    err = wifi_delete(name)
    if err:
        logger.warning("WiFi delete failed for '%s': %s", name, err)
        return {"error": err}
    logger.info("WiFi network '%s' deleted via web UI", name)
    return {"ok": True}


def handle_get_logs(lines: int = 100) -> dict:
    """Return the last N lines of the log file."""
    try:
        text = _LOG_FILE.read_text(errors="replace")
        entries = [l for l in text.splitlines() if l.strip()]
        return {"lines": entries[-lines:]}
    except FileNotFoundError:
        return {"lines": []}
    except Exception as exc:
        logger.error("Could not read log: %s", exc)
        return {"lines": [], "error": str(exc)}


def handle_save_config(body: bytes) -> dict:
    """Validate and persist settings; updates live state immediately."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return {"error": "Invalid JSON body"}

    airports = data.get("airports")
    if not isinstance(airports, list):
        return {"error": "'airports' must be a list"}

    # Load existing config so unrelated fields are preserved
    try:
        config_data = json.loads(AIRPORT_FILE.read_text())
    except Exception:
        config_data = {}

    # Apply only the fields explicitly included in the request
    # Trim or pad airports to match num_leds if both are present
    target_len = data.get("num_leds") or config_data.get("num_leds")
    if isinstance(target_len, int) and target_len > 0:
        if len(airports) > target_len:
            airports = airports[:target_len]
        while len(airports) < target_len:
            airports.append("NONE")
    config_data["airports"] = airports

    if "home" in data:
        home = (data["home"] or "").strip().upper()
        config_data["home"] = home  # empty string is valid (clears home)
    else:
        home = config_data.get("home", "")

    if "num_leds" in data:
        num_leds = data["num_leds"]
        if isinstance(num_leds, int) and num_leds > 0:
            config_data["num_leds"] = num_leds
    else:
        num_leds = None

    if "timezone" in data:
        timezone = (data["timezone"] or "").strip()
        if timezone:
            config_data["timezone"] = timezone
        else:
            config_data.pop("timezone", None)
    else:
        timezone = None

    def _parse_colors(raw) -> dict | None:
        """Convert {cat: "#rrggbb"} to {cat: [R, G, B]}, return None if invalid."""
        if not isinstance(raw, dict):
            return None
        result = {}
        for cat, hex_val in raw.items():
            if not isinstance(hex_val, str) or len(hex_val) != 7 or hex_val[0] != "#":
                return None
            try:
                result[cat] = [int(hex_val[1:3], 16), int(hex_val[3:5], 16), int(hex_val[5:7], 16)]
            except ValueError:
                return None
        return result

    new_colors = None
    new_dim_colors = None
    if "colors" in data:
        parsed = _parse_colors(data["colors"])
        if parsed is not None:
            config_data["colors"] = parsed
            new_colors = parsed
    if "dim_colors" in data:
        parsed = _parse_colors(data["dim_colors"])
        if parsed is not None:
            config_data["dim_colors"] = parsed
            new_dim_colors = parsed

    try:
        validate_config(config_data)
    except ValueError as exc:
        return {"error": str(exc)}

    AIRPORT_FILE.write_text(json.dumps(config_data, indent=2))

    # Hot-update runtime state where safe to do so
    state.current_airports = airports
    if num_leds is not None and isinstance(num_leds, int) and num_leds > 0:
        if state.strip is not None and num_leds != state.strip.numPixels():
            state.strip_needs_reinit = True
            state.refresh_event.set()  # wake the main loop so reinit happens promptly
        state.LED_COUNT = num_leds
    if timezone is not None:
        state.status_display["timezone"] = timezone or None
    if new_colors is not None:
        state.COLOR_MAP.update({k: tuple(v) for k, v in new_colors.items()})
    if new_dim_colors is not None:
        state.COLOR_MAP_DIM.update({k: tuple(v) for k, v in new_dim_colors.items()})

    logger.info("Config saved via web UI — %d airports, home=%s", len(airports), home or "unset")
    return {"ok": True}


# ── HTTP handler ──────────────────────────────────────────────────────────────

_FLASH_RE = re.compile(r"^/api/leds/(\d+)/flash$")


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/":
            self.send_html(load_template())
        elif self.path == "/api/status":
            self.send_json(get_status_json())
        elif self.path == "/api/config":
            self.send_json(handle_get_config())
        elif self.path == "/api/config/download":
            try:
                raw = AIRPORT_FILE.read_bytes()
            except Exception:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Disposition", 'attachment; filename="config.json"')
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        elif self.path == "/api/debug":
            self.send_json(handle_get_debug())
        elif self.path.startswith("/api/logs"):
            from urllib.parse import parse_qs, urlparse
            qs = parse_qs(urlparse(self.path).query)
            lines = int(qs.get("lines", ["100"])[0])
            self.send_json(handle_get_logs(lines))
        elif self.path == "/api/wifi":
            self.send_json(handle_get_wifi())
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if self.path == "/api/leds/clear":
            self.send_json(handle_clear_leds())
        elif m := _FLASH_RE.match(self.path):
            self.send_json(handle_flash_led(int(m.group(1))))
        elif self.path == "/api/config":
            length = int(self.headers.get("Content-Length", 0))
            self.send_json(handle_save_config(self.rfile.read(length)))
        elif self.path == "/api/refresh":
            self.send_json(handle_refresh())
        elif self.path == "/api/leds/test":
            self.send_json(handle_test_colors())
        elif self.path == "/api/wifi":
            length = int(self.headers.get("Content-Length", 0))
            self.send_json(handle_add_wifi(self.rfile.read(length)))
        elif self.path == "/api/wifi/delete":
            length = int(self.headers.get("Content-Length", 0))
            self.send_json(handle_delete_wifi(self.rfile.read(length)))
        else:
            self.send_error(404)

    def send_html(self, html: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_json(self, data: dict) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args) -> None:
        pass


def start_web_server(port: int = 80) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), WebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Web server started on port %d", port)
    return server
