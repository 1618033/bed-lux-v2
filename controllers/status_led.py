from __future__ import annotations

import asyncio
import logging
import neopixel

from defs import RGBLED_STATUS_OFF, RGBLED_STATUS_BOOTED, RGBLED_STATUS_BOOTING, RGBLED_STATUS_CONNECTING, RGBLED_STATUS_CONNECTED, RGBLED_STATUS_ERROR, Dict, Optional, Tuple
from machine import Pin

log: logging.Logger = logging.getLogger("[StatusLED]")
log.setLevel(logging.INFO)

class StatusLED:
    STATUS_OFF = -1

    def __init__(
        self,
        pin_rgb_led: Pin,
        step: int = 5,
        interval_ms: int = 30,
        min_brightness: int = 10,
        max_brightness: int = 100,
    ) -> None:
        self.pin_rgb_led = pin_rgb_led
        self.rgb_led = neopixel.NeoPixel(pin_rgb_led, 1)
        self.step = step
        self.interval_ms = interval_ms
        self.min_brightness = min_brightness
        self.max_brightness = max_brightness

        self._brightness = min_brightness
        self._direction = step
        self._status: int = -1
        self._last_written: Optional[Tuple[int, int, int]] = None

        self._status_colors: Dict[int, Tuple[int, int, int]] = {
            RGBLED_STATUS_OFF: (0, 0, 0),
            RGBLED_STATUS_BOOTING: (150, 0, 0),
            RGBLED_STATUS_BOOTED: (0, 150, 0),
            RGBLED_STATUS_CONNECTING: (0, 0, 150),
            RGBLED_STATUS_CONNECTED: (0, 0, 150),
            RGBLED_STATUS_ERROR: (150, 0, 0),
        }

        self.log = logging.getLogger("[StatusLED]")

    def _get_color_for_status(self, status: int) -> Tuple[int, int, int]:
        return self._status_colors[status]

    def _scale_color(self, color: Tuple[int, int, int], brightness: int) -> Tuple[int, int, int]:
        return tuple((component * brightness) // 100 for component in color)  # pyright: ignore[reportReturnType]

    def _write_color(self, color: Tuple[int, int, int]) -> None:
        if color == self._last_written:
            return

        self.rgb_led[0] = color
        self.rgb_led.write()
        self._last_written = color
        # log.debug("-------------------------------------------Status processing: %d, %d, %d" % color)


    def status(self, status: Optional[int] = None, mandate: bool = False) -> int | None:
        log.debug("Status: %d" % status)

        if status is None:
            return self._status

        if status not in self._status_colors:
            raise ValueError("Status must be an RGBLED_STATUS_* value")

        # if status == self._status:
        #     return None

        log.debug("Status processing: %d" % status)

        self._status = status
        self._brightness = self.min_brightness
        self._direction = self.step
        if mandate:
            self._write_color(self._get_color_for_status(self._status))
        return self._status

    async def start(self) -> None:
        try:
            while True:
                if self._status in [RGBLED_STATUS_OFF, RGBLED_STATUS_BOOTING, RGBLED_STATUS_BOOTED, RGBLED_STATUS_CONNECTED]:
                    self._write_color(self._get_color_for_status(self._status))
                    await asyncio.sleep_ms(self.interval_ms)
                    continue

                if self._status == RGBLED_STATUS_ERROR:
                    self._write_color(self._get_color_for_status(self._status))
                    await asyncio.sleep_ms(200)
                    self._write_color(self._get_color_for_status(RGBLED_STATUS_OFF))
                    await asyncio.sleep_ms(200)
                    continue


                self._write_color(self._scale_color(self._get_color_for_status(self._status), self._brightness))

                self._brightness += self._direction
                if self._brightness >= self.max_brightness:
                    self._brightness = self.max_brightness
                    self._direction = -self.step
                elif self._brightness <= self.min_brightness:
                    self._brightness = self.min_brightness
                    self._direction = self.step

                await asyncio.sleep_ms(self.interval_ms)
        except asyncio.CancelledError:
            self._write_color(self._get_color_for_status(RGBLED_STATUS_OFF))
            self.log.info("Status LED task cancelled")
            raise
