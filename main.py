import asyncio
import time
import webrepl
from boot import sta
from mylib.helpers import is_coroutine, is_awaitable
import logging

from micropython import schedule
from config import JSONConfig
from machine import Pin, I2C

from mylib.queue import Queue
from mylib.one_shot_timer import OneShotTimer
from controllers.blec import BLEController
from controllers.sensor_lux import SensorLUX
from controllers.wlan_ap import APController
from mylib.file_logger import FileLogger
from controllers.status_led import StatusLED
from controllers.motion_radar import MotionRadar
from controllers.led_strip import LEDStrip

from defs import PIN_MOTION, _PIN_NAMES
from defs import RGBLED_STATUS_BOOTED, RGBLED_STATUS_CONNECTED, RGBLED_STATUS_CONNECTING, RGBLED_STATUS_ERROR
from defs import BLEC_NOTIFICATION_SENSORS, BLEC_NOTIFICATION_TEXT, BLEC_EVENT_LIGHT_STATE, BLEC_CHARACTERISTIC_DIMMER_LEVEL, BLEC_CHARACTERISTIC_HOSTNAME, BLEC_CHARACTERISTIC_LIGHT_ON_TIME, BLEC_CHARACTERISTIC_NOTIFICATION, BLEC_CMD_CONTROL_DIMMER, BLEC_CMD_SETCFG_DIMMER_LEVEL, BLEC_CMD_SETCFG_HOSTNAME, BLEC_CMD_SETCFG_LIGHT_ON_TIME, BLEC_CMD_SYSTEM, BLEC_CMD_TOGGLE_SLEEP_MODE
from defs import Dict, Any, List, Optional
from defs import safe_async_call, safe_call, log_memory_status

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pin_dimmer_control: Pin
    pin_blue_led: Pin
    status_led: StatusLED
    led_strip: LEDStrip

event_activate_wireless: asyncio.ThreadSafeFlag
button_press_start_ticks: int

display_queue: Queue
power_light_queue: Queue

timer_light: OneShotTimer

blec: BLEController
apc: APController
cfg: JSONConfig
flog: FileLogger
lux_sensor: SensorLUX
motion_radar: MotionRadar

log = logging.getLogger("[Main]")
log.setLevel(logging.DEBUG)

sleep_mode: asyncio.Event
last_task_exception: Optional[Exception] = None
failed_task_name: Optional[str] = None

@safe_call(log)
def get_sensors_status() -> bytes | None:
    status: bytes = b''


    led_strip_on = int(led_strip.is_on())
    lux = int(lux_sensor.read_lux())
    radar_report = motion_radar.get_last_report()

    energies = [0] * 14
    if radar_report and "moving_gate_energies" in radar_report:
        energies = radar_report["moving_gate_energies"]
    else:
        return None

    status += led_strip_on.to_bytes(1, 'big')
    status += lux.to_bytes(2, 'big')
    status += bytes(energies)
    
    return status


@safe_async_call(log)
async def power_led_strip(state: bool, energies: List) -> None:
    ambient_light = lux_sensor.read_lux()

    light_on_threshold = cfg.get("light_on_threshold")
    if light_on_threshold is None:
        log.error("light_on_time not configured")
        return

    light_on_time_raw = cfg.get("light_on_time")
    if light_on_time_raw is None:
        log.error("light_on_time not configured")
        return
    light_on_time = light_on_time_raw * 1000
    
    if state == False:
        log.debug("Turning LED strip off")
        await led_strip.power(False)
        timer_light.cancel()
        blec.trigger(BLEC_EVENT_LIGHT_STATE, int(False).to_bytes(1, 'big'))
        return

    if ambient_light < light_on_threshold:
        log.debug("Turning LED strip on")
        await led_strip.power(True)
        blec.trigger(BLEC_EVENT_LIGHT_STATE, int(True).to_bytes(1, 'big'))

        try:
            timer_light.start(light_on_time, lambda t: power_led_strip(False, energies))
        except Exception as e:
            app_error("Error initializing timer: %s" % e, e)
            log.exception("Error initializing timer: %s" % e)

