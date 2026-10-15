"""Headless tester library, persistent command shell and loopback HTTP API."""

from __future__ import annotations

import argparse
import inspect
import json
import math
import re
import shlex
import sys
import threading
import time
import uuid
from collections import deque
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


class TesterError(Exception):
    def __init__(self, code: str, message: str, outcome: str = "failed"):
        super().__init__(message)
        self.code = code
        self.outcome = outcome

    def to_dict(self) -> dict:
        return {"code": self.code, "message": str(self), "outcome": self.outcome}


def integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TesterError("validation", f"{name} must be an integer.")
    if not minimum <= value <= maximum or value != int(value):
        raise TesterError("validation", f"{name} must be {minimum}..{maximum}.")
    return int(value)


def number(value, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TesterError("validation", f"{name} must be a finite number.")
    try:
        result = float(value)
    except (ValueError, OverflowError):
        raise TesterError("validation", f"{name} must be a finite number.") from None
    if not math.isfinite(result):
        raise TesterError("validation", f"{name} must be a finite number.")
    return result


def channel_id(channel) -> int:
    return integer(channel, "channel", 1, 4)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ScalingConfig:
    x1: float = 0
    x2: float = 15000
    y1: float = 0
    y2: float = 100

    def __post_init__(self):
        for name in ("x1", "x2", "y1", "y2"):
            number(getattr(self, name), name)
        if self.y1 == self.y2:
            raise TesterError("validation", "Y1 and Y2 must differ.")

    def to_mv(self, value) -> dict:
        desired = number(value, "value")
        mv = self.x1 + (desired - self.y1) * (self.x2 - self.x1) / (self.y2 - self.y1)
        if not math.isfinite(mv) or not 0 <= mv <= 15000:
            raise TesterError("validation", "Calculated voltage must be 0..15000 mV.")
        outside = not min(self.y1, self.y2) <= desired <= max(self.y1, self.y2)
        return {"mv": round(mv), "warning": "Outside engineering range" if outside else None}

    def from_mv(self, mv) -> float:
        value = number(mv, "mv")
        if self.x1 == self.x2:
            raise TesterError("validation", "X1 and X2 must differ for inverse scaling.")
        result = self.y1 + (value - self.x1) * (self.y2 - self.y1) / (self.x2 - self.x1)
        return number(result, "engineering value")


@dataclass
class ChannelConfig:
    mv: int
    scaling: ScalingConfig
    scaling_mode: str = "manual"
    value: float = 0

    def resolved(self) -> dict:
        if self.scaling_mode == "automatic":
            return self.scaling.to_mv(self.value)
        return {"mv": self.mv, "warning": None}


def prepare_channel_commands(commands, configs):
    if not isinstance(commands, list) or not 1 <= len(commands) <= 32:
        raise TesterError("validation", "Commands must be an array of 1..32 command objects.")
    fields = {"Port", "PortNum", "Action", "X1", "Y1", "X2", "Y2", "Output_Value",
              "Operation_Mode", "Manual_voltage", "Cycle_ms", "Duration_ms", "Auto_Enabled"}
    configuration_fields = {"X1", "Y1", "X2", "Y2", "Output_Value", "Operation_Mode", "Manual_voltage"}
    working = deepcopy(configs)
    prepared = []
    for index, command in enumerate(commands):
        try:
            if not isinstance(command, dict) or set(command) - fields:
                raise TesterError("validation", "Command contains unknown fields or is not an object.")
            port = command.get("Port")
            action = command.get("Action")
            if not isinstance(port, str) or not isinstance(action, str):
                raise TesterError("validation", "Port and Action must be strings.")
            port, action = port.upper(), action.lower()
            channel = channel_id(command.get("PortNum"))
            if port not in ("VAI", "WM", "AI"):
                raise TesterError("validation", "Port must be VAI, WM or AI.")
            actions = {"VAI": {"configure", "on", "off", "pulse", "stop"},
                       "WM": {"on", "off", "start", "stop"}, "AI": {"read"}}
            if port == "WM" and action == "trigger":
                raise TesterError("unsupported", "Valve-based WM triggering is unavailable in this firmware.")
            if action not in actions[port]:
                raise TesterError("validation", f"Action {action} is not supported for Port {port}.")
            allowed = set()
            if port == "VAI" and action == "configure":
                allowed = configuration_fields | {"Auto_Enabled", "Duration_ms"}
            elif port == "VAI" and action == "pulse":
                allowed = {"Manual_voltage", "Duration_ms"}
            elif port == "WM" and action == "start":
                allowed = {"Cycle_ms"}
            irrelevant = {name for name in command if name not in allowed | {"Port", "PortNum", "Action"}
                          and command[name] is not None}
            if irrelevant:
                raise TesterError("validation", f"Fields must be null for this action: {', '.join(sorted(irrelevant))}.")
            item = {"Port": port, "PortNum": channel, "Action": action.capitalize()}
            if port == "VAI" and action == "configure":
                auto_enabled = command.get("Auto_Enabled")
                if auto_enabled is not None and not isinstance(auto_enabled, bool):
                    raise TesterError("validation", "Auto_Enabled must be true, false or null.")
                duration = command.get("Duration_ms")
                if duration is not None:
                    if auto_enabled is not True:
                        raise TesterError("validation", "Configure Duration_ms requires Auto_Enabled=true.")
                    duration = integer(duration, "Duration_ms", 10, 3600000)
                item["auto_enabled"] = auto_enabled
                item["auto_duration_ms"] = duration
                config = deepcopy(working[channel])
                points = asdict(config.scaling)
                for name in ("X1", "X2", "Y1", "Y2"):
                    if command.get(name) is not None:
                        points[name.lower()] = number(command[name], name)
                config.scaling = ScalingConfig(**points)
                mode = command.get("Operation_Mode")
                if mode is not None:
                    if not isinstance(mode, str) or mode.lower() not in ("manual", "automatic", "auto"):
                        raise TesterError("validation", "Operation_Mode must be Manual or Automatic.")
                    config.scaling_mode = "manual" if mode.lower() == "manual" else "automatic"
                if command.get("Manual_voltage") is not None:
                    if config.scaling_mode != "manual":
                        raise TesterError("validation", "Manual_voltage requires Manual mode during Configure.")
                    config.mv = integer(command["Manual_voltage"], "Manual_voltage", 0, 15000)
                if command.get("Output_Value") is not None:
                    if config.scaling_mode != "automatic":
                        raise TesterError("validation", "Output_Value requires Automatic mode.")
                    config.value = number(command["Output_Value"], "Output_Value")
                if config.scaling_mode == "manual":
                    config.scaling.from_mv(config.mv)
                config.resolved()
                working[channel] = config
                item["config"] = deepcopy(config)
            elif port == "VAI" and action in ("on", "pulse"):
                if action == "pulse":
                    item["duration_ms"] = integer(command.get("Duration_ms"), "Duration_ms", 10, 3600000)
                    item["mv"] = (integer(command["Manual_voltage"], "Manual_voltage", 0, 15000)
                                  if command.get("Manual_voltage") is not None else working[channel].resolved()["mv"])
                else:
                    working[channel].resolved()
            elif port == "WM" and action == "start":
                period = command.get("Cycle_ms")
                item["cycle_ms"] = integer(1000 if period is None else period, "Cycle_ms", 20, 3600000)
            prepared.append(item)
        except TesterError as error:
            raise TesterError(error.code, f"Commands[{index}]: {error}", error.outcome) from None
        except (OverflowError, ValueError):
            raise TesterError("validation", f"Commands[{index}]: Invalid or overflowing numeric configuration.") from None
    return prepared


def parse_wm_status(line: str) -> dict:
    if not line.startswith("wm status"):
        raise TesterError("protocol", "Not a WM status response.")
    pattern = r" wm ([1-4]) (running \(triggered\)|manual on|started|stopped|triggered) (\d+)ms"
    matches = list(re.finditer(pattern, line[len("wm status"):]))
    if (len(matches) != 4 or {match[1] for match in matches} != {"1", "2", "3", "4"}
            or "".join(match[0] for match in matches) != line[len("wm status"):]):
        raise TesterError("protocol", "Incomplete or malformed WM status.")
    return {int(match[1]): {"state": match[2], "cycle_ms": int(match[3])} for match in matches}


def parse_supply_status(line: str) -> dict:
    match = re.fullmatch(
        r"vsen en=([01]) mv=(\d+) ccr4=(\d+) duty=(\d+\.\d+)% pwm=(run|stopped)"
        r" vai1=(on|off|pend) vai2=(on|off|pend) vai3=(on|off|pend) vai4=(on|off|pend)"
        r"(?: cal=(off|interpolated|extrapolated))?", line)
    if not match:
        raise TesterError("protocol", "Malformed sensor supply status.")
    return {"enabled": match[1] == "1", "mv": int(match[2]), "ccr4": int(match[3]),
            "duty_percent": float(match[4]), "pwm": match[5],
            "rails": {index: match[index + 5] for index in range(1, 5)},
            "calibration": match[10] or "unknown", "timestamp": utc_now()}


def parse_vin(line: str) -> dict:
    match = re.fullmatch(r"ain ([1-4]) raw=(\d+) mv=(\d+)", line)
    if not match:
        raise TesterError("protocol", "Malformed VIN response.")
    raw = integer(int(match[2]), "ADC raw", 0, 4095)
    mv = integer(int(match[3]), "VIN mV", 0, 10076)
    return {"channel": int(match[1]), "raw": raw, "mv": mv,
            "saturated": raw == 4095, "valid": raw != 4095, "timestamp": utc_now()}


class SerialTransport:
    def __init__(self, serial_port):
        self.serial = serial_port
        self.condition = threading.Condition()
        self.lines = deque()
        self.error = None
        self.stopping = threading.Event()
        self.reader = threading.Thread(target=self._read, name="tester-reader", daemon=True)
        self.reader.start()

    def _read(self):
        buffer = bytearray()
        try:
            while not self.stopping.is_set():
                data = self.serial.read(1)
                if not data:
                    continue
                if data in (b"\r", b"\n"):
                    if buffer:
                        line = buffer.decode("utf-8", errors="strict")
                        buffer.clear()
                        with self.condition:
                            if len(self.lines) >= 2048:
                                raise ValueError("Serial receive queue overflow")
                            self.lines.append(line)
                            self.condition.notify_all()
                else:
                    buffer.extend(data)
                    if len(buffer) > 4096:
                        raise ValueError("Serial line too long")
        except Exception as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()

    def write(self, command: str, ending: bytes):
        data = command.encode("ascii") + ending
        try:
            if self.serial.write(data) != len(data):
                raise OSError("Incomplete serial write")
        except Exception as error:
            raise TesterError("connection", f"Serial write failed: {error}", "unknown") from error

    def next_line(self, timeout: float = 0):
        deadline = time.monotonic() + timeout
        with self.condition:
            while True:
                if self.error:
                    raise TesterError("connection", self.error, "unknown")
                if self.lines:
                    return self.lines.popleft()
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self.stopping.is_set():
                    return None
                self.condition.wait(remaining)

    def close(self):
        self.stopping.set()
        with self.condition:
            self.condition.notify_all()
        try:
            self.serial.close()
        finally:
            self.reader.join(timeout=2)


class TesterClient:
    """One serial owner. All public operations are serialized, including compound actions."""

    def __init__(self, serial_factory=None, timeout: float = 1.5, clock=time.monotonic):
        self.timeout = number(timeout, "timeout")
        if not 0 < self.timeout <= 30:
            raise TesterError("validation", "timeout must be >0 and <=30 seconds.")
        self._factory = serial_factory
        self._clock = clock
        self._lock = threading.RLock()
        self._operation_local = threading.local()
        self._slots = threading.BoundedSemaphore(32)
        self._generation = 0
        self._events_condition = threading.Condition()
        self._events = deque(maxlen=2048)
        self._event_id = 0
        self._transport = None
        self._background = None
        self._stop_background = threading.Event()
        self._state = "disconnected"
        self._port = None
        self._last_safe_off = None
        self._wm_observed = None
        self._supply_observed = None
        self._wm = {}
        self._supply = None
        self._last_safe_off = None
        self._wm_observed = None
        self._supply_observed = None
        self._vin = {}
        self._operations = {}
        self._active = None
        self._auto = {}
        self._auto_queue = deque()
        self._sampling = set()
        self._next_poll = 0
        self._poll_index = 0
        self._configs = {index: ChannelConfig(mv, ScalingConfig(), value=mv / 150)
                         for index, mv in enumerate((5000, 7500, 10000, 15000), 1)}

    @staticmethod
    def list_ports() -> list:
        try:
            from serial.tools import list_ports
        except ImportError:
            raise TesterError("dependency", "Install pyserial: python -m pip install pyserial") from None
        return [{"port": item.device, "description": item.description, "hwid": item.hwid}
                for item in list_ports.comports()]

    def _event(self, kind: str, **data):
        with self._events_condition:
            self._event_id += 1
            self._events.append({"id": self._event_id, "type": kind,
                                 "timestamp": utc_now(), **data})
            self._events_condition.notify_all()

    def get_events(self, after: int = 0, timeout_ms: int = 0) -> dict:
        integer(after, "after", 0, 2**63 - 1)
        integer(timeout_ms, "timeout_ms", 0, 30000)
        deadline = time.monotonic() + timeout_ms / 1000
        with self._events_condition:
            while self._event_id <= after and time.monotonic() < deadline:
                self._events_condition.wait(deadline - time.monotonic())
            oldest = self._events[0]["id"] if self._events else 1
            return {"events": deepcopy([event for event in self._events if event["id"] > after]),
                    "gap": after < oldest - 1, "last_id": self._event_id}

    def _fault(self, error: TesterError):
        self._state = "fault"
        self._auto.clear()
        self._auto_queue.clear()
        self._vin.clear()
        self._wm = {}
        self._supply = None
        if self._active:
            self._active.update(status="unknown", error=error.to_dict())
            self._active = None
        self._event("fault", error=error.to_dict(), outputs="unknown")

    @contextmanager
    def _exclusive(self, require_ready=True, safety=False):
        if getattr(self._operation_local, "active", False):
            if require_ready and self._state != "ready":
                raise TesterError("disconnected", "Connect to the tester; faults require reconnect.")
            yield
            return
        generation = self._generation
        if not self._slots.acquire(blocking=False):
            raise TesterError("busy", "Command queue is full.")
        try:
            with self._lock:
                if not safety and generation != self._generation:
                    raise TesterError("cancelled", "Command cancelled by safe shutdown.")
                if require_ready and self._state != "ready":
                    raise TesterError("disconnected", "Connect to the tester; faults require reconnect.")
                self._operation_local.active = True
                try:
                    yield
                finally:
                    self._operation_local.active = False
        finally:
            self._slots.release()

    def _consume(self, line: str):
        self._event("serial.rx", line=line)
        if line == "App Started" and self._state == "ready":
            error = TesterError("reset", "Tester restarted. Reconnect before further operations.", "unknown")
            self._fault(error)
            raise error
        match = re.fullmatch(r"vai ([1-4]) OFF pulse (complete|cancelled)", line)
        if match and self._active and self._active["channel"] == int(match[1]):
            self._active["completion"] = match[2]
        if line.startswith("vsen en="):
            self._supply = parse_supply_status(line)
            self._supply_observed = self._clock()
        elif line.startswith("wm status"):
            self._wm = parse_wm_status(line)
            self._wm_observed = self._clock()

    def _drain(self):
        while self._transport:
            line = self._transport.next_line()
            if line is None:
                break
            self._consume(line)

    def _command(self, command: str, pattern: str, supply_tail=False) -> list:
        if not self._transport or self._state == "fault":
            raise TesterError("disconnected", "No synchronized tester connection.", "unknown")
        try:
            self._drain()
            self._event("serial.tx", line=command)
            if not command.startswith("get ") and command != "help":
                self._last_safe_off = False
            self._transport.write(command, self._ending)
            deadline = time.monotonic() + self.timeout
            result = []
            matched = False
            while True:
                line = self._transport.next_line(max(0, deadline - time.monotonic()))
                if line is None:
                    raise TesterError("timeout", f"No complete response to: {command}", "unknown")
                self._consume(line)
                if line == command:
                    continue
                if line.startswith("ERROR"):
                    code = "unsupported" if re.match(r"ERROR get ain [1-4](?: \(Scanner Error\))?$", line) else "firmware"
                    raise TesterError(code, line)
                if not matched and re.fullmatch(pattern, line):
                    matched = True
                    result.append(line)
                    if not supply_tail:
                        return result
                elif matched and line.startswith("vsen en="):
                    result.append(line)
                    return result
                if time.monotonic() >= deadline:
                    raise TesterError("timeout", f"Response deadline: {command}", "unknown")
        except TesterError as error:
            if error.outcome == "unknown" or error.code == "protocol":
                self._fault(error)
            raise

    def connect(self, port: str, baudrate: int = 115200, line_ending: str = "LF") -> dict:
        if not isinstance(port, str) or not port.strip() or len(port) > 200:
            raise TesterError("validation", "A serial port name is required.")
        integer(baudrate, "baudrate", 1200, 3000000)
        endings = {"LF": b"\n", "CRLF": b"\r\n", "CR": b"\r"}
        if not isinstance(line_ending, str) or line_ending not in endings:
            raise TesterError("validation", "line_ending must be LF, CRLF or CR.")
        if self._transport:
            raise TesterError("conflict", "Disconnect the current session before connecting.")
        with self._exclusive(require_ready=False):
            if self._transport:
                raise TesterError("conflict", "A session is already open.")
            self._ending = endings[line_ending]
            self._state = "connecting"
            self._port = port
            try:
                factory = self._factory
                if factory is None:
                    try:
                        import serial
                    except ImportError:
                        raise TesterError("dependency", "Install pyserial: python -m pip install pyserial") from None
                    factory = serial.Serial
                serial_port = factory(port=port, baudrate=baudrate, timeout=0.1,
                                      write_timeout=self.timeout, dsrdtr=False, rtscts=False)
                try:
                    serial_port.dtr = False
                    serial_port.rts = False
                    self._transport = SerialTransport(serial_port)
                except Exception:
                    serial_port.close()
                    raise
                self._command("get status", r"wm status.*")
                self._state = "safe_reset"
                self._safe_off()
                self._state = "ready"
                self._sampling = {1, 2, 3, 4}
                self._next_poll = self._clock() + 0.25
                self._stop_background.clear()
                self._background = threading.Thread(target=self._background_loop,
                                                    name="tester-service", daemon=True)
                self._background.start()
                self._event("connected", port=port)
                return self._snapshot()
            except Exception as error:
                if self._transport:
                    self._transport.close()
                self._transport = None
                wrapped = error if isinstance(error, TesterError) else TesterError("connection", str(error), "unknown")
                self._fault(wrapped)
                raise wrapped

    def _get_wm(self):
        self._command("get status", r"wm status.*")
        return self._wm

    def _get_supply(self):
        self._command("get vsen", r"vsen en=.*")
        return self._supply

    def _verify_supply_off(self):
        supply = self._get_supply()
        if supply["enabled"] or any(value != "off" for value in supply["rails"].values()):
            raise TesterError("unsafe", "Sensor supply OFF could not be verified.", "unknown")
        return supply

    def _safe_off(self):
        self._auto.clear()
        self._auto_queue.clear()
        failures = []
        for command, pattern in [(f"stop wm {channel}", rf"wm {channel} stopped")
                                 for channel in range(1, 5)] + [("set vsen 0", r"vsen set to 0 mV.*")]:
            try:
                self._command(command, pattern)
            except TesterError as error:
                failures.append(error.to_dict())
        try:
            wm = self._get_wm()
            supply = self._verify_supply_off()
            if any(item["state"] != "stopped" for item in wm.values()) or supply["mv"] != 0:
                failures.append({"message": "Outputs are not all stopped/zero."})
        except TesterError as error:
            failures.append(error.to_dict())
        if failures:
            error = TesterError("unsafe", f"Safe shutdown incomplete: {failures}", "unknown")
            self._fault(error)
            raise error
        if self._active:
            self._active.update(status="cancelled", timestamp=utc_now())
            self._event("pulse.cancelled", operation_id=self._active["id"])
            self._active = None
        self._event("safe_off", verified=True)
        self._last_safe_off = True
        return {"safe_off": True, "verified": True}

    def safe_off(self):
        self._generation += 1
        with self._exclusive(safety=True):
            return self._safe_off()

    def disconnect(self):
        self._generation += 1
        self._stop_background.set()
        error = None
        with self._exclusive(require_ready=False, safety=True):
            try:
                if self._transport:
                    if self._state == "fault":
                        raise TesterError("unsafe", "Link is unsynchronized; outputs remain unknown.", "unknown")
                    self._safe_off()
            except TesterError as caught:
                error = caught
            finally:
                if self._transport:
                    self._transport.close()
                self._transport = None
                self._state = "disconnected"
                self._auto.clear()
                self._auto_queue.clear()
                self._sampling.clear()
                self._vin.clear()
                self._wm = {}
                self._supply = None
                self._wm_observed = None
                self._supply_observed = None
                self._event("disconnected", outputs="verified_off" if self._last_safe_off is True else "unknown")
        if self._background and self._background is not threading.current_thread():
            self._background.join(timeout=2)
        if error:
            raise error
        return {"connected": False, "safe_off": self._last_safe_off}

    close = disconnect

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.disconnect()

    def _snapshot(self):
        now = self._clock()
        return deepcopy({"connection": self._state, "port": self._port, "timestamp": utc_now(),
                "wm": {channel: dict(item) for channel, item in self._wm.items()},
                "supply": self._supply, "outputs_known": self._state == "ready",
            "wm_age_seconds": None if self._wm_observed is None else max(0, now - self._wm_observed),
            "supply_age_seconds": None if self._supply_observed is None else max(0, now - self._supply_observed),
            "last_safe_off": self._last_safe_off,
                "vin": {channel: {**sample, "age_seconds": max(0, now - sample["monotonic"])}
                        for channel, sample in self._vin.items()},
                "config": {channel: asdict(config) for channel, config in self._configs.items()},
                "sampling": sorted(self._sampling), "auto": {channel: dict(value) for channel, value in self._auto.items()},
                "auto_queue": list(self._auto_queue),
                "active_operation": dict(self._active) if self._active else None})

    def get_status(self, refresh: bool = False):
        if not isinstance(refresh, bool):
            raise TesterError("validation", "refresh must be a boolean.")
        with self._exclusive(require_ready=refresh):
            if refresh:
                self._get_wm()
                self._get_supply()
            return self._snapshot()

    @staticmethod
    def get_capabilities():
        return {"api_version": "1", "wm_channels": [1, 2, 3, 4], "sensor_channels": [1, 2, 3, 4],
                "voltage_mv": [0, 15000], "pulse_duration_ms": [10, 3600000],
                "wm_cycle_ms_host_policy": [20, 3600000], "vin_max_mv": 10076,
                "calibrated_mv": [334, 10120], "trigger_wm": False,
                "trigger_limitation": "Firmware calls wm.Task(false); valve triggering is unavailable.",
                "safe_off_on_connect_and_disconnect": True, "shared_sensor_supply": True,
                "physical_voltage_verified": False}

    def set_wm_output(self, channel: int, enabled: bool):
        channel_id(channel)
        if not isinstance(enabled, bool):
            raise TesterError("validation", "enabled must be a boolean.")
        if not enabled:
            return self.stop_wm(channel)
        with self._exclusive():
            status = self._get_wm()[channel]["state"]
            if status == "manual on":
                return {"channel": channel, "state": status, "changed": False}
            if status != "stopped":
                raise TesterError("conflict", "Stop WM pulses before selecting steady HIGH.")
            self._command(f"toggle wm {channel}", rf"wm {channel} manual on")
            if self._get_wm()[channel]["state"] != "manual on":
                self._verification_failed("WM HIGH verification failed.")
            return {"channel": channel, "state": "manual on", "changed": True}

    def start_wm(self, channel: int, cycle_ms: int = 1000):
        channel_id(channel)
        integer(cycle_ms, "cycle_ms", 20, 3600000)
        with self._exclusive():
            self._command(f"start wm {channel} {cycle_ms}", rf"wm {channel} started")
            status = self._get_wm()[channel]
            if status != {"state": "started", "cycle_ms": cycle_ms}:
                self._verification_failed("WM start verification failed.")
            return {"channel": channel, **status}

    def stop_wm(self, channel: int):
        channel_id(channel)
        with self._exclusive():
            self._command(f"stop wm {channel}", rf"wm {channel} stopped")
            status = self._get_wm()[channel]
            if status["state"] != "stopped":
                self._verification_failed("WM stop verification failed.")
            return {"channel": channel, **status}

    def _verification_failed(self, message):
        error = TesterError("unsafe", message, "unknown")
        self._fault(error)
        raise error

    def _configurable(self, channel):
        channel_id(channel)
        if channel in self._auto or self._active:
            raise TesterError("conflict", "Disarm AUTO and finish the pulse before changing settings.")
        return self._configs[channel]

    def set_scaling(self, channel, x1, x2, y1, y2):
        scaling = ScalingConfig(x1, x2, y1, y2)
        with self._exclusive(require_ready=False):
            config = self._configurable(channel)
            config.scaling = scaling
            return asdict(config)

    def set_scaling_mode(self, channel, mode):
        if mode not in ("manual", "automatic"):
            raise TesterError("validation", "mode must be manual or automatic.")
        with self._exclusive(require_ready=False):
            config = self._configurable(channel)
            if mode == "manual":
                config.scaling.from_mv(config.mv)
            else:
                config.scaling.to_mv(config.value)
            config.scaling_mode = mode
            return asdict(config)

    def set_voltage(self, channel, mv):
        integer(mv, "mv", 0, 15000)
        with self._exclusive(require_ready=False):
            config = self._configurable(channel)
            if config.scaling_mode != "manual":
                raise TesterError("conflict", "Select manual mode to set mV directly.")
            config.mv = mv
            return asdict(config)

    def set_engineering_value(self, channel, value):
        with self._exclusive(require_ready=False):
            config = self._configurable(channel)
            if config.scaling_mode != "automatic":
                raise TesterError("conflict", "Select automatic scaling mode first.")
            result = config.scaling.to_mv(value)
            config.value = number(value, "value")
            return {**asdict(config), **result}

    def _supply_available(self, channel=None):
        if self._auto or self._active:
            raise TesterError("conflict", "Sensor supply is owned by AUTO or an active pulse.")
        supply = self._get_supply()
        if any(state != "off" and owner != channel for owner, state in supply["rails"].items()):
            raise TesterError("conflict", "A different sensor owns the shared supply.")

    def sensor_on(self, channel):
        channel_id(channel)
        with self._exclusive():
            self._supply_available(channel)
            resolved = self._configs[channel].resolved()
            mv = resolved["mv"]
            try:
                self._command("set vsen 0", r"vsen set to 0 mV.*")
                if mv:
                    self._command(f"set vsen {mv}", rf"vsen set to {mv} mV.*")
                    self._command("set vsen_en on", rf"vsen_en ON, {mv} mV")
                    self._command(f"set vai {channel} on", rf"vai {channel} ON")
                supply = self._get_supply()
                expected = {owner: "on" if owner == channel and mv else "off" for owner in range(1, 5)}
                if supply["mv"] != mv or supply["rails"] != expected or supply["enabled"] != bool(mv):
                    raise TesterError("unsafe", "Sensor ON status verification failed.")
                return {"channel": channel, **resolved, "supply": supply,
                        "calibration_warning": bool(mv and not 334 <= mv <= 10120)}
            except TesterError as error:
                cleanup = "unknown"
                if self._state != "fault":
                    try:
                        self._command("set vsen 0", r"vsen set to 0 mV.*")
                        self._verify_supply_off()
                        cleanup = "verified_off"
                    except TesterError:
                        pass
                self._event("sensor.error", error=error.to_dict(), cleanup=cleanup)
                if cleanup == "unknown" and self._state != "fault":
                    self._fault(TesterError("unsafe", "Sensor cleanup failed.", "unknown"))
                raise

    def sensor_off(self, channel):
        channel_id(channel)
        with self._exclusive():
            if self._auto:
                raise TesterError("conflict", "Disable AUTO before manual sensor commands.")
            if self._active:
                return self._stop_sensor(channel)
            self._supply_available(channel)
            self._command("set vsen 0", r"vsen set to 0 mV.*")
            return {"channel": channel, "supply": self._verify_supply_off()}

    def get_supply_status(self):
        with self._exclusive():
            return deepcopy(self._get_supply())

    def execute_channel_batch(self, commands):
        with self._exclusive():
            prepared = prepare_channel_commands(commands, self._configs)
            generation = self._generation
            results = []
            failure = None
            cleanup = None
            for index, command in enumerate(prepared):
                entry = {"index": index, "Port": command["Port"], "PortNum": command["PortNum"],
                         "Action": command["Action"], "status": "skipped", "result": None, "error": None}
                results.append(entry)
                if failure:
                    continue
                try:
                    if generation != self._generation:
                        raise TesterError("cancelled", "Batch interrupted by safe shutdown.")
                    channel = command["PortNum"]
                    port, action = command["Port"], command["Action"]
                    if port == "VAI":
                        if action == "Configure":
                            config = deepcopy(command["config"])
                            auto_enabled = command["auto_enabled"]
                            if auto_enabled is False:
                                self.configure_auto(channel, False)
                            if config != self._configs[channel]:
                                self._configurable(channel)
                                self._configs[channel] = config
                            if auto_enabled is True:
                                existing = self._auto.get(channel)
                                duration = command["auto_duration_ms"]
                                if existing:
                                    if duration is not None and duration != existing["duration_ms"]:
                                        raise TesterError("conflict", "Disarm AUTO before changing its duration.")
                                else:
                                    self.configure_auto(channel, True, 5000 if duration is None else duration)
                            automatic = self._auto.get(channel)
                            result = {**asdict(config), "resolved_mv": config.resolved()["mv"],
                                      "warning": config.resolved()["warning"],
                                      "Auto_Enabled": automatic is not None,
                                      "Duration_ms": automatic["duration_ms"] if automatic else None}
                        elif action == "On":
                            result = self.sensor_on(channel)
                        elif action == "Off":
                            result = self.sensor_off(channel)
                        elif action == "Stop":
                            result = self.stop_sensor(channel)
                        else:
                            result = self.pulse_sensor(channel, command["mv"], command["duration_ms"])
                    elif port == "WM":
                        if action == "Start":
                            result = self.start_wm(channel, command["cycle_ms"])
                        elif action == "Stop":
                            result = self.stop_wm(channel)
                        else:
                            result = self.set_wm_output(channel, action == "On")
                    else:
                        result = self.read_vin(channel)
                    entry.update(status=result.get("status", "completed"), result=deepcopy(result))
                except Exception as caught:
                    error = caught if isinstance(caught, TesterError) else TesterError(
                        "internal", "Unexpected batch failure.", "unknown")
                    entry.update(status="unknown" if error.outcome == "unknown" else "failed", error=error.to_dict())
                    failure = error
                    try:
                        self._safe_off()
                        cleanup = {"attempted": True, "verified": True, "error": None}
                    except Exception as cleanup_error:
                        wrapped = cleanup_error if isinstance(cleanup_error, TesterError) else TesterError(
                            "unsafe", "Unexpected cleanup failure; outputs remain unknown.", "unknown")
                        cleanup = {"attempted": True, "verified": False, "error": wrapped.to_dict()}
                        failure = TesterError("unsafe", "Batch failed and shutdown could not be verified.", "unknown")
            for entry in results:
                result = entry["result"]
                if isinstance(result, dict) and result.get("id") in self._operations:
                    entry["result"] = deepcopy(self._operations[result["id"]])
                    entry["status"] = entry["result"]["status"]
            status = "unknown" if failure and failure.outcome == "unknown" else "failed" if failure else "completed"
            if not failure and any(entry["status"] in ("accepted", "running") for entry in results):
                status = "running"
            self._event("batch.finished", status=status, command_count=len(results))
            return {"status": status, "commands": results, "cleanup": cleanup,
                    "error": failure.to_dict() if failure else None}

    def _start_pulse(self, channel, mv, duration_ms, automatic=False):
        if len(self._operations) >= 1024:
            for operation_id in list(self._operations):
                if self._operations[operation_id]["status"] not in ("running", "accepted"):
                    del self._operations[operation_id]
                    break
        operation = {"id": uuid.uuid4().hex, "channel": channel, "mv": mv,
                     "duration_ms": duration_ms, "status": "accepted", "automatic": automatic,
                     "timestamp": utc_now(), "deadline": self._clock() + duration_ms / 1000 + self.timeout}
        self._active = operation
        self._operations[operation["id"]] = operation
        try:
            self._command(f"pulse vai {channel} {mv} {duration_ms}",
                          rf"vai {channel} (?:ON|OFF) pulse_ms={duration_ms}", supply_tail=True)
            supply = self._supply
            expected = {owner: "on" if owner == channel and mv else "off" for owner in range(1, 5)}
            if supply["mv"] != mv or supply["rails"] != expected or supply["enabled"] != bool(mv):
                raise TesterError("unsafe", "Pulse start supply status mismatch.", "unknown")
            operation["status"] = "running"
            operation["deadline"] = self._clock() + duration_ms / 1000 + self.timeout
            self._event("pulse.started", operation_id=operation["id"], channel=channel)
            return dict(operation)
        except TesterError as error:
            operation.update(status="unknown" if error.outcome == "unknown" else "failed", error=error.to_dict())
            self._abort_auto(error)
            raise

    def pulse_sensor(self, channel, mv, duration_ms, wait=False):
        channel_id(channel)
        integer(mv, "mv", 0, 15000)
        integer(duration_ms, "duration_ms", 10, 3600000)
        if not isinstance(wait, bool):
            raise TesterError("validation", "wait must be boolean.")
        with self._exclusive():
            self._supply_available()
            result = self._start_pulse(channel, mv, duration_ms)
        if wait:
            return self.wait_operation(result["id"], duration_ms + round(2 * self.timeout * 1000))
        return result

    def _finish_pulse(self):
        operation = self._active
        if operation and operation.get("completion"):
            try:
                self._verify_supply_off()
            except TesterError as error:
                self._abort_auto(error)
                raise
            operation.update(status="completed" if operation["completion"] == "complete" else "cancelled",
                             timestamp=utc_now())
            self._vin.pop(operation["channel"], None)
            self._event("pulse." + operation["status"], operation_id=operation["id"], channel=operation["channel"])
            self._active = None
        elif operation and self._clock() >= operation["deadline"]:
            error = TesterError("timeout", "No pulse completion received; forcing sensor OFF.", "unknown")
            self._abort_auto(error)
            raise error

    def _stop_sensor(self, channel):
        if self._active and self._active["channel"] != channel:
            raise TesterError("conflict", "A different sensor owns the active pulse.")
        if not self._active:
            self._supply_available(channel)
            if self._supply["rails"][channel] != "off":
                raise TesterError("conflict", "Use OFF for a manually enabled sensor.")
            return {"channel": channel, "state": "idle"}
        self._command(f"stop vai {channel}", rf"vai {channel} OFF pulse cancelled", supply_tail=True)
        self._finish_pulse()
        return {"channel": channel, "state": "stopped"}

    def stop_sensor(self, channel):
        channel_id(channel)
        with self._exclusive():
            if self._auto:
                raise TesterError("conflict", "Disable AUTO to cancel its output.")
            return self._stop_sensor(channel)

    def get_operation(self, operation_id):
        if not isinstance(operation_id, str) or not operation_id or len(operation_id) > 128:
            raise TesterError("validation", "operation_id must be a nonempty string (max 128).")
        with self._exclusive(require_ready=False):
            if operation_id not in self._operations:
                raise TesterError("not_found", "Operation not found or expired.")
            return deepcopy(self._operations[operation_id])

    def wait_operation(self, operation_id, timeout_ms=10000):
        integer(timeout_ms, "timeout_ms", 0, 3700000)
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            operation = self.get_operation(operation_id)
            if operation["status"] not in ("accepted", "running"):
                return operation
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TesterError("timeout", "Wait expired; operation may still be running.", "unknown")
            with self._events_condition:
                self._events_condition.wait(min(remaining, 0.05))

    def get_time(self):
        with self._exclusive():
            return {"time": self._command("get time", r"sys time \d{1,2}:\d{1,2}:\d{1,2}")[0][9:]}

    def set_time(self, value):
        if not isinstance(value, str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise TesterError("validation", "Time must be HH:MM, 00:00..23:59.")
        with self._exclusive():
            self._command(f"set time {value}", r"OK")
            return {"time": value}

    def get_help(self):
        with self._exclusive():
            self._command("help", r"OK")
            return {"message": "Firmware help lines are available in serial.rx events."}

    def system_init(self):
        self._generation += 1
        with self._exclusive(safety=True):
            self._safe_off()
            self._command("system init", r"OK")
            self._safe_off()
            self._vin.clear()
            return {"initialized": True, "safe_off": True}

    def _read_vin(self, channel):
        try:
            line = self._command(f"get ain {channel}", rf"ain {channel} raw=\d+ mv=\d+")[0]
            sample = parse_vin(line)
            sample["monotonic"] = self._clock()
            self._vin[channel] = sample
            self._event("vin", sample=sample)
            if channel in self._auto and (not self._active or self._active["channel"] != channel):
                if sample["valid"] and sample["mv"] > 1000:
                    if channel not in self._auto_queue:
                        self._auto_queue.append(channel)
                else:
                    self._auto_queue = deque(owner for owner in self._auto_queue if owner != channel)
            return dict(sample)
        except TesterError as error:
            self._vin.pop(channel, None)
            self._auto_queue = deque(owner for owner in self._auto_queue if owner != channel)
            if error.code == "unsupported":
                self._sampling.clear()
            if self._auto:
                self._abort_auto(error)
            raise

    def read_vin(self, channel):
        channel_id(channel)
        with self._exclusive():
            return self._read_vin(channel)

    def configure_sampling(self, channels, enabled=True):
        if not isinstance(channels, (list, tuple)) or not channels:
            raise TesterError("validation", "channels must be a nonempty list.")
        selected = {channel_id(channel) for channel in channels}
        if not isinstance(enabled, bool):
            raise TesterError("validation", "enabled must be a boolean.")
        with self._exclusive():
            if enabled:
                self._sampling.update(selected)
            else:
                self._sampling.difference_update(selected)
            return {"sampling": sorted(self._sampling), "auto_required": sorted(self._auto)}

    def configure_auto(self, channel, enabled, duration_ms=5000):
        channel_id(channel)
        integer(duration_ms, "duration_ms", 10, 3600000)
        if not isinstance(enabled, bool):
            raise TesterError("validation", "enabled must be a boolean.")
        with self._exclusive():
            if not enabled:
                self._auto.pop(channel, None)
                self._auto_queue = deque(owner for owner in self._auto_queue if owner != channel)
                self._vin.pop(channel, None)
                if self._active and self._active["channel"] == channel and self._active["automatic"]:
                    self._stop_sensor(channel)
                self._event("auto.disabled", channel=channel)
                return {"channel": channel, "enabled": False}
            if self._active and not self._active["automatic"]:
                raise TesterError("conflict", "Finish the manual pulse before arming AUTO.")
            if channel in self._auto:
                raise TesterError("conflict", "Disarm AUTO before changing its settings.")
            if not self._active:
                self._verify_supply_off()
            resolved = self._configs[channel].resolved()
            self._auto[channel] = {"duration_ms": duration_ms, "mv": resolved["mv"],
                                   "threshold_mv": 1000, "enabled": True}
            self._vin.pop(channel, None)
            self._event("auto.armed", channel=channel)
            return {"channel": channel, **self._auto[channel]}

    def _abort_auto(self, error):
        disarmed = sorted(self._auto)
        self._auto.clear()
        self._auto_queue.clear()
        operation = self._active
        if self._state != "fault":
            try:
                self._command("set vsen 0", r"vsen set to 0 mV.*")
                self._verify_supply_off()
                if operation:
                    operation.update(status="failed", error=error.to_dict())
                self._active = None
            except TesterError as cleanup_error:
                if self._state != "fault":
                    self._fault(cleanup_error)
        self._event("supply.error", error=error.to_dict(), auto_disarmed=disarmed)

    def _dispatch_auto(self):
        if self._active:
            return
        while self._auto_queue:
            channel = self._auto_queue.popleft()
            sample = self._vin.get(channel)
            if (channel not in self._auto or not sample or not sample["valid"]
                    or sample["mv"] <= 1000 or self._clock() - sample["monotonic"] > 2):
                continue
            settings = self._auto[channel]
            self._start_pulse(channel, settings["mv"], settings["duration_ms"], automatic=True)
            return

    def _service(self):
        self._drain()
        self._finish_pulse()
        channels = sorted(self._sampling | set(self._auto))
        if channels and self._clock() >= self._next_poll:
            channel = channels[self._poll_index % len(channels)]
            self._poll_index += 1
            self._next_poll = self._clock() + 0.25
            self._read_vin(channel)
        self._dispatch_auto()

    def _background_loop(self):
        while not self._stop_background.wait(0.02):
            if not self._lock.acquire(blocking=False):
                continue
            try:
                if self._state == "ready":
                    self._service()
            except TesterError as error:
                self._event("service.error", error=error.to_dict())
                if self._auto:
                    self._abort_auto(error)
                elif error.outcome == "unknown" and self._state != "fault":
                    self._fault(error)
            except Exception as error:
                self._fault(TesterError("internal", str(error), "unknown"))
            finally:
                self._lock.release()


CLI_HELP = """PORTS | CONNECT <port> | DISCONNECT | STATUS | CAPABILITIES | SAFE_OFF | EXIT
ON WM1 | OFF WM1 | START WM1 CYCLE_MS 1000 | STOP WM1
MODE VAI1 MANUAL|AUTOMATIC | SET VAI1 MV 5000 | VALUE VAI1 50
SCALE VAI1 X1 0 X2 10000 Y1 0 Y2 100
ON VAI1 | OFF VAI1 | PULSE VAI1 MV 5000 DURATION_MS 2000 | STOP VAI1
VIN AI1|ALL | SAMPLE AI1 AI2 ON | SAMPLE ALL OFF
AUTO VAI1 ON DURATION_MS 5000 | AUTO VAI1 OFF
TIME GET | TIME SET 14:30 | SYSTEM INIT | SUPPLY STATUS | FIRMWARE HELP
WAIT <operation_id> TIMEOUT_MS 10000 | EVENTS AFTER 0"""


class CommandDispatcher:
    def __init__(self, client: TesterClient):
        self.client = client
        self.actions = {
            "ports": client.list_ports, "connection.connect": client.connect,
            "connection.disconnect": client.disconnect, "status": client.get_status,
            "capabilities": client.get_capabilities, "safety.off": client.safe_off,
            "wm.on": lambda channel: client.set_wm_output(channel, True),
            "wm.off": lambda channel: client.set_wm_output(channel, False),
            "wm.start": client.start_wm, "wm.stop": client.stop_wm,
            "sensor.on": client.sensor_on, "sensor.off": client.sensor_off,
            "sensor.pulse": client.pulse_sensor, "sensor.stop": client.stop_sensor,
            "scaling.configure": client.set_scaling, "scaling.mode": client.set_scaling_mode,
            "scaling.value": client.set_engineering_value, "sensor.voltage": client.set_voltage,
            "vin.read": client.read_vin, "sampling.configure": client.configure_sampling,
            "auto.configure": client.configure_auto, "supply.status": client.get_supply_status,
            "system.init": client.system_init, "time.get": client.get_time, "time.set": client.set_time,
            "firmware.help": client.get_help, "operation.get": client.get_operation,
            "operation.wait": client.wait_operation, "events": client.get_events,
            "help": lambda: {"commands": CLI_HELP.splitlines()},
        }

    def execute(self, action: str, args=None):
        if action == "wm.trigger":
            raise TesterError("unsupported", "Valve-based WM triggering is unavailable in this firmware.")
        if not isinstance(action, str) or action not in self.actions:
            raise TesterError("validation", "Unknown action. Use help or capabilities.")
        if args is None:
            args = {}
        if not isinstance(args, dict) or not all(isinstance(key, str) for key in args):
            raise TesterError("validation", "args must be an object with string keys.")
        function = self.actions[action]
        try:
            inspect.signature(function).bind(**args)
        except TypeError as error:
            raise TesterError("validation", str(error)) from None
        return function(**args)


def cli_number(text: str):
    try:
        return int(text)
    except ValueError:
        try:
            return number(float(text), "numeric argument")
        except ValueError:
            raise TesterError("validation", f"Invalid number: {text}") from None


def parse_cli(command: str):
    if not isinstance(command, str) or len(command) > 4096:
        raise TesterError("validation", "CLI input must be at most 4096 characters.")
    try:
        tokens = shlex.split(command)
    except ValueError as error:
        raise TesterError("validation", str(error)) from None
    upper = [token.upper() for token in tokens]
    if not tokens:
        raise TesterError("validation", "Empty command.")
    simple = {"PORTS": "ports", "DISCONNECT": "connection.disconnect", "STATUS": "status",
              "CAPABILITIES": "capabilities", "SAFE_OFF": "safety.off", "HELP": "help", "EXIT": "exit"}
    if len(tokens) == 1 and upper[0] in simple:
        return simple[upper[0]], {}
    if upper[0] == "CONNECT" and len(tokens) == 2:
        return "connection.connect", {"port": tokens[1]}
    if upper == ["SYSTEM", "INIT"]:
        return "system.init", {}
    if upper == ["TIME", "GET"]:
        return "time.get", {}
    if len(tokens) == 3 and upper[:2] == ["TIME", "SET"]:
        return "time.set", {"value": tokens[2]}
    if upper == ["SUPPLY", "STATUS"]:
        return "supply.status", {}
    if upper == ["FIRMWARE", "HELP"]:
        return "firmware.help", {}
    if len(tokens) == 3 and upper[:2] == ["EVENTS", "AFTER"]:
        return "events", {"after": cli_number(tokens[2])}
    if len(tokens) == 4 and upper[0] == "WAIT" and upper[2] == "TIMEOUT_MS":
        return "operation.wait", {"operation_id": tokens[1], "timeout_ms": cli_number(tokens[3])}
    if upper[0] == "SAMPLE" and len(tokens) >= 3 and upper[-1] in ("ON", "OFF"):
        channels = [1, 2, 3, 4] if upper[1:-1] == ["ALL"] else [
            int(token[2:]) for token in upper[1:-1] if re.fullmatch(r"AI[1-4]", token)]
        if upper[1:-1] != ["ALL"] and len(channels) != len(tokens) - 2:
            raise TesterError("validation", "Use SAMPLE AI1 AI2 ON or SAMPLE ALL OFF.")
        return "sampling.configure", {"channels": channels, "enabled": upper[-1] == "ON"}
    if len(tokens) >= 2:
        match = re.fullmatch(r"(WM|VAI|AI)([1-4])", upper[1])
        if match:
            kind, channel = match[1], int(match[2])
            verb = upper[0]
            args = {"channel": channel}
            if kind == "WM":
                if len(tokens) == 2 and verb in ("ON", "OFF", "STOP"):
                    return "wm." + verb.lower(), args
                if len(tokens) in (2, 4) and verb == "START":
                    if len(tokens) == 4:
                        if upper[2] != "CYCLE_MS":
                            raise TesterError("validation", "Expected CYCLE_MS.")
                        args["cycle_ms"] = cli_number(tokens[3])
                    return "wm.start", args
            if kind == "AI" and verb == "VIN" and len(tokens) == 2:
                return "vin.read", args
            if kind == "VAI":
                if verb in ("ON", "OFF", "STOP") and len(tokens) == 2:
                    return "sensor." + verb.lower(), args
                if verb == "MODE" and len(tokens) == 3:
                    return "scaling.mode", {**args, "mode": tokens[2].lower()}
                if verb == "VALUE" and len(tokens) == 3:
                    return "scaling.value", {**args, "value": cli_number(tokens[2])}
                if verb == "SET" and len(tokens) == 4 and upper[2] == "MV":
                    return "sensor.voltage", {**args, "mv": cli_number(tokens[3])}
                if verb == "SCALE" and len(tokens) == 10 and upper[2::2] == ["X1", "X2", "Y1", "Y2"]:
                    return "scaling.configure", {**args, **{key.lower(): cli_number(value)
                                                           for key, value in zip(tokens[2::2], tokens[3::2])}}
                if verb == "PULSE" and len(tokens) == 6 and upper[2::2] == ["MV", "DURATION_MS"]:
                    return "sensor.pulse", {**args, "mv": cli_number(tokens[3]), "duration_ms": cli_number(tokens[5])}
                if verb == "AUTO" and len(tokens) in (3, 5) and upper[2] in ("ON", "OFF"):
                    args["enabled"] = upper[2] == "ON"
                    if len(tokens) == 5:
                        if upper[3] != "DURATION_MS":
                            raise TesterError("validation", "Expected DURATION_MS.")
                        args["duration_ms"] = cli_number(tokens[4])
                    return "auto.configure", args
    if upper == ["VIN", "ALL"]:
        return "vin.all", {}
    raise TesterError("validation", "Unrecognized command. Type HELP.")


HTTP_CODES = {"validation": 400, "conflict": 409, "disconnected": 409, "cancelled": 409,
              "firmware": 422, "unsupported": 422, "connection": 503, "dependency": 503,
              "busy": 503, "timeout": 504, "unsafe": 503, "reset": 503,
              "not_found": 404, "protocol": 502, "forbidden": 403, "internal": 500}


def result_envelope(request_id, result=None, error=None):
    status = "completed"
    if error:
        status = "unknown" if error.outcome == "unknown" else "failed"
    elif isinstance(result, dict) and result.get("status") in ("accepted", "running", "cancelled", "failed", "unknown"):
        status = result["status"]
    return {"api_version": "1", "id": request_id, "ok": error is None,
            "status": status, "result": result, "error": error.to_dict() if error else None,
            "timestamp": utc_now()}


class TesterHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, client: TesterClient, port=8765):
        integer(port, "http port", 0, 65535)
        self.dispatcher = CommandDispatcher(client)
        self._request_slots = threading.BoundedSemaphore(16)
        self._duplicates = {}
        self._duplicates_lock = threading.Lock()
        super().__init__(("127.0.0.1", port), TesterHttpHandler)

    def process_request(self, request, client_address):
        if not self._request_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()

    def run_command(self, payload):
        if not isinstance(payload, dict):
            raise TesterError("validation", "Request must be an object.")
        batch = "RequestId" in payload or "Commands" in payload
        fields = {"RequestId", "Commands"} if batch else {"id", "action", "args"}
        if set(payload) - fields:
            raise TesterError("validation", "Expected RequestId/Commands or id/action/args, without mixing formats.")
        request_id = payload.get("RequestId" if batch else "id")
        if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
            raise TesterError("validation", "id must be a nonempty string, max 128 characters.")
        action = payload.get("action")
        args = payload.get("args", {})
        if action == "sensor.pulse" and isinstance(args, dict) and args.get("wait"):
            raise TesterError("validation", "HTTP pulses are asynchronous; use operations to follow completion.")
        if action == "operation.wait":
            raise TesterError("validation", "Use GET operations over HTTP; do not block an HTTP command.")
        try:
            key = json.dumps(payload, sort_keys=True, allow_nan=False)
        except (ValueError, TypeError):
            raise TesterError("validation", "Arguments must be finite JSON values.") from None
        with self._duplicates_lock:
            record = self._duplicates.get(request_id)
            if record:
                if record["key"] != key:
                    raise TesterError("conflict", "Request id was already used for different arguments.")
            else:
                if len(self._duplicates) >= 1024:
                    expired = next((identifier for identifier, item in self._duplicates.items() if item["done"].is_set()), None)
                    if expired is None:
                        raise TesterError("busy", "Request-id cache is full.")
                    del self._duplicates[expired]
                record = {"key": key, "done": threading.Event(), "response": None}
                self._duplicates[request_id] = record
        if record["response"] is not None:
            return deepcopy(record["response"])
        with self._duplicates_lock:
            owner = not record.get("started", False)
            if owner:
                record["started"] = True
        if not owner:
            if not record["done"].wait(30):
                raise TesterError("timeout", "Original request still executing; retry with the SAME id.", "unknown")
            return deepcopy(record["response"])
        try:
            result = (self.dispatcher.client.execute_channel_batch(payload.get("Commands")) if batch
                      else self.dispatcher.execute(action, args))
            if batch and result["error"]:
                details = result["error"]
                error = TesterError(details["code"], details["message"], details["outcome"])
                envelope = result_envelope(request_id, result, error)
                code = HTTP_CODES.get(error.code, 500)
            else:
                envelope = result_envelope(request_id, result)
                code = 202 if envelope["status"] in ("accepted", "running") else 200
        except TesterError as error:
            code, envelope = HTTP_CODES.get(error.code, 500), result_envelope(request_id, error=error)
        except Exception:
            error = TesterError("internal", "Unexpected internal failure; inspect service events.", "unknown")
            code, envelope = 500, result_envelope(request_id, error=error)
        record["response"] = (code, envelope)
        record["done"].set()
        return deepcopy(record["response"])


class TesterHttpHandler(BaseHTTPRequestHandler):
    server: TesterHttpServer

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format, *args):
        pass

    def _reply(self, code, payload):
        data = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _validate_local(self):
        port = self.server.server_port
        if (self.headers.get("Host") not in (f"127.0.0.1:{port}", f"localhost:{port}")
                or self.headers.get("Origin") is not None):
            raise TesterError("forbidden", "Only non-browser loopback clients are supported.")

    def _handle(self, post=False):
        request_id = None
        try:
            self._validate_local()
            route = urlparse(self.path)
            if post:
                if route.path != "/api/v1/commands" or route.query:
                    raise TesterError("not_found", "Unknown endpoint.")
                if self.headers.get("Transfer-Encoding"):
                    raise TesterError("validation", "Chunked requests are not supported.")
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip() != "application/json":
                    raise TesterError("validation", "Content-Type must be application/json.")
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    raise TesterError("validation", "Invalid Content-Length.") from None
                integer(size, "body length", 1, 65536)
                body = self.rfile.read(size)
                if len(body) != size:
                    raise TesterError("validation", "Incomplete request body.")
                try:
                    payload = json.loads(body, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
                except (ValueError, UnicodeDecodeError):
                    raise TesterError("validation", "Body must be valid finite JSON.") from None
                if isinstance(payload, dict):
                    request_id = payload.get("RequestId", payload.get("id"))
                code, response = self.server.run_command(payload)
            else:
                query = parse_qs(route.query)
                endpoints = {"/api/v1/status": "status", "/api/v1/ports": "ports",
                             "/api/v1/capabilities": "capabilities"}
                if route.path in endpoints and not query:
                    result = self.server.dispatcher.execute(endpoints[route.path])
                elif route.path.startswith("/api/v1/operations/") and not query:
                    result = self.server.dispatcher.execute("operation.get", {"operation_id": route.path.rsplit("/", 1)[1]})
                elif route.path == "/api/v1/events" and not set(query) - {"after", "timeout_ms"}:
                    try:
                        args = {name: int(values[0]) for name, values in query.items() if len(values) == 1}
                        if len(args) != len(query):
                            raise ValueError
                    except ValueError:
                        raise TesterError("validation", "Invalid event cursor or timeout.") from None
                    result = self.server.dispatcher.execute("events", args)
                else:
                    raise TesterError("not_found", "Unknown endpoint or query.")
                code, response = 200, result_envelope(None, result)
        except TesterError as error:
            code, response = HTTP_CODES.get(error.code, 500), result_envelope(request_id, error=error)
        except (OSError, ValueError):
            code, response = 400, result_envelope(request_id, error=TesterError("validation", "Invalid request."))
        self._reply(code, response)

    def do_GET(self):
        self._handle()

    def do_POST(self):
        self._handle(post=True)


class RemoteClient:
    def __init__(self, address):
        parsed = urlparse(address)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
                or parsed.path not in ("", "/") or parsed.username or parsed.password
                or parsed.query or parsed.fragment):
            raise TesterError("validation", "Server must be http://127.0.0.1:<port>.")
        self.address = address.rstrip("/")

    def execute(self, action, args=None):
        payload = {"id": uuid.uuid4().hex, "action": action, "args": args or {}}
        request = Request(self.address + "/api/v1/commands", json.dumps(payload).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        try:
            try:
                response = urlopen(request, timeout=35)
            except HTTPError as error:
                response = error
            with response:
                data = json.load(response)
        except (URLError, OSError, ValueError) as error:
            raise TesterError("connection", f"Local API unavailable: {error}", "unknown") from None
        if not data["ok"]:
            error = data["error"]
            raise TesterError(error["code"], error["message"], error["outcome"])
        return data["result"]


def run_shell(dispatcher, json_output=False):
    failed = False
    while True:
        try:
            if sys.stdin.isatty():
                print("tester> ", end="", file=sys.stderr, flush=True)
            command = input()
        except EOFError:
            break
        if not command.strip():
            continue
        request_id = uuid.uuid4().hex
        try:
            action, args = parse_cli(command)
            if action == "exit":
                break
            if action == "vin.all":
                result = [dispatcher.execute("vin.read", {"channel": channel}) for channel in range(1, 5)]
            elif isinstance(dispatcher, RemoteClient) and action == "operation.wait":
                deadline = time.monotonic() + integer(args["timeout_ms"], "timeout_ms", 0, 3700000) / 1000
                while True:
                    result = dispatcher.execute("operation.get", {"operation_id": args["operation_id"]})
                    if result["status"] not in ("accepted", "running"):
                        break
                    if time.monotonic() >= deadline:
                        raise TesterError("timeout", "Wait expired; operation may still run.", "unknown")
                    threading.Event().wait(0.1)
            else:
                result = dispatcher.execute(action, args)
            envelope = result_envelope(request_id, result)
            print(json.dumps(envelope if json_output else result, allow_nan=False))
        except TesterError as error:
            failed = True
            if json_output:
                print(json.dumps(result_envelope(request_id, error=error)))
            else:
                print(f"ERROR {error.code}: {error}", file=sys.stderr)
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="mode", required=True)
    shell = subparsers.add_parser("shell", help="Persistent CLI, direct serial or remote local API")
    server = subparsers.add_parser("serve", help="Loopback HTTP server, one serial owner")
    for subparser in (shell, server):
        subparser.add_argument("--port", help="Tester COM port; connection resets outputs OFF")
        subparser.add_argument("--baudrate", type=int, default=115200)
        subparser.add_argument("--line-ending", choices=("LF", "CRLF", "CR"), default="LF")
    shell.add_argument("--server", help="Use an existing local HTTP service instead of opening COM")
    shell.add_argument("--json", action="store_true", help="Newline JSON results on stdout")
    server.add_argument("--http-port", type=int, default=8765)
    args = parser.parse_args(argv)
    if args.mode == "shell" and args.server and args.port:
        parser.error("--server and --port are mutually exclusive")
    client = TesterClient()
    http_server = None
    code = 0
    try:
        if args.mode == "shell" and args.server:
            return run_shell(RemoteClient(args.server), args.json)
        if args.port:
            client.connect(args.port, args.baudrate, args.line_ending)
        if args.mode == "shell":
            code = run_shell(CommandDispatcher(client), args.json)
        else:
            http_server = TesterHttpServer(client, args.http_port)
            print(f"Local tester API: http://127.0.0.1:{http_server.server_port}/api/v1/status", file=sys.stderr)
            http_server.serve_forever(poll_interval=0.1)
    except KeyboardInterrupt:
        pass
    except TesterError as error:
        print(f"ERROR {error.code}: {error}", file=sys.stderr)
        code = {"validation": 2, "connection": 3, "dependency": 3, "timeout": 4,
                "firmware": 5, "conflict": 6, "unsupported": 7, "unsafe": 8}.get(error.code, 1)
    except OSError as error:
        print(f"ERROR service: {error}", file=sys.stderr)
        code = 3
    finally:
        if http_server:
            http_server.server_close()
        try:
            client.disconnect()
        except TesterError as error:
            print(f"WARNING shutdown: {error}", file=sys.stderr)
            code = 8
    return code


if __name__ == "__main__":
    raise SystemExit(main())