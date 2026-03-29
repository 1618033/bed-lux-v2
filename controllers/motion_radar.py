from __future__ import annotations

import logging
import asyncio 
import time
import _thread

from defs import Any, Optional, List, Dict
from machine import Pin, UART
from drivers.hlk_ld2412 import HLKLD2412
from mylib.helpers import is_awaitable

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
        energy_threshold: int = 70
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
        self._last_motion_event_ticks: Optional[int] = None
        self._last_report: Optional[Dict[str, Any]] = None
        self._energy_threshold = energy_threshold
        self._lock = _thread.allocate_lock()
        self._thread_id: Optional[int] = None
        self._worker_exception: Optional[Exception] = None
        self._pending_motion_events: List[tuple[bool, List[int]]] = []

    def motion_event_handler(self, state: bool, energies: List) -> None:
        pass

    def poll_once(self) -> None:
        report = self.read_report()
        if report is None:
            return

        if "moving_gate_energies" not in report:
            self._radar.enable_engineering_mode()
            return
        
        now = time.ticks_ms()

        with self._lock:
            energy_threshold = self._energy_threshold
            current_motion_state = self._motion_state
            last_motion_ticks = self._last_motion_ticks
            last_motion_event_ticks = self._last_motion_event_ticks

        motion_detected = False

        for energy in report["moving_gate_energies"]:
            if energy > energy_threshold:
                motion_detected = True
                last_motion_ticks = now
                break

        if (
            not motion_detected
            and self._motion_hold_time > 0
            and last_motion_ticks is not None
        ):
            elapsed = time.ticks_diff(now, last_motion_ticks)
            if elapsed < self._motion_hold_time:
                motion_detected = True
            else:
                last_motion_ticks = None
        elif not motion_detected:
            last_motion_ticks = None

        emit_event = motion_detected != current_motion_state
        if (
            not emit_event
            and motion_detected
            and self._motion_hold_time > 0
            and last_motion_event_ticks is not None
        ):
            elapsed = time.ticks_diff(now, last_motion_event_ticks)
            if elapsed >= self._motion_hold_time:
                emit_event = True

        with self._lock:
            self._last_motion_ticks = last_motion_ticks

            if not emit_event:
                return

            self._motion_state = motion_detected
            self._last_motion_event_ticks = now if motion_detected else None
            self._pending_motion_events.append(
                (motion_detected, list(report["moving_gate_energies"]))
            )

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
    
    def is_running(self):
        return self._running

    def start(self, poll_interval_ms=10) -> bool:
        if self._running:
            return False

        if not self._initialized:
            raise OSError("LD2412 radar is not available")

        self._running = True
        log.info("LD2412 radar in monitoring mode. Polling every %dms" % poll_interval_ms)
        self._thread_id = _thread.start_new_thread(self._thread_main, (poll_interval_ms,))
        return True

    def _thread_main(self, poll_interval_ms: int) -> None:
        try:
            while self._running:
                self.poll_once()
                time.sleep_ms(poll_interval_ms)
        except Exception as exc:
            self._worker_exception = exc
            log.error("Radar worker failed: %s" % exc)
            raise
        finally:
            self._running = False
            self._thread_id = None
            log.info("Radar worker stopped")

    async def event_loop(self, poll_interval_ms: int = 20) -> None:
        while True:
            worker_exception = self.consume_worker_exception()
            if worker_exception is not None:
                raise worker_exception

            event = self.consume_pending_motion_event()
            if event is not None:
                state, energies = event
                res = self.motion_event_handler(state, energies)
                if is_awaitable(res):
                    await res  # pyright: ignore[reportGeneralTypeIssues]
                continue

            if not self._running:
                await asyncio.sleep_ms(100)
                continue

            await asyncio.sleep_ms(poll_interval_ms)

    def stop(self):
        """Stop the monitoring loop."""
        self._running = False

    def is_connected(self) -> bool:
        return self._initialized

    def read_info(self):
        if not self._initialized:
            raise OSError("LD2412 radar is not available")
        return self._radar.read_all_info()

    def get_last_report(self) -> None | Dict[str, Any]:
        with self._lock:
            return self._last_report

    def get_motion_state(self) -> bool:
        with self._lock:
            return self._motion_state

    def read_report(self, timeout_ms: Optional[int] = None):
        if not self._initialized:
            raise OSError("LD2412 radar is not available")
        report = self._radar.read_report(timeout_ms=timeout_ms)
        with self._lock:
            self._last_report = report
        return report

    def is_motion_detected(self, timeout_ms: Optional[int] = None) -> bool:
        report = self.read_report(timeout_ms=timeout_ms)
        return bool(report and report.get("has_target"))

    def set_energy_threshold(self, energy_threshold: int):
        with self._lock:
            self._energy_threshold = energy_threshold

    def consume_pending_motion_event(self) -> None | tuple[bool, List[int]]:
        with self._lock:
            if not self._pending_motion_events:
                return None

            return self._pending_motion_events.pop(0)

    def consume_worker_exception(self) -> Optional[Exception]:
        with self._lock:
            exc = self._worker_exception
            self._worker_exception = None
            return exc

    @property
    def driver(self) -> HLKLD2412:
        return self._radar
