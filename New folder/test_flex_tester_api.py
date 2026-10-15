"""Isolated tests. No physical serial ports are opened."""

import subprocess
import sys
import queue
import threading
import json
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from FlexTesterApi import (CommandDispatcher, RemoteClient, ScalingConfig, TesterClient,
                          TesterError, TesterHttpServer, parse_cli, parse_supply_status,
                          parse_vin, parse_wm_status)


class CoreTests(unittest.TestCase):
    def test_scaling(self):
        scaling = ScalingConfig(x2=10000)
        self.assertEqual(scaling.to_mv(50), {"mv": 5000, "warning": None})
        self.assertEqual(scaling.from_mv(5000), 50)
        self.assertIsNotNone(scaling.to_mv(110)["warning"])
        self.assertEqual(ScalingConfig(10000, 0, 0, 100).to_mv(50)["mv"], 5000)
        self.assertEqual(scaling.to_mv(0)["mv"], 0)
        self.assertEqual(scaling.to_mv(150)["mv"], 15000)

    def test_bad_scaling(self):
        for value in (float("nan"), float("inf"), -1, 151, True, "50"):
            with self.assertRaises(TesterError):
                ScalingConfig(x2=10000).to_mv(value)
        with self.assertRaises(TesterError):
            ScalingConfig(y1=1, y2=1)
        with self.assertRaises(TesterError):
            ScalingConfig(x1=1, x2=1).from_mv(100)

    def test_status(self):
        status = parse_wm_status("wm status wm 1 stopped 1000ms wm 2 manual on 1000ms"
                                 " wm 3 started 1000ms wm 4 triggered 1000ms")
        self.assertEqual(status[2]["state"], "manual on")
        with self.assertRaises(TesterError):
            parse_wm_status("wm status wm 1 stopped 1000ms")
        supply = parse_supply_status("vsen en=0 mv=0 ccr4=0 duty=0.00% pwm=run"
                                     " vai1=off vai2=off vai3=off vai4=off cal=off")
        self.assertFalse(supply["enabled"])
        self.assertEqual(supply["rails"], {1: "off", 2: "off", 3: "off", 4: "off"})

    def test_vin(self):
        self.assertEqual(parse_vin("ain 1 raw=2032 mv=5000")["mv"], 5000)
        self.assertFalse(parse_vin("ain 4 raw=4095 mv=10076")["valid"])
        with self.assertRaises(TesterError):
            parse_vin("ain 1 raw=4095 mv=13300")

    def test_import_has_no_gui_or_serial_side_effects(self):
        snippet = ("import sys, threading; before = set(threading.enumerate()); "
                   "import FlexTesterApi; "
                   "assert set(threading.enumerate()) == before; "
                   "assert not any(name in sys.modules for name in "
                   "('tkinter', 'matplotlib', 'serial'))")
        subprocess.run([sys.executable, "-c", snippet], check=True, cwd=Path(__file__).parent)


