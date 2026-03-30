import asyncio
import machine
import webrepl
from boot import sta
import logging


from config import JSONConfig
from machine import Pin

from mylib.queue import Queue
from mylib.one_shot_timer import OneShotTimer
from controllers.blec import BLEController
from controllers.sensor_lux import SensorLUX
from mylib.file_logger import FileLogger
from controllers.status_led import StatusLED
from controllers.motion_radar import MotionRadar
from controllers.led_strip import LEDStrip

from defs import BLEC_CHARACTERISTIC_GETCFG, BLEC_CMD_SET_LIGHT_LEVEL, BLEC_CMD_SET_LIGHT_STATE, BLEC_SUBCMD_SYSTEM_RESET, BLEC_SUBCMD_SYSTEM_TURN_OFF_WIRELESS, RGBLED_STATUS_BTOFF
from defs import RGBLED_STATUS_BOOTED, RGBLED_STATUS_CONNECTED, RGBLED_STATUS_ERROR
from defs import BLEC_NOTIFICATION_SENSORS, BLEC_NOTIFICATION_TEXT, BLEC_CMD_SETCFG, BLEC_CMD_SYSTEM
from defs import Dict, Any, List, Optional
from defs import safe_async_call, safe_call, log_memory_status

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pin_dimmer_control: Pin
    status_led: StatusLED
    led_strip: LEDStrip

timer_light: OneShotTimer

blec: BLEController
cfg: JSONConfig
flog: FileLogger
lux_sensor: SensorLUX
motion_radar: MotionRadar

main_tasks: Optional[List[asyncio.Task[Any]]] = None
last_task_exception: Optional[Exception]
failed_task_name: Optional[str] = None

log = logging.getLogger("[Main]")
log.setLevel(logging.DEBUG)

quit_event: asyncio.Event

@safe_call(log)
def get_sensors_status() -> bytes | None:
    status: bytes = b''

    led_strip_on = int(led_strip.is_on())
    lux = int(lux_sensor.read_lux())
    radar_report = motion_radar.get_last_report()
    motion_state = motion_radar.get_motion_state()

    energies = [0] * 14
    if radar_report and "moving_gate_energies" in radar_report:
        energies = radar_report["moving_gate_energies"]
    else:
        return None

    status += led_strip_on.to_bytes(1, 'big')
    status += lux.to_bytes(2, 'big')
    status += bytes(energies)
    status += bytes(chr(motion_state), "utf-8")
    
    return status

@safe_async_call(log)
async def power_led_strip(state: bool, energies: List) -> None:
    ambient_light = lux_sensor.read_lux()

    ambient_light_threshold = cfg.get("ambient_light_threshold")
    light_level = cfg.get("light_level")
    light_on_time = cfg.get("light_on_time") * 1000
    energies_text = ''.join('%4d' % n for n in energies)
    
    if state == False:
        log.debug("Turning LED strip off")
        notification = "⚫ LED strip off [light_level=%d] [ambient_light=%d] [energies=[%s]]" % (light_level, ambient_light, energies_text)
        blec.notify(BLEC_NOTIFICATION_TEXT, notification.encode())
        await led_strip.power(False)
        timer_light.cancel()
        return

    if ambient_light < ambient_light_threshold:

        if led_strip.get_state() != state or led_strip.get_target_level() != light_level:
            log.debug("Turning LED strip on")
            notification = "⚪ LED strip on [light_level=%d] [ambient_light=%d] [energies=[%s]]" % (light_level, ambient_light, energies_text)
            blec.notify(BLEC_NOTIFICATION_TEXT, notification.encode())
            await led_strip.power(True, light_level)
        else:
            log.debug("Resetting timer")


        try:
            timer_light.start(light_on_time, lambda t: power_led_strip(False, energies))
        except Exception as e:
            app_error("Error initializing timer: %s" % e, e)
            log.exception("Error initializing timer: %s" % e)

@safe_async_call(log)
async def motion_event_handler(state: bool, energies: List) -> None:
    log.debug('motion_event_handler')
    if state == True:
        await power_led_strip(state, energies)

async def motion_radar_event_loop() -> None:
    await motion_radar.event_loop()

@safe_async_call(log)
async def blec_cmd_callback(cmd: int, payload: bytes) -> None:
    if not payload:
        log.error("Empty payload for command: 0x%02X" % cmd)
        return
        
    if cmd == BLEC_CMD_SYSTEM:
        if len(payload) < 1:
            log.error("BLEC_CMD_SYSTEM: payload too short")
            return
        subcmd = payload[0]
        if subcmd == BLEC_SUBCMD_SYSTEM_TURN_OFF_WIRELESS:
            log.info("Stopping wireless services...")
            try:
                blec.stop(True)
                webrepl.stop()
                log.info("Wireless services stopped")
            except Exception as e:
                app_error("Error stopping wireless services: %s" % e, e)
                log.exception("Error stopping wireless services: %s" % e)
        if subcmd == BLEC_SUBCMD_SYSTEM_RESET:
            log.info("Performing a hard reset...")
            await cleanup(True)
            machine.reset()

    elif cmd == BLEC_CMD_SET_LIGHT_LEVEL:
        if len(payload) < 1:
            log.error("BLEC_CMD_SET_LIGHT_LEVEL: payload too short")
            return
        light_level = payload[0]
        await led_strip.power(True, light_level)
                
    elif cmd == BLEC_CMD_SET_LIGHT_STATE:
        if len(payload) < 1:
            log.error("BLEC_CMD_SET_LIGHT_STATE: payload too short")
            return
        state = bool(payload[0])
        await led_strip.power(state)

    elif cmd == BLEC_CMD_SETCFG:
        try:
            merged_config = cfg.merge_config(payload.decode("utf-8"))
            log.debug("config received: %s" % merged_config)
            if merged_config is not None:
                if "energy_threshold" in merged_config:
                    motion_radar.set_energy_threshold(merged_config["energy_threshold"])
                config = cfg.json()
                log.info("Config saved: %s" % config)
                blec.set_characteristic_value(BLEC_CHARACTERISTIC_GETCFG, config)
        except UnicodeDecodeError as e:
            log.exception("Malformed config payload: %s" % payload)
    
    else:
        log.error("Unknown command: 0x%02X" % cmd)
    