@safe_async_call(log)
async def motion_event_handler(state: bool, energies: List) -> None:
    if state == True:
        await power_led_strip(state, energies)

@safe_async_call(log)
async def blec_cmd_callback(cmd: int, payload: bytes) -> None:
    if not payload:
        log.error("Empty payload for command: 0x%02X" % cmd)
        return
        
    if cmd == BLEC_CMD_SYSTEM:
        if len(payload) < 1:
            log.error("BLEC_CMD_SYSTEM: payload too short")
            return
        cmd_sys = payload[0]
        if cmd_sys == 0xFF:
            log.info("Stopping wireless services...")
            try:
                blec.stop(True)
                await apc.stop()
                webrepl.stop()
                log.info("Wireless services stopped")
            except Exception as e:
                app_error("Error stopping wireless services: %s" % e, e)
                log.exception("Error stopping wireless services: %s" % e)
            
    elif cmd == BLEC_CMD_CONTROL_DIMMER:
        if len(payload) < 1:
            log.error("BLEC_CMD_CONTROL_DIMMER: payload too short")
            return
        state = payload[0]
        try:
            pin_blue_led.value(state)
            pin_dimmer_control.value(state)
            log.info("Dimmer control: %s" % state)
        except Exception as e:
            app_error("Error controlling dimmer: %s" % e, e)
            log.exception("Error controlling dimmer: %s" % e)
            
    elif cmd == BLEC_CMD_TOGGLE_SLEEP_MODE:
        if len(payload) < 1:
            log.error("BLEC_CMD_TOGGLE_SLEEP_MODE: verification payload too short")
            return

        if sleep_mode.is_set():
            notification = "Turning sleep mode OFF"
            sleep_mode.clear()
        else:
            notification = "Turning sleep mode ON"
            sleep_mode.set()

        blec.notify(BLEC_NOTIFICATION_TEXT, notification.encode())
        log.debug(notification)
    elif cmd == BLEC_CMD_SETCFG_DIMMER_LEVEL:
        if len(payload) < 1:
            log.error("BLEC_CMD_SETCFG_DIMMER_LEVEL: payload too short")
            return
        dimmer_level = payload[0]
        try:
            cfg.set("dimmer_level", dimmer_level)
            cfg.save()
            blec.set_characteristic_value(BLEC_CHARACTERISTIC_DIMMER_LEVEL, str(dimmer_level))
            log.info("Dimmer level config saved: %d" % dimmer_level)
        except Exception as e:
            app_error("Error saving dimmer level: %s" % e, e)
            log.exception("Error saving dimmer level: %s" % e)
    elif cmd == BLEC_CMD_SETCFG_HOSTNAME:
        try:
            hostname = payload.decode("utf-8")
            if not hostname:
                log.error("Empty hostname provided")
                return
            cfg.set("hostname", hostname)
            cfg.save()
            blec.set_characteristic_value(BLEC_CHARACTERISTIC_HOSTNAME, hostname)     
            log.info("Hostname saved: %s" % hostname)
        except UnicodeDecodeError as e:
            app_error("Invalid hostname encoding: %s" % e, e)
            log.exception("Invalid hostname encoding: %s" % e)
        except Exception as e:
            app_error("Error saving hostname: %s" % e, e)
            log.exception("Error saving hostname: %s" % e)
    elif cmd == BLEC_CMD_SETCFG_LIGHT_ON_TIME:
        if len(payload) < 4:
            log.error("BLEC_CMD_SETCFG_LIGHT_ON_TIME: payload too short")
            return
        try:
            light_on_time = int.from_bytes(payload, 'big')
            cfg.set("light_on_time", light_on_time)
            cfg.save()
            blec.set_characteristic_value(BLEC_CHARACTERISTIC_LIGHT_ON_TIME, light_on_time.to_bytes(4, 'big'))
            log.info("Light on time config saved: %d" % light_on_time)
        except Exception as e:
            app_error("Error saving light on time: %s" % e, e)
            log.exception("Error saving light on time: %s" % e)
    else:
        log.error("Unknown command: 0x%02X" % cmd)
    