class FakeSerial:
    def __init__(self, **kwargs):
        self.incoming = queue.Queue()
        self.closed = False
        self.commands = []
        self.wm = {channel: ["stopped", 1000] for channel in range(1, 5)}
        self.mv = 0
        self.enabled = False
        self.rails = {channel: "off" for channel in range(1, 5)}
        self.pulse = None
        self.silent = set()
        self.reject = set()
        self.vin = {channel: (0, 0) for channel in range(1, 5)}

    def emit(self, *lines):
        for line in lines:
            for value in (line + "\r\n").encode():
                self.incoming.put(bytes([value]))

    def read(self, count):
        try:
            value = self.incoming.get(timeout=0.02)
            if isinstance(value, Exception):
                raise value
            return value
        except queue.Empty:
            return b""

    def status(self):
        return "wm status" + "".join(f" wm {channel} {state} {cycle}ms"
                                    for channel, (state, cycle) in self.wm.items())

    def supply(self):
        return (f"vsen en={int(self.enabled)} mv={self.mv} ccr4=0 duty=0.00% pwm=run"
                + "".join(f" vai{channel}={state}" for channel, state in self.rails.items())
                + " cal=off")

    def all_off(self):
        self.enabled = False
        self.rails = {channel: "off" for channel in range(1, 5)}
        self.pulse = None

    def complete(self):
        channel = self.pulse
        self.all_off()
        self.emit(f"vai {channel} OFF pulse complete", self.supply())

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        self.emit(command)
        if command in self.silent:
            return len(data)
        if command in self.reject:
            self.emit("ERROR " + command)
            return len(data)
        parts = command.split()
        if command == "get status":
            self.emit(self.status())
        elif command == "get vsen":
            self.emit(self.supply())
        elif parts[:2] == ["get", "ain"]:
            raw, mv = self.vin[int(parts[2])]
            self.emit(f"ain {parts[2]} raw={raw} mv={mv}")
        elif parts[:2] in (["stop", "wm"], ["start", "wm"], ["toggle", "wm"]):
            channel = int(parts[2])
            if parts[0] == "stop":
                self.wm[channel][0] = "stopped"
            elif parts[0] == "start":
                self.wm[channel] = ["started", int(parts[3])]
            else:
                self.wm[channel][0] = "stopped" if self.wm[channel][0] == "manual on" else "manual on"
            response = "manual off" if parts[0] == "toggle" and self.wm[channel][0] == "stopped" else self.wm[channel][0]
            self.emit(f"wm {channel} {response}")
        elif parts[:2] == ["set", "vsen"]:
            self.mv = int(parts[2])
            if not self.mv:
                self.all_off()
            self.emit(f"vsen set to {self.mv} mV")
        elif parts[:2] == ["set", "vsen_en"]:
            self.enabled = parts[2] == "on" and self.mv != 0
            self.emit(f"vsen_en ON, {self.mv} mV" if self.enabled else "vsen_en OFF")
        elif parts[:2] == ["set", "vai"]:
            channel = int(parts[2])
            self.rails[channel] = "on" if parts[3] == "on" else "off"
            self.emit(f"vai {channel} {parts[3].upper()}")
        elif parts[:2] == ["pulse", "vai"]:
            channel, self.mv, duration = map(int, parts[2:])
            self.all_off()
            self.enabled = bool(self.mv)
            self.rails[channel] = "on" if self.mv else "off"
            self.pulse = channel
            self.emit(f"vai {channel} {'ON' if self.mv else 'OFF'} pulse_ms={duration}", self.supply())
        elif parts[:2] == ["stop", "vai"]:
            self.all_off()
            self.emit(f"vai {parts[2]} OFF pulse cancelled", self.supply())
        elif command == "get time":
            self.emit("sys time 12:34:0")
        elif command.startswith("set time") or command == "system init":
            self.emit("OK")
        elif command == "help":
            self.emit("Available Commands:", " get status", "OK")
        else:
            self.emit("ERROR " + command)
        return len(data)

    def close(self):
        self.closed = True


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.serial = FakeSerial()
        self.client = TesterClient(serial_factory=lambda **kwargs: self.serial, timeout=0.15)
        self.client.connect("FAKE")

    def tearDown(self):
        try:
            self.client.disconnect()
        except TesterError:
            pass

    def test_connect_and_disconnect_safe(self):
        self.assertEqual(self.serial.commands[:2], ["get status", "stop wm 1"])
        self.assertIn("set vsen 0", self.serial.commands)
        self.client.set_wm_output(1, True)
        self.client.disconnect()
        self.assertEqual(self.serial.wm[1][0], "stopped")
        self.assertTrue(self.serial.closed)
        self.assertFalse(self.client._transport)

    def test_wm_idempotent_and_conflicts(self):
        self.client.set_wm_output(1, True)
        self.assertFalse(self.client.set_wm_output(1, True)["changed"])
        self.assertEqual(self.serial.commands.count("toggle wm 1"), 1)
        self.client.start_wm(1, 1000)
        with self.assertRaises(TesterError) as caught:
            self.client.set_wm_output(1, True)
        self.assertEqual(caught.exception.code, "conflict")
        self.client.stop_wm(1)
        for channel, period in ((5, 1000), (1, 0), (1, 0.5), (1, float("inf"))):
            with self.assertRaises(TesterError):
                self.client.start_wm(channel, period)

    def test_configuration_does_not_send_commands(self):
        count = len(self.serial.commands)
        self.client.set_scaling(1, 0, 10000, 0, 100)
        self.client.set_scaling_mode(1, "automatic")
        self.assertEqual(self.client.set_engineering_value(1, 50)["mv"], 5000)
        self.assertEqual(len(self.serial.commands), count)
        result = self.client.sensor_on(1)
        self.assertEqual(result["mv"], 5000)
        with self.assertRaises(TesterError):
            self.client.sensor_on(2)
        self.client.sensor_off(1)
        self.assertFalse(self.serial.enabled)

    def test_failed_sensor_sequence_cleanup(self):
        self.serial.reject.add("set vai 1 on")
        with self.assertRaises(TesterError):
            self.client.sensor_on(1)
        self.assertFalse(self.serial.enabled)
        self.assertEqual(self.serial.mv, 0)

    def test_pulse_completion_and_cancel(self):
        operation = self.client.pulse_sensor(1, 5000, 2000)
        self.assertEqual(operation["status"], "running")
        with self.assertRaises(TesterError):
            self.client.pulse_sensor(2, 5000, 100)
        self.serial.complete()
        result = self.client.wait_operation(operation["id"], 500)
        self.assertEqual(result["status"], "completed")
        operation = self.client.pulse_sensor(2, 0, 2000)
        self.assertFalse(self.serial.enabled)
        self.client.stop_sensor(2)
        self.assertEqual(self.client.get_operation(operation["id"])["status"], "cancelled")

    def test_timeout_echo_not_ack_and_no_retry(self):
        self.serial.silent.add("toggle wm 1")
        with self.assertRaises(TesterError) as caught:
            self.client.set_wm_output(1, True)
        self.assertEqual(caught.exception.outcome, "unknown")
        self.assertEqual(self.client.get_status()["connection"], "fault")
        self.assertEqual(self.serial.commands.count("toggle wm 1"), 1)
        self.serial.emit("wm 1 manual on")
        with self.assertRaises(TesterError):
            self.client.set_wm_output(1, True)

    def test_concurrent_wm_on(self):
        errors = []
        def activate():
            try:
                self.client.set_wm_output(1, True)
            except Exception as error:
                errors.append(error)
        threads = [threading.Thread(target=activate) for unused in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(self.serial.commands.count("toggle wm 1"), 1)

    def test_time_help(self):
        self.assertEqual(self.client.get_time()["time"], "12:34:0")
        self.client.set_time("14:30")
        self.client.get_help()
        with self.assertRaises(TesterError):
            self.client.set_time("25:99")

    def test_serial_loss_marks_outputs_unknown(self):
        self.serial.incoming.put(OSError("Cable removed"))
        with self.assertRaises(TesterError):
            self.client.get_time()
        self.assertFalse(self.client.get_status()["outputs_known"])
        with self.assertRaises(TesterError) as caught:
            self.client.disconnect()
        self.assertEqual(caught.exception.code, "unsafe")
        self.assertTrue(self.serial.closed)

    def test_status_snapshots_are_independent(self):
        status = self.client.get_status()
        status["supply"]["enabled"] = True
        self.assertFalse(self.client.get_status()["supply"]["enabled"])
        events = self.client.get_events()
        events["events"][0]["line"] = "changed"
        self.assertNotEqual(self.client.get_events()["events"][0].get("line"), "changed")

    def test_failed_handshake_closes_without_claiming_safe(self):
        serial = FakeSerial()
        serial.reject.add("get status")
        client = TesterClient(serial_factory=lambda **kwargs: serial, timeout=0.15)
        with self.assertRaises(TesterError):
            client.connect("WRONG_DEVICE")
        self.assertTrue(serial.closed)
        self.assertIsNone(client.disconnect()["safe_off"])

    def test_event_history_is_bounded_and_reports_gap(self):
        for index in range(2100):
            self.client._event("test", index=index)
        result = self.client.get_events()
        self.assertTrue(result["gap"])
        self.assertEqual(len(result["events"]), 2048)


class AutoTests(unittest.TestCase):
    def setUp(self):
        ClientTests.setUp(self)
        self.client._stop_background.set()
        self.client._background.join()
        self.now = 10.0
        self.client._clock = lambda: self.now
        self.client._sampling.clear()
        self.client._next_poll = 0

    def tearDown(self):
        ClientTests.tearDown(self)

    def service(self):
        with self.client._lock:
            self.client._service()

    def test_vin_read_and_poll_selection(self):
        self.serial.vin[1] = (2032, 5000)
        sample = self.client.read_vin(1)
        self.assertEqual(sample["mv"], 5000)
        self.client.configure_sampling([1, 2], True)
        count = len(self.serial.commands)
        self.service()
        self.service()
        self.now += 0.25
        self.service()
        self.assertEqual(self.serial.commands[count:], ["get ain 1", "get ain 2"])

    def test_threshold_saturation_and_fifo(self):
        self.client.configure_auto(1, True)
        self.client.configure_auto(2, True)
        self.serial.vin[1] = (406, 1000)
        self.client.read_vin(1)
        self.client._dispatch_auto()
        self.assertIsNone(self.serial.pulse)
        self.serial.vin[1] = (4095, 10076)
        self.client.read_vin(1)
        self.client._dispatch_auto()
        self.assertIsNone(self.serial.pulse)
        self.serial.vin[1] = (500, 1230)
        self.serial.vin[2] = (600, 1476)
        self.client.read_vin(2)
        self.client.read_vin(1)
        self.client._dispatch_auto()
        self.assertEqual(self.serial.pulse, 2)
        with self.assertRaises(TesterError):
            self.client.sensor_on(1)
        with self.assertRaises(TesterError):
            self.client.set_voltage(1, 3000)
        self.serial.complete()
        self.client.get_time()
        self.client._next_poll = self.now + 1
        self.service()
        self.assertEqual(self.serial.pulse, 1)

    def test_stale_and_fresh_retrigger(self):
        self.client.configure_auto(1, True)
        self.serial.vin[1] = (500, 1230)
        self.client.read_vin(1)
        self.now += 2.01
        self.client._dispatch_auto()
        self.assertIsNone(self.serial.pulse)
        self.client.read_vin(1)
        self.client._dispatch_auto()
        operation_id = self.client._active["id"]
        self.serial.complete()
        self.client.get_time()
        self.client._next_poll = self.now + 10
        self.service()
        self.assertIsNone(self.serial.pulse)
        self.assertEqual(self.client.get_operation(operation_id)["status"], "completed")
        self.client.read_vin(1)
        self.client._dispatch_auto()
        self.assertEqual(self.serial.pulse, 1)
        self.client.configure_auto(1, False)
        self.assertIsNone(self.serial.pulse)
        self.assertFalse(self.client._auto)

    def test_auto_forces_sampling_and_error_disarms(self):
        self.client.configure_auto(3, True)
        self.client.configure_sampling([1, 2, 3, 4], False)
        self.service()
        self.assertEqual(self.serial.commands[-1], "get ain 3")
        self.serial.reject.add("get ain 3")
        with self.assertRaises(TesterError):
            self.client.read_vin(3)
        self.assertFalse(self.client._auto)
        self.assertFalse(self.serial.enabled)

    def test_reset_invalidates_and_never_rearms(self):
        self.client.configure_auto(1, True)
        self.serial.emit("App Started", "ADC init=ready configured_vref=2500mV")
        with self.assertRaises(TesterError):
            self.client.get_status(refresh=True)
        self.assertEqual(self.client.get_status()["connection"], "fault")
        self.assertFalse(self.client._auto)

    def test_missing_completion_forces_sensor_off(self):
        operation = self.client.pulse_sensor(1, 5000, 100)
        self.now += 1
        with self.assertRaises(TesterError) as caught:
            self.service()
        self.assertEqual(caught.exception.code, "timeout")
        self.assertFalse(self.serial.enabled)
        self.assertEqual(self.serial.mv, 0)
        self.assertEqual(self.client.get_operation(operation["id"])["status"], "failed")


class CliTests(unittest.TestCase):
    def test_grammar(self):
        self.assertEqual(parse_cli("on wm1"), ("wm.on", {"channel": 1}))
        self.assertEqual(parse_cli("START WM1 CYCLE_MS 1000"), ("wm.start", {"channel": 1, "cycle_ms": 1000}))
        self.assertEqual(parse_cli("SCALE VAI1 X1 0 X2 10000 Y1 0 Y2 100")[1]["x2"], 10000)
        self.assertEqual(parse_cli("AUTO VAI2 ON DURATION_MS 5000")[1]["duration_ms"], 5000)
        self.assertEqual(parse_cli("SAMPLE AI1 AI3 ON")[1]["channels"], [1, 3])
        for text in ("ON WM5", "ON WM1 garbage", "SAMPLE AI5 ON", "SET VAI1 MV nan", 'CONNECT "'):
            with self.assertRaises(TesterError):
                parse_cli(text)

    def test_shell_subprocess_no_hardware(self):
        process = subprocess.run([sys.executable, "FlexTesterApi.py", "shell", "--json"],
                                 input="HELP\nCAPABILITIES\nSTATUS\nEXIT\n", text=True,
                                 capture_output=True, cwd=Path(__file__).parent, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        results = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(results), 3)
        self.assertEqual(results[-1]["result"]["connection"], "disconnected")


class HttpTests(unittest.TestCase):
    def setUp(self):
        ClientTests.setUp(self)
        self.server = TesterHttpServer(self.client, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01})
        self.thread.start()
        self.address = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        ClientTests.tearDown(self)

    def request(self, path="/api/v1/commands", payload=None, headers=None, raw=None):
        data = raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
        request = Request(self.address + path, data, headers=headers or {"Content-Type": "application/json"})
        try:
            response = urlopen(request, timeout=5)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_commands_duplicate_id_and_conflict(self):
        payload = {"id": "on-1", "action": "wm.on", "args": {"channel": 1}}
        self.assertEqual(self.request(payload=payload)[0], 200)
        self.assertEqual(self.request(payload=payload)[0], 200)
        self.assertEqual(self.serial.commands.count("toggle wm 1"), 1)
        payload["args"]["channel"] = 2
        self.assertEqual(self.request(payload=payload)[0], 409)
        payload = {"id": "bad", "action": "wm.on", "args": {"channel": 5}}
        self.assertEqual(self.request(payload=payload)[0], 400)

    def test_pulse_accepted_and_completed(self):
        code, body = self.request(payload={"id": "pulse", "action": "sensor.pulse",
                                          "args": {"channel": 1, "mv": 5000, "duration_ms": 2000}})
        self.assertEqual(code, 202)
        operation_id = body["result"]["id"]
        self.serial.complete()
        self.client.wait_operation(operation_id, 1000)
        code, body = self.request("/api/v1/operations/" + operation_id)
        self.assertEqual(code, 200)
        self.assertEqual(body["result"]["status"], "completed")

    def test_validation_and_loopback(self):
        self.assertEqual(self.request(payload={"id": "x", "action": "wm.on", "args": {"channel": 1, "oops": 1}})[0], 400)
        self.assertEqual(self.request(raw=b"{")[0], 400)
        self.assertEqual(self.request(raw=b'{"id":"x","action":"wm.start","args":{"cycle_ms":NaN}}')[0], 400)
        self.assertEqual(self.request(payload={}, headers={"Content-Type": "text/plain"})[0], 400)
        self.assertEqual(self.request("/api/v1/status", headers={"Host": "evil.example"})[0], 403)
        self.assertEqual(self.request("/api/v1/status", headers={"Origin": "http://evil.example"})[0], 403)
        self.assertEqual(self.request("/api/v1/unknown")[0], 404)

    def test_remote_cli_and_events(self):
        remote = RemoteClient(self.address)
        remote.execute(*parse_cli("ON WM2"))
        self.assertEqual(self.serial.wm[2][0], "manual on")
        self.assertEqual(self.request("/api/v1/status")[1]["result"]["connection"], "ready")
        events = self.request("/api/v1/events?after=0")[1]["result"]["events"]
        self.assertTrue(any(event["type"] == "connected" for event in events))
        with self.assertRaises(TesterError):
            RemoteClient("http://example.com:8765")

    def test_channel_batch_combines_vai_and_wm(self):
        payload = {"RequestId": "combined", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Operation_Mode": "Manual",
             "Manual_voltage": 5000, "X1": None, "X2": None, "Y1": None, "Y2": None,
             "Output_Value": None, "Cycle_ms": None, "Duration_ms": None},
            {"Port": "VAI", "PortNum": 1, "Action": "On", "Manual_voltage": None},
            {"Port": "WM", "PortNum": 1, "Action": "Start", "Cycle_ms": 1000}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 200, body)
        self.assertEqual(body["id"], "combined")
        self.assertEqual(len(body["result"]["commands"]), 3)
        self.assertTrue(body["ok"])
        self.assertTrue(self.serial.enabled)
        self.assertEqual(self.serial.rails[1], "on")
        self.assertEqual(self.serial.wm[1][0], "started")
        self.assertLess(self.serial.commands.index("set vai 1 on"), self.serial.commands.index("start wm 1 1000"))
        self.assertEqual(self.request(payload=payload)[0], 200)
        self.assertEqual(self.serial.commands.count("start wm 1 1000"), 1)

    def test_channel_batch_prevalidates_every_command(self):
        self.client.configure_sampling([1, 2, 3, 4], False)
        before = len(self.serial.commands)
        payload = {"RequestId": "invalid-batch", "Commands": [
            {"Port": "WM", "PortNum": 1, "Action": "On"},
            {"Port": "VAI", "PortNum": 1, "Action": "On", "Manual_voltage": 5000}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 400, body)
        self.assertIn("Commands[1]", body["error"]["message"])
        self.assertEqual(len(self.serial.commands), before)
        self.assertEqual(self.serial.wm[1][0], "stopped")

    def test_channel_batch_conflict_stops_remaining_and_cleans_up(self):
        payload = {"RequestId": "conflicting-batch", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "On"},
            {"Port": "VAI", "PortNum": 2, "Action": "On"},
            {"Port": "WM", "PortNum": 1, "Action": "Start"}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 409, body)
        self.assertFalse(body["ok"])
        self.assertEqual([entry["status"] for entry in body["result"]["commands"]],
                         ["completed", "failed", "skipped"])
        self.assertTrue(body["result"]["cleanup"]["verified"])
        self.assertFalse(self.serial.enabled)
        self.assertNotIn("start wm 1 1000", self.serial.commands)

    def test_channel_batch_example_file(self):
        path = Path(__file__).with_name("FlexTesterApi.examples.json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        code, body = self.request(payload=payload)
        self.assertEqual(code, 200, body)
        self.assertEqual(self.client.get_status()["auto"][1]["mv"], 5000)
        self.assertEqual(self.client.get_status()["auto"][1]["duration_ms"], 5000)
        self.assertFalse(self.serial.enabled)
        self.assertEqual(self.serial.wm[1], ["started", 1000])

    def test_channel_batch_atomic_config_and_null_preservation(self):
        original_mv = self.client.get_status()["config"][1]["mv"]
        payload = {"RequestId": "scale-batch", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "X1": 0, "X2": 10000,
             "Y1": 100, "Y2": 200, "Operation_Mode": "Automatic", "Output_Value": 150},
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "X1": None, "Manual_voltage": None},
            {"Port": "VAI", "PortNum": 1, "Action": "On"},
            {"Port": "AI", "PortNum": 1, "Action": "Read"}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 200, body)
        result = body["result"]["commands"]
        self.assertEqual(result[0]["result"]["resolved_mv"], 5000)
        self.assertEqual(result[1]["result"]["value"], 150)
        self.assertEqual(result[1]["result"]["mv"], original_mv)
        self.assertEqual(result[3]["result"]["channel"], 1)
        self.assertEqual(self.serial.mv, 5000)

    def test_channel_batch_pulse_is_accepted_without_blocking(self):
        payload = {"RequestId": "batch-pulse", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Pulse", "Manual_voltage": None, "Duration_ms": 2000},
            {"Port": "WM", "PortNum": 2, "Action": "Start", "Cycle_ms": None}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 202, body)
        self.assertEqual(body["status"], "running")
        operation_id = body["result"]["commands"][0]["result"]["id"]
        self.assertEqual(self.serial.wm[2][0], "started")
        self.serial.complete()
        self.assertEqual(self.client.wait_operation(operation_id, 1000)["status"], "completed")

    def test_channel_batch_normalizes_integer_valued_floats(self):
        payload = {"RequestId": "normalized", "Commands": [
            {"Port": "VAI", "PortNum": 1.0, "Action": "Configure", "Manual_voltage": 5000.0},
            {"Port": "VAI", "PortNum": 1.0, "Action": "On"},
            {"Port": "WM", "PortNum": 2.0, "Action": "Start", "Cycle_ms": 1000.0}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 200, body)
        self.assertIn("set vsen 5000", self.serial.commands)
        self.assertIn("start wm 2 1000", self.serial.commands)
        self.assertFalse(any(".0" in command for command in self.serial.commands))

    def test_channel_batch_invalid_shapes_and_fields_have_no_side_effects(self):
        self.client.configure_sampling([1, 2, 3, 4], False)
        invalid_commands = [None, [], [{}] * 33,
            [{"Port": "DI", "PortNum": 1, "Action": "Start"}],
            [{"Port": "WM", "PortNum": True, "Action": "Start"}],
            [{"Port": "WM", "PortNum": 5, "Action": "Start"}],
            [{"Port": "WM", "PortNum": 1, "Action": "On", "Cycle_ms": 1000}],
            [{"Port": "AI", "PortNum": 1, "Action": "On"}],
            [{"Port": "VAI", "PortNum": 1, "Action": "Pulse", "Duration_ms": None}],
            [{"Port": "VAI", "PortNum": 1, "Action": "Configure", "Y1": 0, "Y2": 0}],
            [{"Port": "VAI", "PortNum": 1, "Action": "Configure", "Manual_voltage": 5000,
              "Operation_Mode": "Automatic"}],
            [{"Port": "WM", "PortNum": 1, "Action": "Start", "State": None}]]
        before = len(self.serial.commands)
        for index, commands in enumerate(invalid_commands):
            with self.subTest(commands=commands):
                code, body = self.request(payload={"RequestId": f"invalid-{index}", "Commands": commands})
                self.assertEqual(code, 400, body)
                self.assertEqual(len(self.serial.commands), before)
        code, body = self.request(payload={"RequestId": "trigger", "Commands": [
            {"Port": "WM", "PortNum": 1, "Action": "Trigger"}]})
        self.assertEqual(code, 422, body)
        self.assertEqual(len(self.serial.commands), before)

    def test_channel_batch_timeout_reports_unsafe_cleanup(self):
        self.serial.silent.add("toggle wm 1")
        payload = {"RequestId": "batch-timeout", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "On"},
            {"Port": "WM", "PortNum": 1, "Action": "On"},
            {"Port": "WM", "PortNum": 2, "Action": "On"}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 503, body)
        self.assertEqual(body["error"]["code"], "unsafe")
        self.assertEqual(body["status"], "unknown")
        self.assertFalse(body["result"]["cleanup"]["verified"])
        self.assertEqual(body["result"]["commands"][1]["error"]["code"], "timeout")
        self.assertEqual(body["result"]["commands"][2]["status"], "skipped")
        self.assertEqual(self.serial.commands.count("toggle wm 1"), 1)

    def test_channel_batch_duplicate_id_conflict(self):
        payload = {"RequestId": "reuse-batch", "Commands": [
            {"Port": "WM", "PortNum": 1, "Action": "On"}]}
        self.assertEqual(self.request(payload=payload)[0], 200)
        payload["Commands"][0]["PortNum"] = 2
        self.assertEqual(self.request(payload=payload)[0], 409)
        self.assertNotIn("toggle wm 2", self.serial.commands)

    def test_channel_batch_auto_enable_disable_and_null(self):
        payload = {"RequestId": "auto-arm", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": True,
             "Operation_Mode": "Automatic", "X1": 0, "X2": 10000, "Y1": 0, "Y2": 100,
             "Output_Value": 50, "Duration_ms": 250},
            {"Port": "WM", "PortNum": 1, "Action": "Start", "Auto_Enabled": None}]}
        code, body = self.request(payload=payload)
        self.assertEqual(code, 200, body)
        self.assertTrue(body["result"]["commands"][0]["result"]["Auto_Enabled"])
        self.assertEqual(self.client.get_status()["auto"][1]["mv"], 5000)
        self.assertEqual(self.client.get_status()["auto"][1]["duration_ms"], 250)
        self.assertFalse(self.serial.enabled)
        self.assertEqual(self.serial.wm[1][0], "started")
        for identifier, value in (("auto-null", None), ("auto-same", True)):
            code, body = self.request(payload={"RequestId": identifier, "Commands": [
                {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": value}]})
            self.assertEqual(code, 200, body)
            self.assertEqual(self.client.get_status()["auto"][1]["duration_ms"], 250)
        code, body = self.request(payload={"RequestId": "auto-disarm", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": False}]})
        self.assertEqual(code, 200, body)
        self.assertFalse(body["result"]["commands"][0]["result"]["Auto_Enabled"])
        self.assertFalse(self.client.get_status()["auto"])

    def test_channel_batch_auto_input_validation(self):
        self.client.configure_sampling([1, 2, 3, 4], False)
        before = len(self.serial.commands)
        invalid = [
            {"Auto_Enabled": "true"}, {"Auto_Enabled": 1},
            {"Auto_Enabled": True, "Duration_ms": 9},
            {"Auto_Enabled": False, "Duration_ms": 100},
            {"Auto_Enabled": None, "Duration_ms": 100}]
        for index, values in enumerate(invalid):
            code, body = self.request(payload={"RequestId": f"bad-auto-{index}", "Commands": [
                {"Port": "WM", "PortNum": 1, "Action": "On"},
                {"Port": "VAI", "PortNum": 1, "Action": "Configure", **values}]})
            self.assertEqual(code, 400, body)
            self.assertEqual(len(self.serial.commands), before)
        for index, port in enumerate(("WM", "AI")):
            code, body = self.request(payload={"RequestId": f"wrong-auto-port-{index}", "Commands": [
                {"Port": port, "PortNum": 1, "Action": "Start" if port == "WM" else "Read", "Auto_Enabled": False}]})
            self.assertEqual(code, 400, body)
            self.assertEqual(len(self.serial.commands), before)

    def test_channel_batch_auto_threshold_cancel_and_manual_transition(self):
        self.client._stop_background.set()
        self.client._background.join()
        code, body = self.request(payload={"RequestId": "threshold-arm", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": True},
            {"Port": "WM", "PortNum": 1, "Action": "Start"}]})
        self.assertEqual(code, 200, body)
        self.assertEqual(self.client.get_status()["auto"][1]["duration_ms"], 5000)
        self.serial.vin[1] = (406, 1000)
        self.client.read_vin(1)
        with self.client._lock:
            self.client._dispatch_auto()
        self.assertIsNone(self.serial.pulse)
        self.serial.vin[1] = (500, 1230)
        self.client.read_vin(1)
        with self.client._lock:
            self.client._dispatch_auto()
        operation_id = self.client._active["id"]
        self.assertEqual(self.serial.pulse, 1)
        code, body = self.request(payload={"RequestId": "switch-to-manual", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure", "Auto_Enabled": False,
             "Operation_Mode": "Manual", "Manual_voltage": 3000},
            {"Port": "VAI", "PortNum": 1, "Action": "On"}]})
        self.assertEqual(code, 200, body)
        self.assertFalse(self.client.get_status()["auto"])
        self.assertEqual(self.client.get_operation(operation_id)["status"], "cancelled")
        self.assertEqual(self.serial.mv, 3000)
        self.assertTrue(self.serial.enabled)
        self.assertEqual(self.serial.wm[1][0], "started")

    def test_channel_batch_auto_duration_change_requires_disarm(self):
        self.client.configure_auto(1, True, 250)
        code, body = self.request(payload={"RequestId": "invalid-duration-change", "Commands": [
            {"Port": "VAI", "PortNum": 1, "Action": "Configure",
             "Auto_Enabled": True, "Duration_ms": 500}]})
        self.assertEqual(code, 409, body)
        self.assertEqual(body["error"]["code"], "conflict")
        self.assertTrue(body["result"]["cleanup"]["verified"])
        self.assertFalse(self.client.get_status()["auto"])


if __name__ == "__main__":
    unittest.main()