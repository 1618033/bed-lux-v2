import uasyncio as asyncio
import time, logging

from machine import Pin
from helpers import is_coroutine
from defs import _PIN_NAMES

log: logging.Logger = logging.getLogger("[PinMonitor]")
log.setLevel(logging.DEBUG)

class PinMonitor:
    """
    Asynchronous GPIO pin monitor without interrupts, with debouncing and callbacks.
    """
    
    def __init__(self):
        self.pins = {}
        self._running = False

    async def on_pin_state_change(self, pin_num: int, new_state: bool, prev_state: bool) -> None:
        pass
    
    def add_pin(self, pin_num, callback=None, debounce_ms=50, invert=False):
        """
        Add a pin to monitor.
        
        Args:
            pin_num: GPIO pin number
            mode: Pin.IN (input mode)
            pull: Pin.PULL_UP, Pin.PULL_DOWN, or None
            callback: Function to call on state change, receives (pin_num, new_state)
                     Can be sync or async function
            debounce_ms: Debounce time in milliseconds
        """
        pin = Pin(pin_num)
        initial_state = bool(pin.value())
        if invert:
            initial_state = not initial_state
        log.debug("Pin now being monitored: %s" % _PIN_NAMES[pin_num])
        
        self.pins[pin_num] = {
            'pin': pin,
            'callback': callback,
            'debounce_ms': debounce_ms,
            'last_state': initial_state,
            'last_change_time': time.ticks_ms(),
            'pending_state': None,
            'pending_time': None,
            'invert': invert,
        }
    
    def remove_pin(self, pin_num):
        """Remove a pin from monitoring."""
        if pin_num in self.pins:
            del self.pins[pin_num]
            log.debug("Pin removed from monitoring: %s" % _PIN_NAMES[pin_num])
    
    def set_callback(self, pin_num, callback):
        """Update the callback for a specific pin."""
        if pin_num in self.pins:
            self.pins[pin_num]['callback'] = callback
    
    async def poll(self):
        """
        Poll all monitored pins once.
        This is called automatically by run() but can be called manually.
        """
        current_time = time.ticks_ms()
        
        for pin_num, pin_data in self.pins.items():
            pin = pin_data['pin']
            current_state = bool(pin.value())
            if pin_data['invert']:
                current_state = not current_state
            last_state = pin_data['last_state']
            
            # Check if state is different from last confirmed state
            if current_state != last_state:
                # If this is a new change, record it

                if pin_data['pending_state'] != current_state:
                    pin_data['pending_state'] = current_state
                    pin_data['pending_time'] = current_time
                # If the state has been stable for debounce period
                elif time.ticks_diff(current_time, pin_data['pending_time']) >= pin_data['debounce_ms']:
                    # Confirm the state change
                    pin_data['last_state'] = current_state
                    pin_data['last_change_time'] = current_time
                    pin_data['pending_state'] = None
                    
                    # Call the callback if one is registered
                    if pin_data['callback']:
                        await self.on_pin_state_change(pin_num, current_state, last_state)
                        try:
                            if is_coroutine(pin_data['callback']):
                                await pin_data['callback'](current_state)
                            else:
                                pin_data['callback'](current_state)
                        except Exception as e:
                            log.error("Error in callback for pin %s: %s" % (pin_num, e))
                            raise
            else:
                # State matches confirmed state, clear any pending change
                pin_data['pending_state'] = None
    
    async def start(self, poll_interval_ms=10):
        """
        Run the monitor as an async task.
        
        Args:
            poll_interval_ms: Time between polls in milliseconds
        """
        self._running = True
        log.info("Pin monitor running. Polling every %dms" % poll_interval_ms)
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
    
    def get_state(self, pin_num) -> bool:
        """Get the current debounced state of a pin."""
        if pin_num not in self.pins:
            raise Exception("Pin number not registered")

        return self.pins[pin_num]['last_state']
        
    
    def get_all_states(self):
        """Get a dictionary of all pin states."""
        return {pin_num: data['last_state'] for pin_num, data in self.pins.items()}