@safe_async_call(log)
async def blec_on_start() -> None:
    status_led.status(RGBLED_STATUS_BOOTED)

    cfg_dimmer_level = cfg.get("dimmer_level")
    if cfg_dimmer_level is not None:
        blec.set_characteristic_value(BLEC_CHARACTERISTIC_DIMMER_LEVEL, str(cfg_dimmer_level))
    
    cfg_hostname = cfg.get("hostname")
    if cfg_hostname:
        blec.set_characteristic_value(BLEC_CHARACTERISTIC_HOSTNAME, cfg_hostname)

    cfg_light_on_time = cfg.get("light_on_time")
    if cfg_light_on_time is not None:
        blec.set_characteristic_value(BLEC_CHARACTERISTIC_LIGHT_ON_TIME, cfg_light_on_time.to_bytes(4, 'big'))
    
    status_sensors = get_sensors_status()
    if status_sensors is not None:
        blec.notify(BLEC_NOTIFICATION_SENSORS, status_sensors)

@safe_async_call(log)
async def blec_on_connect() -> None:
    status_led.status(RGBLED_STATUS_CONNECTED)

@safe_async_call(log)
async def blec_on_disconnect() -> None:
    status_led.status(RGBLED_STATUS_BOOTED)

@safe_async_call(log)
async def blec_on_stop() -> None:
    status_led.status(StatusLED.STATUS_OFF)

@safe_async_call(log)
async def apc_on_start(ip: str) -> None:
    webrepl.start()

@safe_async_call(log)
async def apc_on_stop() -> None:
    webrepl.stop()

def initialize_variables() -> None:
    global display_queue, power_light_queue, event_activate_wireless, button_press_start_ticks
    global timer_light, pin_monitor, flog, sleep_mode, status_led

    event_activate_wireless = asyncio.ThreadSafeFlag()
    button_press_start_ticks = -1
    display_queue = Queue()
    power_light_queue = Queue()
    timer_light = OneShotTimer()
    flog = FileLogger("log.txt", max_bytes=100_000, backups=2)
    sleep_mode = asyncio.Event()


        # blec.notify(BLEC_NOTIFICATION_SENSORS, get_sensors_status())
        # log.debug("%s %s -> %s" % (_PIN_NAMES[pin_num], prev_state, new_state))
        # flog.debug("on_pin_state_change(): %s %s -> %s" % (_PIN_NAMES[pin_num], prev_state, new_state))

def initialize_blec() -> None:    
    global blec

    blec = BLEController("Bed Lux Brain v2 R")

    blec.on_start = blec_on_start
    blec.on_connect = blec_on_connect
    blec.on_disconnect = blec_on_disconnect
    blec.on_stop = blec_on_stop
    blec.on_error = app_error

    blec.cmd_callback = blec_cmd_callback

def initialize_lux_sensor() -> None:    
    global lux_sensor

    lux_sensor = SensorLUX(0x10)
    lux_sensor.start()


def initialize_radar() -> None:
    global motion_radar
    energy_threshold = cfg.get("energy_threshold")
    motion_radar = MotionRadar(baudrate=460800, motion_hold_time=1000, energy_threshold=energy_threshold)
    motion_radar.motion_event_handler = motion_event_handler
    motion_radar.initialize()



def initialize_apc() -> None:
    global apc

    # @safe_async_call(log)
    # async def apc_on_client_connect_wrapper(mac: str) -> None:
    #     update_display(wlan=apc.client_count())
    
    # @safe_async_call(log)
    # async def apc_on_client_disconnect_wrapper(mac: str) -> None:
    #     update_display(wlan=apc.client_count())
    
    apc = APController("Bed Lux Brain v2 R", "bedluxbrainpass")

    apc.on_start = apc_on_start
    # apc.on_client_connect = apc_on_client_connect_wrapper
    # apc.on_client_disconnect = apc_on_client_disconnect_wrapper
    apc.on_stop = apc_on_stop

