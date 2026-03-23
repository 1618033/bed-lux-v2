import asyncio
import network
import logging
import gc

from defs import *

log = logging.getLogger("[APC]")

class APController:
    def __init__(
        self,
        ssid: str,
        password: str,
        authmode: int = network.AUTH_WPA_WPA2_PSK,
        channel: int = 1,
        max_clients: int = 4,
        ifconfig: Optional[Tuple[str, str, str, str]] = None,  # e.g. ("192.168.4.1","255.255.255.0","192.168.4.1","8.8.8.8")
        poll_interval: float = 5.0,  # seconds between station scans
    ) -> None:
        self.ssid: str = ssid
        self.password: str = password
        self.authmode: int = authmode
        self.channel: int = channel
        self.max_clients: int = max_clients
        self.ifconfig: Optional[Tuple[str, str, str, str]] = ifconfig
        self.poll_interval: float = poll_interval

        self.ap: network.WLAN = network.WLAN(network.AP_IF)
        self._clients: set[Tuple[bytes, int]] = set()
        self._task: Optional[asyncio.Task[Any]] = None
        self._active: bool = False


    async def on_start(self, ip: str) -> None:
        """Default callback for when AP starts."""
        pass

    async def on_stop(self) -> None:
        """Default callback for when AP stops."""
        pass

    async def on_client_connect(self, mac: str) -> None:
        """Default callback for when a client connects."""
        pass

    async def on_client_disconnect(self, mac: str) -> None:
        """Default callback for when a client disconnects."""
        pass

    def client_count(self) -> int:
        return len(self._clients)

    def active(self) -> bool:
        return self._active
    
    async def start(self) -> None:
        """Activate AP and begin monitoring clients."""
        log.info("Starting...")
        
        # Free memory before WiFi activation
        gc.collect()
        self.ap.active(True)

        self.ap.config(
            ssid=self.ssid,
            key=self.password,
            authmode=self.authmode,
            channel=self.channel,
            max_clients=self.max_clients,
        )
        
        log.info("Active: %s" % self.ap.active())

        # prime the client set so we only report new joins
        raw = self.ap.status("stations") or []
        
        self._clients = set(raw)  # pyright: ignore[reportAssignmentType, reportArgumentType, reportAttributeAccessIssue]
        self._active = True
        self._task = asyncio.create_task(self._monitor_clients())
        
        ip = self.ap.ifconfig()[0]
        log.info("Started: %s @ %s" % (self.ssid, ip))
        asyncio.create_task(self.on_start(ip))

    async def _monitor_clients(self) -> None:
        """Poll every poll_interval seconds for station changes."""
        while self._active:
            # Get list of tuples: (mac_bytes, rssi)
            raw_stations: List[Tuple[bytes, int]] = self.ap.status("stations")  # pyright: ignore[reportAssignmentType]
            
            stations: set[Tuple[bytes, int]] = set(raw_stations) if raw_stations else set()
            
            joined: set[Tuple[bytes, int]] = stations - self._clients
            left: set[Tuple[bytes, int]] = self._clients - stations
            self._clients = stations
            
            for mac in joined:
                mac_bytes: bytes = mac[0]
                # mac_str needs to format mac_bytes as colon-separated hex; can't use f-string,
                # so have to use a generator with % formatting.
                mac_str: str = ':'.join('0x%02X' % b for b in mac_bytes)
                log.debug("Client joined: %s" % mac_str)
                asyncio.create_task(self.on_client_connect(mac_str))

            for mac in left:
                mac_bytes: bytes = mac[0]
                mac_str: str = ':'.join('0x%02X' % b for b in mac_bytes)
                log.debug("Client disconnected: %s" % mac_str)
                asyncio.create_task(self.on_client_disconnect(mac_str))

            await asyncio.sleep(self.poll_interval)

    async def stop(self) -> None:
        """Stop monitoring and deactivate AP."""
        log.info("Stopping...")
        self._active = False
        if self._task:
            self._task.cancel()
            # give it a moment to clean up
            await asyncio.sleep_ms(50)

        try:
            asyncio.create_task(self.on_stop())
        except Exception as e:
            log.error("Error in on_stop callback: %s" % e)
        
        try:
            self.ap.active(False)
            await asyncio.sleep_ms(100)  # Give WiFi time to deinitialize
            gc.collect()
        except Exception as e:
            log.error("Error deactivating WiFi AP: %s" % e)
        
        log.info("Stopped")