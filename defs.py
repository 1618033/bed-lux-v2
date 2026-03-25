from __future__ import annotations  # keeps annotations from being eagerly evaluated
import logging, gc, micropython
from mylib.helpers import log_memory_status

TYPE_CHECKING = False

if TYPE_CHECKING:
    from typing import Optional as Optional, Callable as Callable, Any as Any, Dict as Dict, Union as Union, Tuple as Tuple, List as List, cast as cast
else:
    # Runtime exports - minimal memory footprint
    # These are only needed if other modules import them
    # They're never evaluated due to string annotations from __future__
    
    # Use built-in types as fallbacks (zero memory overhead)
    Dict = dict
    List = list
    Tuple = tuple
    Any = object
    
    # Lightweight callables
    def Optional(T): return T
    def Union(*args): return args[0] if args else object
    Callable = None  # Special handling if needed
    def cast(typ, val): return val
    
from micropython import const

PIN_SCL = const(1)
PIN_SDA = const(2)

PIN_LEDSTRIP_PWM = const(7)
PIN_RGB_LED = const(21)

RGBLED_STATUS_OFF = const(0)
RGBLED_STATUS_BOOTING = const(1)
RGBLED_STATUS_BOOTED = const(2)
RGBLED_STATUS_CONNECTING = const(3)
RGBLED_STATUS_CONNECTED = const(4)
RGBLED_STATUS_ERROR = const(5)

# https://www.uuidgenerator.net/
BLE_SERVICE_UUID = const('6f30FFFF-6c13-464f-a152-f24a4a1d47f5')
BLE_CMD_UUID = const('6f300000-6c13-464f-a152-f24a4a1d47f5')
BLE_GETCFG_UUID = const('6f300100-6c13-464f-a152-f24a4a1d47f5')
BLE_EVENT_UUID = const('6f300200-6c13-464f-a152-f24a4a1d47f5')
BLE_NOTIFICATION_UUID = const('6f300300-6c13-464f-a152-f24a4a1d47f5')

ADV_INTERVAL_MS = 250_000

BLEC_EVENT_LIGHT_STATE = const(0x00)

BLEC_NOTIFICATION_SENSORS = const(0x00)
BLEC_NOTIFICATION_TEXT = const(0x01)

BLEC_CMD_SYSTEM = const(0x00)
BLEC_CMD_SET_LIGHT_LEVEL = const(0x01)
BLEC_CMD_SETCFG_DIMMER_LEVEL = const(0x02)
BLEC_CMD_SETCFG_HOSTNAME = const(0x03)
BLEC_CMD_SETCFG_LIGHT_ON_TIME = const(0x04)
BLEC_CMD_SETCFG_AMBIENT_LIGHT_THRESHOLD = const(0x05)
BLEC_CMD_SETCFG_ENERGY_THRESHOLD = const(0x06)

BLEC_CHARACTERISTIC_GETCFG = const(0x00)
BLEC_CHARACTERISTIC_EVENT = const(0x10)
BLEC_CHARACTERISTIC_NOTIFICATION = const(0x20)


def safe_async_call(logger: logging.Logger):
    def _safe_async_call(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                logger.error("Error in %s: %s" % (func.__name__, e))
                log_memory_status(logger, simple=False)
                raise
        return wrapper
    return _safe_async_call


def safe_call(logger: logging.Logger):
    def _safe_call(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.error("Error in %s: %s" % (func.__name__, e))
                log_memory_status(logger, simple=False)
                raise
        return wrapper
    return _safe_call