def load_config():
    global cfg
    log.info('Loading config...')
    cfg = JSONConfig(default={"dimmer_level": 255, "hostname": "bed-lux-device", "light_on_time": 5})
    cfg.load()
    log.info('Config loaded')

def app_error(error: str, exception: Optional[Exception]=None) -> None:
    if exception:
        status_led.status(RGBLED_STATUS_ERROR)
        flog.exception("🚨 %s" % error, exception)
    else:
        flog.error(error)

async def watch_task(coro, name: str) -> None:
    global last_task_exception, failed_task_name
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:
        last_task_exception = e
        failed_task_name = name
        raise


async def main() -> None:
    global last_task_exception, failed_task_name
    tasks: List[asyncio.Task[Any]] = []


    try:
        last_task_exception = None
        failed_task_name = None
        load_config()

        initialize_variables()
        initialize_lux_sensor()
        initialize_radar()
        initialize_blec()
        initialize_apc()

        flog.info("main(): Initialized")
        
        try:
            tasks = [
                asyncio.create_task(watch_task(status_led.start(), "status_led.start")),
                asyncio.create_task(watch_task(apc.start(), "apc.start")),
                asyncio.create_task(watch_task(blec.start(), "blec.start")),
                asyncio.create_task(watch_task(motion_radar.start(poll_interval_ms=10), "motion_radar.start")),
            ]
            await asyncio.sleep_ms(100)
        except Exception as e:
            status_led.status(RGBLED_STATUS_ERROR)
            app_error("Creating tasks", e)

        status_led.status(RGBLED_STATUS_BOOTED)

        memory_log_counter = 0
        
        while True:
            await asyncio.sleep_ms(500)

            light_on_threshold = cfg.get("light_on_threshold")
            lux = lux_sensor.read_lux()
            log.debug("Lux %d" % lux)

            if lux <= light_on_threshold:
                if not motion_radar.is_running():
                    mr_task = asyncio.create_task(watch_task(motion_radar.start(poll_interval_ms=10), "motion_radar.start"))
                    tasks.append(mr_task)
                    log.debug("Turning radar back on")

            elif lux > light_on_threshold + 20:
                motion_radar.stop()
                log.debug("Turning radar off")


            status_sensors = get_sensors_status()
            if status_sensors is not None:
                blec.notify(BLEC_NOTIFICATION_SENSORS, status_sensors)


            if last_task_exception is not None:
                raise last_task_exception

            memory_log_counter += 1
            if memory_log_counter % 120 == 0:  # Every 10 minutes
                text = log_memory_status(log, flog)
                blec.notify(BLEC_NOTIFICATION_TEXT, text.encode())
                


    except asyncio.CancelledError:
        log.info("Main loop cancelled")
        raise
    except Exception as e:
        app_error("Error in main loop: %s" % e, e)
        log.exception("Error in main loop: %s" % e)
        raise

    finally:
        log.info("Cleaning up...")
        # Cancel all tasks
        for task in tasks:
            if task and not task.done():
                task.cancel()
        
        # Wait for all tasks to complete cancellation
        await asyncio.gather(*tasks, return_exceptions=True)
        
        # Cleanup resources
        try:
            timer_light.cancel()
        except Exception as e:
            app_error("Error cancelling timer: %s" % e, e)
            log.exception("Error cancelling timer: %s" % e)
        
        # Ensure BLE and WiFi are stopped
        try:
            await apc.stop()
            blec.stop(True)
            motion_radar.stop()
        except Exception as e:
            app_error("Error stopping services: %s" % e, e)
            log.exception("Error stopping services: %s" % e)

        log.info("Cleanup complete")
        
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info('Ctrl+C pressed')
    except Exception as e:
        app_error("Fatal error: %s" % e, e)
        log.exception("Fatal error: %s" % e)
        raise e
    finally:
        asyncio.new_event_loop()
