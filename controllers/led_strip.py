from __future__ import annotations

import asyncio
import logging

from defs import PIN_LEDSTRIP_PWM, Optional
from machine import PWM, Pin
from asyncio import Event, Task


log: logging.Logger = logging.getLogger("[LEDStrip]")
log.setLevel(logging.DEBUG)


class LEDStrip:
    def __init__(
        self,
        pin: int | Pin = PIN_LEDSTRIP_PWM,
        freq: int = 1000,
        fade_time_ms: int = 500,
        step_ms: int = 10,
        max_duty: int = 65535,
    ) -> None:
        self._pin = pin if isinstance(pin, Pin) else Pin(pin, Pin.OUT)
        self._pwm = PWM(self._pin, freq=freq, duty_u16=0)
        self._fade_time_ms = fade_time_ms
        self._step_ms = max(1, step_ms)
        self._max_duty = max(0, min(65535, max_duty))
        self._duty = 0
        self._is_on = False

        self._interrupt_event = Event() 
        self._done_event = Event() 
        self._worker: Optional[Task] = None
        self._current_state = False
        self._current_target_level = -1

    def is_on(self) -> bool:
        return self._is_on

    def duty(self) -> int:
        return self._duty

    def get_target_level(self) -> int:
        return self._current_target_level

    def get_state(self) -> bool:
        return self._current_state

    def set_duty(self, duty: int) -> None:
        duty = max(0, min(self._max_duty, duty))
        self._pwm.duty_u16(duty)
        self._duty = duty
        self._is_on = duty > 0

    async def _fade_to(self, target_duty: int) -> None:
        target_duty = max(0, min(self._max_duty, target_duty))

        if target_duty == self._duty:
            self._is_on = target_duty > 0
            return

        steps = max(1, self._fade_time_ms // self._step_ms)
        start_duty = self._duty
        delta = target_duty - start_duty

        log.debug("Fading LED strip from %d to %d in %d steps" % (start_duty, target_duty, steps))

        for step in range(1, steps + 1):
            if self._interrupt_event.is_set():
                return
            duty = start_duty + (delta * step) // steps
            self.set_duty(duty)
            await asyncio.sleep_ms(self._step_ms)

        self.set_duty(target_duty)

    def _turn_on(self, duty: int | None = None) -> Task:
        target_duty = self._max_duty if duty is None else duty
        log.debug("Turning LED strip on")
        return self._fade_to(target_duty)

    def _turn_off(self) -> Task:
        log.debug("Turning LED strip off")
        return self._fade_to(0)

    async def power(self, state: bool, level: int = 100) -> None:
        if level == 0:
            state = False

        if state == self._current_state and level == self._current_target_level:
            return
        
        self._current_state = state
        self._current_target_level = level

        if self._worker is not None:
            self._interrupt_event.set()
            await self._worker
            self._interrupt_event.clear()
            self._worker = None

        if state:
            self._worker = asyncio.create_task(self._turn_on(int(level * self._max_duty / 100)))
        else:
            self._worker = asyncio.create_task(self._turn_off())

        await asyncio.sleep_ms(10)

    def deinit(self) -> None:
        self.set_duty(0)
        self._pwm.deinit()
        log.info("LED strip PWM deinitialized")
