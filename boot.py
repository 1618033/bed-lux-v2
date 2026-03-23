import network, bluetooth, time, logging, micropython, neopixel
from machine import Pin
from defs import PIN_SCL, PIN_SDA, PIN_MOTION, PIN_LEDSTRIP_PWM, PIN_RGB_LED
from defs import RGBLED_STATUS_BOOTING
from helpers import log_memory_status
from status_led import StatusLED
from motion_radar import MotionRadar

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - [%(levelname)s][BLX]%(name)s %(message)s")

log: logging.Logger = logging.getLogger("[Boot]")
log.setLevel(logging.DEBUG)

log.info('Booting...')

log_memory_status(log, simple=False)

pin_scl = Pin(PIN_SCL)
pin_sda = Pin(PIN_SDA)

pin_ledstrip_pwm = Pin(PIN_LEDSTRIP_PWM, Pin.OUT)
pin_motion = Pin(PIN_MOTION, Pin.IN, Pin.PULL_DOWN)
pin_rgb_led = Pin(PIN_RGB_LED, Pin.OUT)

status_led = StatusLED(pin_rgb_led)

status_led.status(RGBLED_STATUS_BOOTING, True)

motion_radar = MotionRadar(baudrate=460800, motion_hold_time=1000)

sta = network.WLAN(network.STA_IF)
ap = network.WLAN(network.AP_IF)
ble = bluetooth.BLE()
        # Ensure WiFi is deinitialized first
try:
    sta.active(False)
    ap.active(False)
    ble.active(False)
    time.sleep_ms(500)  # Give WiFi time to deinitialize
    ble.active(True)
    ap.active(True)
except Exception as e:
    log.warning("Error deactivating wireless functions: %s" % e)

