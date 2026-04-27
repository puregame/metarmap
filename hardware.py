"""LED hardware imports with mock fallbacks for non-Pi environments."""

from __future__ import annotations
from typing import List, Tuple

HARDWARE_AVAILABLE = False
try:
    from rpi_ws281x import PixelStrip, Color  # type: ignore
    HARDWARE_AVAILABLE = True
except (ModuleNotFoundError, RuntimeError):
    class Color(tuple):  # type: ignore[no-redef]
        def __new__(cls, r: int, g: int, b: int):
            return super().__new__(cls, (r, g, b))

        def __repr__(self) -> str:
            return f"Color(r={self[0]}, g={self[1]}, b={self[2]})"

    class PixelStrip:  # type: ignore[no-redef]
        def __init__(self, num: int, *args, **kwargs) -> None:
            self._num = num
            self._pixels: List[Tuple[int, int, int]] = [(0, 0, 0)] * num

        def numPixels(self) -> int:
            return self._num

        def setPixelColor(self, i: int, color: Color) -> None:
            if 0 <= i < self._num:
                self._pixels[i] = color

        def show(self) -> None:
            print("LEDs:", " ".join(f"{i}:{c}" for i, c in enumerate(self._pixels)))

        def begin(self) -> None:
            print("[MOCK] PixelStrip initialised with", self._num, "pixels")
