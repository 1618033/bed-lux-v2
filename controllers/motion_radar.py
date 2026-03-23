from __future__ import annotations

import logging
import asyncio 
import time

from defs import Optional
from machine import Pin, UART
from drivers.hlk_ld2412 import HLKLD2412
from helpers import is_awaitable, is_coroutine


log = logging.getLogger("[MotionRadar]")
log.setLevel(logging.DEBUG)


class MotionRadar:
    def __init__(
        self,
        uart_id: int = 2,
        tx_pin: int = 13,
        rx_pin: int = 12,
        baudrate: int = 115200,
        timeout_ms: int = 500,
        uart_timeout: int = 100,
        uart_timeout_char: int = 10,
        motion_hold_time: int = 0,
    ) -> None:
        self._uart = UART(
            uart_id,
            baudrate=baudrate,
            bits=8,
            parity=None,
            stop=1,
            tx=Pin(tx_pin),
            rx=Pin(rx_pin),
            timeout=uart_timeout,
            timeout_char=uart_timeout_char,
        )
        self._radar = HLKLD2412(self._uart, timeout_ms=timeout_ms)
        self._initialized = False
        self._running = False
        self._motion_state = False
        self._motion_hold_time = motion_hold_time
        self._last_motion_ticks: Optional[int] = None

    def motion_event_handler(self, state: bool):
        log.debug('self.motion')

        return

    async def poll(self):
        report = self.read_report()
        if report is None:
            return

        if "moving_gate_energies" not in report:
            self._radar.enable_engineering_mode()
            return
        
        motion_detected = False

        for energy in report["moving_gate_energies"]:
            if energy > 70:
                motion_detected = True
                self._last_motion_ticks = time.ticks_ms()
                break

        if (
            not motion_detected
            and self._motion_hold_time > 0
            and self._last_motion_ticks is not None
        ):
            elapsed = time.ticks_diff(time.ticks_ms(), self._last_motion_ticks)
            if elapsed < self._motion_hold_time:
                motion_detected = True

        if motion_detected == self._motion_state:
            return

        self._motion_state = motion_detected

        try:
            if is_awaitable(self.motion_event_handler(motion_detected)):
                await self.motion_event_handler(motion_detected)  # pyright: ignore[reportGeneralTypeIssues]
        except Exception as e:
            log.error("Error in callback for MotionRadar.motion_detected: %s" % (e))
            raise
        
        log.debug(report['moving_gate_energies'])

    def initialize(self) -> bool:
        try:
            self._radar.flush()
            info = self._radar.read_all_info()
            self._radar.enable_engineering_mode()
        except Exception as exc:
            self._initialized = False
            log.error("LD2412 failed to initialize: %s" % exc)
            return False

        self._initialized = "firmware" in info
        if self._initialized:
            log.debug("LD2412 radar successfully initialized")
        else:
            log.error("LD2412 radar did not return firmware information")

        return self._initialized
        
    async def start(self, poll_interval_ms=10):
        self._running = True
        log.info("LD2412 radar in monitoring mode. Polling every %dms" % poll_interval_ms)
        try:
            while self._running:
                await self.poll()
                await asyncio.sleep_ms(poll_interval_ms)
        except asyncio.CancelledError:
            log.info("Pin monitor task cancelled")
            raise
        finally:
            self._running = False

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False

    def is_connected(self) -> bool:
        return self._initialized

    def read_info(self):
        if not self._initialized and not self.start():
            raise OSError("LD2412 radar is not available")
        return self._radar.read_all_info()

    def read_report(self, timeout_ms: Optional[int] = None):
        if not self._initialized and not self.start():
            raise OSError("LD2412 radar is not available")
        return self._radar.read_report(timeout_ms=timeout_ms)

    def is_motion_detected(self, timeout_ms: Optional[int] = None) -> bool:
        report = self.read_report(timeout_ms=timeout_ms)
        return bool(report and report.get("has_target"))

    @property
    def driver(self) -> HLKLD2412:
        return self._radar