@safe_async_call(log)
async def blec_on_start() -> None:
    status_led.status(RGBLED_STATUS_BOOTED)
    
    blec.set_characteristic_value(BLEC_CHARACTERISTIC_GETCFG, cfg.json())

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
    status_led.status(RGBLED_STATUS_BTOFF)

def initialize_variables() -> None:
    global timer_light, flog, quit_event

    timer_light = OneShotTimer()
    flog = FileLogger("log.txt", max_bytes=100_000, backups=2)
    quit_event = asyncio.Event()

def initialize_blec() -> None:    
    global blec

    device_name = cfg.get("device_name")

    blec = BLEController(device_name)

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

def load_config():
    global cfg

    log.info('Loading config...')
    cfg = JSONConfig(default={})
    cfg.load()
    log.info('Config loaded')

def verify_config():
    for param in ["light_on_time", "ambient_light_threshold", "energy_threshold", "device_name", "light_level"]:
        if cfg.get(param) is None:
            raise Exception("%s not configured" % param)

async def main() -> None:
    global last_task_exception, failed_task_name, main_tasks


    try:
        last_task_exception = None
        failed_task_name = None
        initialize_variables()

        load_config()
        verify_config()

        initialize_lux_sensor()
        initialize_radar()
        initialize_blec()

        flog.info("main(): Initialized")
        
        try:
            motion_radar.start(poll_interval_ms=100)
            main_tasks = [
                asyncio.create_task(watch_task(status_led.start(), "status_led.start")),
                asyncio.create_task(watch_task(blec.start(), "blec.start")),
                asyncio.create_task(watch_task(motion_radar_event_loop(), "motion_radar.event_loop")),
            ]
            await asyncio.sleep_ms(100)
        except Exception as e:
            status_led.status(RGBLED_STATUS_ERROR)
            app_error("Creating tasks", e)

        status_led.status(RGBLED_STATUS_BOOTED)

        memory_log_counter = 0

        
        while not quit_event.is_set():
            await asyncio.sleep_ms(500)
            if quit_event.is_set():
                break

            ambient_light_threshold = cfg.get("ambient_light_threshold")
            lux = lux_sensor.read_lux()

            if lux <= ambient_light_threshold:
                if not motion_radar.is_running():
                    motion_radar.start(poll_interval_ms=10)
                    log.debug("Reading radar: back on")
                    blec.notify(BLEC_NOTIFICATION_TEXT, "Reading radar: back on".encode())
            elif lux > ambient_light_threshold + 20:
                if motion_radar.is_running():
                    motion_radar.stop()
                    log.debug("Reading radar: off")
                    blec.notify(BLEC_NOTIFICATION_TEXT, "Reading radar: off".encode())

            status_sensors = get_sensors_status()
            if status_sensors is not None:
                blec.notify(BLEC_NOTIFICATION_SENSORS, status_sensors)

            if last_task_exception is not None:
                raise last_task_exception

            memory_log_counter += 1
            if memory_log_counter % 1200 == 0:  # Every 10 minutes
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
        await cleanup()


async def cleanup(manual: bool=False):
    log.info(f"Cleaning up [manual={manual}]...")
    quit_event.set()

    # Cancel all tasks
    if not main_tasks:
        log.info("No tasks have been registed.")
        return

    for task in main_tasks:
        if task and not task.done():
            task.cancel()
    
    # Wait for all tasks to complete cancellation
    await asyncio.gather(*main_tasks, return_exceptions=True)
    
    # Cleanup resources
    try:
        timer_light.cancel()
    except Exception as e:
        app_error("Error cancelling timer: %s" % e, e)
        log.exception("Error cancelling timer: %s" % e)
    
    # Ensure BLE and WiFi are stopped
    try:
        blec.stop(True)
        motion_radar.stop()
    except Exception as e:
        app_error("Error stopping services: %s" % e, e)
        log.exception("Error stopping services: %s" % e)

    log.info("Cleanup complete")

    if not manual:
        app_error("Application crashed")



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


def app_error(error: str, exception: Optional[Exception]=None) -> None:
    if exception:
        status_led.status(RGBLED_STATUS_ERROR)
        flog.exception("🚨 %s" % error, exception)
        log.exception("🚨 %s" % error)
    else:
        flog.error(error)
        log.error(error)


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
