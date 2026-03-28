import asyncio
import aioble
import aioble.peripheral as aioble_peripheral
import bluetooth
import logging
import gc

from defs import BLE_SERVICE_UUID, BLE_CMD_UUID, BLE_GETCFG_UUID, BLE_NOTIFICATION_UUID
from defs import BLEC_NOTIFICATION_SENSORS, BLEC_NOTIFICATION_TEXT
from defs import BLEC_CHARACTERISTIC_GETCFG, BLEC_CHARACTERISTIC_NOTIFICATION
from defs import ADV_INTERVAL_MS
from defs import Optional, Any, Union, List

_BLE_SERVICE_UUID = bluetooth.UUID(BLE_SERVICE_UUID)
_BLE_CMD_UUID = bluetooth.UUID(BLE_CMD_UUID)
_BLE_GETCFG_UUID = bluetooth.UUID(BLE_GETCFG_UUID)
_BLE_NOTIFICATION_UUID = bluetooth.UUID(BLE_NOTIFICATION_UUID)

_CMD_WRITE_BUFFER_SIZE = 128
_BLE_PREFERRED_MTU = _CMD_WRITE_BUFFER_SIZE + 3
_BLE_RXBUF_SIZE = 512

log: logging.Logger = logging.getLogger("[BLEC]")
log.setLevel(logging.DEBUG)
logcmd: logging.Logger = logging.getLogger("[BLEC][CMD]")
logcmd.setLevel(logging.DEBUG)


