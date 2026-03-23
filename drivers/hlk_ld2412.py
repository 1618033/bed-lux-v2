from __future__ import annotations

import time
import logging

from defs import Optional
from machine import UART


log = logging.getLogger("[HLKLD2412]")
log.setLevel(logging.DEBUG)

class HLKLD2412:
    CMD_HEADER = b"\xFD\xFC\xFB\xFA"
    CMD_TAIL = b"\x04\x03\x02\x01"
    DATA_HEADER = b"\xF4\xF3\xF2\xF1"
    DATA_TAIL = b"\xF8\xF7\xF6\xF5"

    DATA_TYPE_ENGINEERING = 0x01
    DATA_TYPE_BASIC = 0x02

    TARGET_NONE = 0x00
    TARGET_MOVING = 0x01
    TARGET_STATIONARY = 0x02
    TARGET_BOTH = 0x03

    ACK_OK = 0x0000
    ACK_ERROR = 0x0001

    BAUD_9600 = 0x0001
    BAUD_19200 = 0x0002
    BAUD_38400 = 0x0003
    BAUD_57600 = 0x0004
    BAUD_115200 = 0x0005
    BAUD_230400 = 0x0006
    BAUD_256000 = 0x0007
    BAUD_460800 = 0x0008

    RESOLUTION_0_75_M = 0x00
    RESOLUTION_0_5_M = 0x01
    RESOLUTION_0_2_M = 0x03

    LIGHT_FUNCTION_OFF = 0x00
    LIGHT_FUNCTION_BELOW = 0x01
    LIGHT_FUNCTION_ABOVE = 0x02

    OUT_PIN_LEVEL_HIGH_WHEN_OCCUPIED = 0x00
    OUT_PIN_LEVEL_LOW_WHEN_OCCUPIED = 0x01

    GATE_COUNT = 14
    NO_MAC = b"\x08\x05\x04\x03\x02\x01"

    def __init__(self, uart: UART, timeout_ms: int = 500) -> None:
        self._uart = uart
        self._timeout_ms = timeout_ms
        self._buffer = bytearray()

    def flush(self) -> None:
        while True:
            waiting = self._uart.any()
            if not waiting:
                self._buffer = bytearray()
                return
            self._uart.read(waiting)
            time.sleep_ms(10)

    def read_report(self, timeout_ms: Optional[int] = None):
        payload = self._wait_for_frame(self.DATA_HEADER, self.DATA_TAIL, timeout_ms)
        if payload is None:
            return None
        return self._parse_report(payload)

    def enable_configuration(self) -> bool:
        ack = self._send_command(0x00FF, b"\x01\x00")
        return ack["status"] == self.ACK_OK

    def end_configuration(self) -> bool:
        ack = self._send_command(0x00FE)
        return ack["status"] == self.ACK_OK

    def set_resolution(self, resolution_value: int) -> bool:
        value = bytes((resolution_value, 0x00, 0x00, 0x00, 0x00, 0x00))
        ack = self._send_config_command(0x0001, value)
        return ack["status"] == self.ACK_OK

    def read_resolution(self):
        ack = self._send_config_command(0x0011)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 8:
            return None
        value = ack["value"][2]
        return {
            "value": value,
            "label": self._resolution_label(value),
        }

    def set_basic_parameters(
        self,
        min_gate: int,
        max_gate: int,
        unmanned_duration_s: int,
        out_pin_polarity: int = 0,
    ) -> bool:
        value = bytes((min_gate, max_gate)) + int(unmanned_duration_s).to_bytes(2, "little") + bytes((out_pin_polarity,))
        ack = self._send_config_command(0x0002, value)
        return ack["status"] == self.ACK_OK

    def read_basic_parameters(self):
        ack = self._send_config_command(0x0012)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 7:
            return None
        raw = ack["value"]
        return {
            "min_gate": raw[2],
            "max_gate": raw[3],
            "unmanned_duration_s": int.from_bytes(raw[4:6], "little"),
            "out_pin_polarity": raw[6],
            "out_pin_level": self._out_pin_level_label(raw[6]),
        }

    def enable_engineering_mode(self) -> bool:
        ack = self._send_config_command(0x0062)
        return ack["status"] == self.ACK_OK

    def disable_engineering_mode(self) -> bool:
        ack = self._send_config_command(0x0063)
        return ack["status"] == self.ACK_OK

    def set_motion_sensitivity(self, values) -> bool:
        value = self._normalize_gate_values(values)
        ack = self._send_config_command(0x0003, value)
        return ack["status"] == self.ACK_OK

    def read_motion_sensitivity(self):
        ack = self._send_config_command(0x0013)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 16:
            return None
        return list(ack["value"][2:16])

    def set_stationary_sensitivity(self, values) -> bool:
        value = self._normalize_gate_values(values)
        ack = self._send_config_command(0x0004, value)
        return ack["status"] == self.ACK_OK

    def read_stationary_sensitivity(self):
        ack = self._send_config_command(0x0014)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 16:
            return None
        return list(ack["value"][2:16])

    def enter_dynamic_background_correction(self) -> bool:
        ack = self._send_config_command(0x000B)
        return ack["status"] == self.ACK_OK

    def read_dynamic_background_correction_status(self):
        ack = self._send_config_command(0x001B)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 4:
            return None
        return int.from_bytes(ack["value"][2:4], "little")

    def read_firmware_version(self):
        ack = self._send_config_command(0x00A0)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 10:
            return None
        raw = ack["value"]
        version_bytes = bytes(raw[4:10])
        return {
            "firmware_type": int.from_bytes(raw[2:4], "little"),
            "version_bytes": version_bytes,
            "version_text": self._format_version(version_bytes),
        }

    def set_baudrate(self, baudrate_index: int) -> bool:
        ack = self._send_config_command(0x00A1, int(baudrate_index).to_bytes(2, "little"))
        return ack["status"] == self.ACK_OK

    def restore_factory_settings(self) -> bool:
        ack = self._send_config_command(0x00A2)
        return ack["status"] == self.ACK_OK

    def restart(self) -> bool:
        ack = self._send_config_command(0x00A3)
        return ack["status"] == self.ACK_OK

    def set_bluetooth(self, enabled: bool) -> bool:
        value = b"\x01\x00" if enabled else b"\x00\x00"
        ack = self._send_config_command(0x00A4, value)
        return ack["status"] == self.ACK_OK

    def get_mac_address(self):
        ack = self._send_config_command(0x00A5, b"\x01\x00")
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 8:
            return None
        mac = ack["value"][2:8]
        return ":".join("%02X" % b for b in mac)

    def set_light_control(self, mode: int, threshold: int = 0) -> bool:
        value = bytes((mode & 0xFF, threshold & 0xFF))
        ack = self._send_config_command(0x000C, value)
        return ack["status"] == self.ACK_OK

    def read_light_control(self):
        ack = self._send_config_command(0x001C)
        if ack["status"] != self.ACK_OK or len(ack["value"]) < 4:
            return None
        return {
            "mode": ack["value"][2],
            "mode_label": self._light_function_label(ack["value"][2]),
            "threshold": ack["value"][3],
        }

    def read_all_info(self):
        if not self.enable_configuration():
            raise OSError("unable to enter configuration mode")

        try:
            firmware = self._send_command(0x00A0)
            mac_ack = self._send_command(0x00A5, b"\x01\x00")
            resolution = self._send_command(0x0011)
            basic = self._send_command(0x0012)
            dynamic_background = self._send_command(0x001B)
            light_control = self._send_command(0x001C)
            motion = self._send_command(0x0013)
            stationary = self._send_command(0x0014)
        finally:
            self.end_configuration()

        info = {}

        if firmware["status"] == self.ACK_OK and len(firmware["value"]) >= 10:
            version_bytes = bytes(firmware["value"][4:10])
            info["firmware"] = {
                "firmware_type": int.from_bytes(firmware["value"][2:4], "little"),
                "version_bytes": version_bytes,
                "version_text": self._format_version(version_bytes),
            }

        if mac_ack["status"] == self.ACK_OK and len(mac_ack["value"]) >= 8:
            mac = bytes(mac_ack["value"][2:8])
            info["mac_address"] = ":".join("%02X" % b for b in mac)
            info["bluetooth_enabled"] = mac != self.NO_MAC

        if resolution["status"] == self.ACK_OK and len(resolution["value"]) >= 8:
            value = resolution["value"][2]
            info["resolution"] = {
                "value": value,
                "label": self._resolution_label(value),
            }

        if basic["status"] == self.ACK_OK and len(basic["value"]) >= 7:
            raw = basic["value"]
            info["basic_parameters"] = {
                "min_gate": raw[2],
                "max_gate": raw[3],
                "unmanned_duration_s": int.from_bytes(raw[4:6], "little"),
                "out_pin_polarity": raw[6],
                "out_pin_level": self._out_pin_level_label(raw[6]),
            }

        if dynamic_background["status"] == self.ACK_OK and len(dynamic_background["value"]) >= 4:
            info["dynamic_background_correction_status"] = int.from_bytes(dynamic_background["value"][2:4], "little")

        if light_control["status"] == self.ACK_OK and len(light_control["value"]) >= 4:
            info["light_control"] = {
                "mode": light_control["value"][2],
                "mode_label": self._light_function_label(light_control["value"][2]),
                "threshold": light_control["value"][3],
            }

        if motion["status"] == self.ACK_OK and len(motion["value"]) >= 16:
            info["motion_sensitivity"] = list(motion["value"][2:16])

        if stationary["status"] == self.ACK_OK and len(stationary["value"]) >= 16:
            info["stationary_sensitivity"] = list(stationary["value"][2:16])

        return info

    def _normalize_gate_values(self, values) -> bytes:
        if len(values) != self.GATE_COUNT:
            raise ValueError("expected %d gate values" % self.GATE_COUNT)
        return bytes(int(v) & 0xFF for v in values)

    def _send_config_command(self, command_word: int, value: bytes = b"", timeout_ms: Optional[int] = None):
        if not self.enable_configuration():
            raise OSError("unable to enter configuration mode")
        try:
            return self._send_command(command_word, value, timeout_ms)
        finally:
            self.end_configuration()

    def _send_command(self, command_word: int, value: bytes = b"", timeout_ms: Optional[int] = None):
        payload = int(command_word).to_bytes(2, "little") + value
        frame = self.CMD_HEADER + len(payload).to_bytes(2, "little") + payload + self.CMD_TAIL
        self._uart.write(frame)

        while True:
            ack_payload = self._wait_for_frame(self.CMD_HEADER, self.CMD_TAIL, timeout_ms)
            if ack_payload is None:
                raise OSError("timeout waiting for ACK")

            ack_command = int.from_bytes(ack_payload[:2], "little")
            if ack_command != (command_word | 0x0100):
                continue

            value = ack_payload[2:]
            status = int.from_bytes(value[:2], "little") if len(value) >= 2 else None
            return {
                "command": ack_command,
                "status": status,
                "value": value,
            }

    def _wait_for_frame(self, header: bytes, tail: bytes, timeout_ms: Optional[int] = None):
        timeout = self._timeout_ms if timeout_ms is None else timeout_ms
        start = time.ticks_ms()

        while True:
            frame = self._extract_frame(header, tail)
            if frame is not None:
                return frame

            waiting = self._uart.any()
            if waiting:
                data = self._uart.read(waiting)
                if data:
                    self._buffer.extend(data)
                    continue

            if timeout is not None and time.ticks_diff(time.ticks_ms(), start) >= timeout:
                return None

            time.sleep_ms(10)

    def _extract_frame(self, header: bytes, tail: bytes):
        header_index = self._buffer.find(header)
        if header_index < 0:
            if len(self._buffer) > len(header):
                self._buffer = self._buffer[-len(header):]
            return None

        if header_index > 0:
            self._buffer = self._buffer[header_index:]

        if len(self._buffer) < 6:
            return None

        payload_len = int.from_bytes(self._buffer[4:6], "little")
        frame_len = 4 + 2 + payload_len + 4
        if len(self._buffer) < frame_len:
            return None

        frame = bytes(self._buffer[:frame_len])
        if frame[-4:] != tail:
            self._buffer = self._buffer[1:]
            return None

        self._buffer = self._buffer[frame_len:]
        return frame[6:-4]

    def _parse_report(self, payload: bytes):
        if len(payload) < 4:
            log.error("report payload too short")
            return None

        data_type = payload[0]
        if payload[1] != 0xAA or payload[-2] != 0x55: # or payload[-1] != 0x00: # <- might not be needed
            log.error("invalid report payload markers")
            log.error(payload)
            return None

        target_data = payload[2:-2]
        if len(target_data) < 7:
            log.error("target payload too short")
            return None

        report = {
            "data_type": data_type,
            "target_state": target_data[0],
            "moving_distance_cm": int.from_bytes(target_data[1:3], "little"),
            "moving_energy": target_data[3],
            "stationary_distance_cm": int.from_bytes(target_data[4:6], "little"),
            "stationary_energy": target_data[6],
            "has_target": target_data[0] != self.TARGET_NONE,
            "has_moving_target": bool(target_data[0] & self.TARGET_MOVING),
            "has_stationary_target": bool(target_data[0] & self.TARGET_STATIONARY),
        }

        if report["has_moving_target"]:
            report["detection_distance_cm"] = report["moving_distance_cm"]
        elif report["has_stationary_target"]:
            report["detection_distance_cm"] = report["stationary_distance_cm"]
        else:
            report["detection_distance_cm"] = 0

        if data_type == self.DATA_TYPE_ENGINEERING:
            if len(target_data) < 37:
                raise ValueError("engineering payload too short")
            report["max_moving_gate"] = target_data[7]
            report["max_stationary_gate"] = target_data[8]
            report["moving_gate_energies"] = list(target_data[9:23])
            report["stationary_gate_energies"] = list(target_data[23:37])
            if len(target_data) >= 38:
                report["light"] = target_data[37]

        return report

    def _format_version(self, version_bytes: bytes) -> str:
        if len(version_bytes) != 6:
            return ""
        return "V%d.%02d.%02d%02d%02d%02d" % (
            version_bytes[1],
            version_bytes[0],
            version_bytes[5],
            version_bytes[4],
            version_bytes[3],
            version_bytes[2],
        )

    def _resolution_label(self, value: int) -> str:
        if value == self.RESOLUTION_0_2_M:
            return "0.2m"
        if value == self.RESOLUTION_0_5_M:
            return "0.5m"
        if value == self.RESOLUTION_0_75_M:
            return "0.75m"
        return "unknown"

    def _light_function_label(self, value: int) -> str:
        if value == self.LIGHT_FUNCTION_OFF:
            return "off"
        if value == self.LIGHT_FUNCTION_BELOW:
            return "below"
        if value == self.LIGHT_FUNCTION_ABOVE:
            return "above"
        return "unknown"

    def _out_pin_level_label(self, value: int) -> str:
        if value == self.OUT_PIN_LEVEL_HIGH_WHEN_OCCUPIED:
            return "high"
        if value == self.OUT_PIN_LEVEL_LOW_WHEN_OCCUPIED:
            return "low"
        return "unknown"
