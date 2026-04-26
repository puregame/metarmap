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

logger = logging.getLogger("metar_led")

_TEMPLATE_PATH = Path(__file__).parent / "templates" / "index.html"


# ── Template ──────────────────────────────────────────────────────────────────

def load_template() -> str:
    return _TEMPLATE_PATH.read_text()


# ── API handlers (pure functions, easy to unit-test) ─────────────────────────

def get_status_json() -> dict:
    return {
        "airports":   state.current_airports,
        "home":       state.status_display.get("home_airport"),
        "timezone":   state.status_display.get("timezone"),
        "last_metar": (
            state.status_display["last_metar"].isoformat()
            if state.status_display.get("last_metar")
            else None
        ),
        "ip_address": state.status_display.get("ip_address"),
        "led_count":  state.LED_COUNT,
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
    if index < 0 or index >= state.strip.numPixels():
        return {"error": f"LED index {index} out of range"}
    from hardware import Color
    from led_control import led_set_single
    for _ in range(3):
        led_set_single(state.strip, index, Color(255, 255, 255))
        time.sleep(0.25)
        led_set_single(state.strip, index, Color(0, 0, 0))
        time.sleep(0.15)
    return {"ok": True}


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

    try:
        validate_config(config_data)
    except ValueError as exc:
        return {"error": str(exc)}

    AIRPORT_FILE.write_text(json.dumps(config_data, indent=2))

    # Hot-update runtime state where safe to do so
    state.current_airports = airports
    if num_leds is not None and isinstance(num_leds, int) and num_leds > 0:
        state.LED_COUNT = num_leds
    if timezone is not None:
        state.status_display["timezone"] = timezone or None

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


def start_web_server(port: int = 8080) -> HTTPServer:
    server = HTTPServer(("0.0.0.0", port), WebHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Web server started on port %d", port)
    return server
