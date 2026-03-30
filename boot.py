import network, bluetooth, time, logging
from machine import Pin
from defs import PIN_SCL, PIN_SDA, PIN_LEDSTRIP_PWM, PIN_RGB_LED
from defs import RGBLED_STATUS_BOOTING
from mylib.helpers import log_memory_status
from controllers.status_led import StatusLED
from controllers.led_strip import LEDStrip


logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - [%(levelname)s][BLX]%(name)s %(message)s")

log: logging.Logger = logging.getLogger("[Boot]")
log.setLevel(logging.DEBUG)

log.info('Booting...')

log_memory_status(log, simple=False)

pin_scl = Pin(PIN_SCL)
pin_sda = Pin(PIN_SDA)

# pin_ledstrip_pwm = Pin(PIN_LEDSTRIP_PWM, Pin.OUT)
pin_rgb_led = Pin(PIN_RGB_LED, Pin.OUT)

status_led = StatusLED(pin_rgb_led)
status_led.status(RGBLED_STATUS_BOOTING, True)

led_strip = LEDStrip(pin=PIN_LEDSTRIP_PWM, step_ms=1, fade_time_ms=500, freq=500)

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
except Exception as e:
    log.warning("Error deactivating wireless functions: %s" % e)