class BLEController:
    def __init__(self, name: str) -> None:
        self.name: str = name
        self.ble_service: aioble.Service = aioble.Service(_BLE_SERVICE_UUID)
        self.cmd_characteristic: Optional[aioble.Characteristic] = None
        self.getcfg_characteristic: Optional[aioble.Characteristic] = None
        self.notification_characteristic: Optional[aioble.Characteristic] = None
        self.terminate: bool = False
        self._active: bool = False
        self._connected: bool = False
        self.ble_enable_task: Optional[asyncio.Task[Any]] = None
        self.wait_for_cmd_characteristic_task: Optional[asyncio.Task[Any]] = None
        self.tasks: List[asyncio.Task[Any]] = []
        self.initialized: bool = False
        self.last_exception: Optional[Exception]
        self.failed_task_name: str
    
    async def cmd_callback(self, cmd: int, payload: bytes) -> None:
        return
    
    async def on_start(self) -> None:
        return
    
    async def on_stop(self) -> None:
        return
    
    async def on_connect(self) -> None:
        return
    
    async def on_disconnect(self) -> None:
        return
    
    def on_error(self, error: str, exception: Optional[Exception]=None) -> None:
        return

    def active(self) -> bool:
        return self._active
    
    def connected(self) -> bool:
        return self._connected

    def _create_task(self, coro, name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(self._watch_task(coro, name))
        self.tasks.append(task)
        return task

    def _configure_cmd_write_buffer(self) -> None:
        if self.cmd_characteristic is None:
            return

        ble = bluetooth.BLE()

        try:
            ble.config(mtu=_BLE_PREFERRED_MTU, rxbuf=_BLE_RXBUF_SIZE)
        except Exception as e:
            log.warning("Unable to configure preferred BLE MTU/rxbuf: %s", e)

        value_handle = getattr(self.cmd_characteristic, "_value_handle", None)
        if value_handle is None:
            log.warning("Command characteristic value handle unavailable; using default write buffer")
            return

        try:
            ble.gatts_set_buffer(value_handle, _CMD_WRITE_BUFFER_SIZE)
            log.info("Command characteristic write buffer set to %d bytes", _CMD_WRITE_BUFFER_SIZE)
        except Exception as e:
            log.warning("Unable to configure command write buffer: %s", e)
    
    async def ble_enable(self) -> None:

        while not self.terminate:
            try:                
                async with await aioble.advertise(  # type: ignore
                    ADV_INTERVAL_MS,
                    name=self.name,
                    services=[_BLE_SERVICE_UUID],
                    ) as connection:
                        log.info("Connection from: %s" % connection.device)
                        self._connected = True
                        self._create_task(self.on_connect(), "on_connect")
                        await connection.disconnected()
                        self._connected = False
                        self._create_task(self.on_disconnect(), "on_disconnect")
            except asyncio.CancelledError:
                self.on_error("Bluetooth enabling cancelled")
                log.exception("Bluetooth enabling cancelled")
            except Exception as e:
                self.on_error("Error in ble_enable", e)
                log.exception("Error in ble_enable")
                raise
            finally:
                self._connected = False
                if aioble_peripheral._connect_event is not None:
                    aioble_peripheral._connect_event.clear()
                
                await asyncio.sleep_ms(100)


    def set_characteristic_value(self, characteristic: int, value: Union[bytes, str], send_update: bool = False) -> None:
        if not self._active:
            log.debug("Bluetooth service not active")
            return

        # TODO: config

        if characteristic == BLEC_CHARACTERISTIC_GETCFG:
            char = self.getcfg_characteristic
        elif characteristic == BLEC_CHARACTERISTIC_NOTIFICATION:
            char = self.notification_characteristic
        else:
            self.on_error("Unknown characteristic: [0x%02X]" % characteristic)
            log.error("Unknown characteristic: [0x%02X]" % characteristic)
            return

        if char is None:
            log.debug("Characteristic not initialized: [0x%02X]" % characteristic)
            return
        
        try:
            if isinstance(value, str):
                value = value.encode("utf-8")
            log.debug("Setting characteristic value. [0x%02X] -> %s" % (characteristic, value))
            char.write(value, send_update=send_update)
        except Exception as e:
            self.on_error("Unable to write to BLE characteristic [0x%02x]: %s" % (characteristic, e))
            log.exception("Unable to write to BLE characteristic [0x%02x]: %s" % (characteristic, e))

        
    
    async def wait_for_cmd_characteristic(self) -> None:
        while not self.terminate:
            try:
                if self.cmd_characteristic is None:
                    await asyncio.sleep_ms(100)
                    continue
                connection, data = await self.cmd_characteristic.written()  # type: ignore
                
                cmd = data[0]
                payload = data[1:]
                
                logcmd.debug("Command received: 0x%02X" % cmd)
                logcmd.debug(payload)
                
                await self.cmd_callback(cmd, payload)
                    
            except asyncio.CancelledError:
                self.on_error("wait_for_cmd_characteristic task cancelled")
                logcmd.exception("wait_for_cmd_characteristic task cancelled")
            except Exception as e:
                self.on_error("Error in wait_for_cmd_characteristic")
                logcmd.exception("Error in wait_for_cmd_characteristic")
                raise
            finally:
                await asyncio.sleep_ms(100)
    
    def notify(self, notification_type: int, value: bytes) -> None:
        if not self.connected():
            return

        if notification_type not in [BLEC_NOTIFICATION_SENSORS, BLEC_NOTIFICATION_TEXT]:
            self.on_error("Unknown notification_type: [0x%02X]" % notification_type)
            log.error("Unknown notification_type: [0x%02X]" % notification_type)
            return
        
        log.debug("Sending notification [0x%02X]" % notification_type)
        self.set_characteristic_value(BLEC_CHARACTERISTIC_NOTIFICATION, chr(notification_type).encode() + value, send_update=True)
                
    def stop(self, internal: bool = False) -> None:
        if not self._active:
            log.info("Already stopped")
            return
        log.info("Stopping...")
        
        self.terminate = True
        if self.ble_enable_task is not None:
            self.ble_enable_task.cancel()
        if not internal and self.wait_for_cmd_characteristic_task is not None:
            self.wait_for_cmd_characteristic_task.cancel()
        
        aioble.stop()
        self._active = False
        
        log.info("Stopped")
        
        self._create_task(self.on_stop(), "on_stop")
    

    async def _watch_task(self, coro, name):
        try:
            return await coro
        except asyncio.CancelledError:
            log.warning("%s cancelled", name)
            raise
        except Exception as e:
            log.debug("Task monitor: %s failed", name)
            self.on_error("%s failed" % name, e)
            self.last_exception = e
            self.failed_task_name = name

            for t in (
                self.ble_enable_task,
                self.wait_for_cmd_characteristic_task,
            ):
                if t is not None and t is not asyncio.current_task():
                    try:
                        t.cancel()
                    except Exception:
                        pass
            return None

    async def start(self) -> None:
        if self._active:
            log.info("BLE activation requested. Already active.")
            return
        log.info("Starting...")

#        await asyncio.sleep(1)
        gc.collect()
        #aioble.core.ensure_active() 

        self.terminate = False
        self._active = False
        self._connected = False
        self.tasks = []
        self.last_exception = None
    
        self.ble_service = aioble.Service(_BLE_SERVICE_UUID)
        self.cmd_characteristic = aioble.Characteristic(self.ble_service, _BLE_CMD_UUID, write=True, capture=True)
        self.getcfg_characteristic = aioble.Characteristic(self.ble_service, _BLE_GETCFG_UUID, read=True)
        self.notification_characteristic = aioble.Characteristic(self.ble_service, _BLE_NOTIFICATION_UUID, notify=True, read=True)
        
        aioble.register_services(self.ble_service)
        self._configure_cmd_write_buffer()

        try:
            self.ble_enable_task = self._create_task(self.ble_enable(), "ble_enable")
            self.wait_for_cmd_characteristic_task = self._create_task(self.wait_for_cmd_characteristic(), "wait_for_cmd_characteristic")

            self.initialized = True
            self._active = True
            log.info("Started")

            self._create_task(self.on_start(), "on_start")

            while True:
                await asyncio.sleep(1)
                if self.last_exception is not None:
                    raise self.last_exception

        except Exception:
            raise
