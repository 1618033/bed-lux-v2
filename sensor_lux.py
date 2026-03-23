from __future__ import annotations

import logging

from defs import Optional
from defs import PIN_SCL, PIN_SDA
from drivers.veml7700 import VEML7700


log = logging.getLogger("[SensorLUX]")
log.setLevel(logging.DEBUG)


class SensorLUX:
    def __init__(
        self,
        address: Optional[int] = None,
        gain: Optional[float] = None,
        integration_time: Optional[int] = None,
    ) -> None:
        self._sensor = VEML7700(PIN_SDA, PIN_SCL, address=address)
        self._gain = gain
        self._integration_time = integration_time
        self._initialized = False

    def start(self) -> bool:
        if not self._sensor.begin():
            self._initialized = False
            log.error("VEML7700 sensor not found or failed to initialize")
            return False

        if self._gain is not None:
            self._sensor.set_gain(self._gain)

        if self._integration_time is not None:
            self._sensor.set_integ_time(self._integration_time)

        self._initialized = True
        log.debug("VEML7700 sensor successfully initialized")
        return True

    def is_connected(self) -> bool:
        return self._sensor.is_connected()

    def read_lux(self) -> float:
        if not self._initialized and not self.start():
            log.error("VEML7700 is not available")
            raise OSError("VEML7700 is not available")
        return self._sensor.read_light()
