from machine import Timer
from defs import *

class OneShotTimer:
    def __init__(self, timer_id: int=1, tick_ms: int=100) -> None:
        """
        Initialize the timer wrapper with a hardware timer.
        
        Args:
            timer_id: Hardware timer ID (0, 1, 2, 3 depending on platform)
                      ESP32: 0-3
                      ESP8266: 0 (only one available, must use timer_id=-1)
                      RP2040: 0-3
                      STM32: varies by board
            tick_ms: Internal tick period in milliseconds (default 100ms)
        """
        self.timer = Timer(timer_id)
        self.tick_ms = tick_ms
        self._active = False
        self._callback = None
        self._tick_count = 0
        self._target_ticks = 0
    
    def start(self, delay_ms: int, callback: Callable[[Timer], None]) -> None:
        """
        Start a one-shot timer.
        
        Args:
            delay_ms: Delay in milliseconds before callback is executed
            callback: Function to call when timer expires (receives timer object as arg)
        """
        # Cancel any existing timer first
        self.cancel()
        
        # Calculate how many ticks we need
        self._target_ticks = delay_ms // self.tick_ms
        if delay_ms % self.tick_ms != 0:
            self._target_ticks += 1  # Round up
        
        # Store the user's callback
        self._callback = callback
        self._tick_count = 0
        
        # Start the timer in periodic mode with fixed tick period
        self.timer.init(
            mode=Timer.PERIODIC,
            period=self.tick_ms,
            callback=self._internal_callback
        )
        self._active = True
    
    def _internal_callback(self, t):
        """Internal callback that counts ticks and implements one-shot behavior."""
        self._tick_count += 1
        
        # Check if we've reached the target
        if self._tick_count >= self._target_ticks:
            # Stop the timer first
            self.timer.deinit()
            self._active = False
            
            # Call the user's callback
            if self._callback:
                user_callback = self._callback
                self._callback = None
                self._tick_count = 0
                self._target_ticks = 0
                user_callback(t)
    
    def cancel(self) -> None:
        """Cancel the timer if it's running."""
        if self._active:
            self.timer.deinit()
            self._active = False
            self._callback = None
            self._tick_count = 0
            self._target_ticks = 0
    
    def is_active(self) -> bool:
        """Check if timer is currently active."""
        return self._active
    
    def get_remaining_ms(self) -> int:
        """Get approximate remaining time in milliseconds."""
        if not self._active:
            return 0
        remaining_ticks = self._target_ticks - self._tick_count
        return remaining_ticks * self.tick_ms
    
    def __del__(self):
        """Cleanup when object is destroyed."""
        self.cancel()