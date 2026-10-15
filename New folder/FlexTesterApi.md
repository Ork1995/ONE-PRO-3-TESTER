# Flex Tester Headless API

Independent Python library, persistent CLI and local HTTP/JSON service for the
Main Controller. The existing GUI and firmware are not modified or imported.
The GUI must release the tester's COM port before this tool connects.

## Implementation Status

Documentation baseline: 15 October 2026, based on inspection of
[FlexTesterApi.py](FlexTesterApi.py) and
[test_flex_tester_api.py](test_flex_tester_api.py).

The tool is implemented, not merely planned. It includes the serial transport,
Python client, persistent direct CLI, loopback HTTP service and remote CLI.
It is not physically hardware-qualified or certified for production use.
Known defects are documented in [Known Defects](#known-defects).

All output examples in this manual are illustrative, code-compatible examples,
not physical tester captures. Port identifiers, timestamps, operation IDs,
monotonic times and measured values will vary. The last recorded automated
run passed 43 tests against fake serial; see [Test Record](#test-record).

### Project Layout And Exact Paths

```text
ONE PRO 3 TESTER/
  Application/                    Existing tester firmware; unchanged
  Core/                           Existing board configuration; unchanged
  Drivers/                        Existing embedded drivers; unchanged
  Middlewares/                    Existing firmware dependencies; unchanged
  New folder/
    FlexTesterApi.py               Required runtime entry point and Python API
    FlexTesterApi.md               This user manual; optional at runtime
    test_flex_tester_api.py        Isolated automated tests; optional at runtime
    FlexTesterGui.py               Existing GUI; not imported or required
    FLEX_LOGS/                    Existing GUI logs; not required
    __pycache__/                  Optional Python-generated cache
```

The existing firmware project contains additional configuration and build
files, which are omitted from this runtime-focused layout. No separate API
package, server script, requirements file, database or configuration file is
required. The runtime script is self-contained apart from pyserial.

On the development workstation, the repository root is:

```text
C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER
```

The exact runtime script path is:

```text
C:\Users\o29373\OneDrive - Netafim\Desktop\Netafim Projects\ONE PRO 3 TESTER\New folder\FlexTesterApi.py
```

The documentation and test files are in that same directory, named
`FlexTesterApi.md` and `test_flex_tester_api.py`. Use the tester repository,
not the adjacent `Netafim_Flex_Lite` repository. Quote paths containing spaces.

## Safety First

- CONNECT reads the tester's WM status, stops WM1..WM4, sends `set vsen 0`,
  and verifies that every WM and sensor supply rail is OFF. This intentionally
  changes existing outputs and clears the board's voltage setpoint.
- DISCONNECT, direct-shell EXIT, EOF, Ctrl+C and normal server exit perform
  the same verified shutdown before closing the port. A Python context manager
  also disconnects on exit. A shutdown error is reported, not hidden.
- `SAFE_OFF` disarms AUTO and invalidates previously queued ordinary operations
  when it reaches the operation lock. It cannot preempt the operation already
  running and has no reserved queue slot; see the known safety-queue limitation.
- An open serial port is not proof of a compatible tester or successful shutdown.
  The handshake checks response syntax, not a hardware identity/version.
- A cable loss, timeout or board restart invalidates output state. Disconnect,
  fix the connection and reconnect; the tool never resumes outputs automatically.
  Late acknowledgements are not allowed to authorize another mutation on a faulted
  connection. The firmware has no request IDs, so commands are never blindly retried.
- A killed process, removed cable, host crash or power failure cannot guarantee
  OFF. Steady WM outputs and continuous WM pulses may persist on the board.
  Sensor timed pulses have a firmware deadline, but software cannot verify it
  while disconnected. This tool is not a hardware emergency stop.
- Remote-shell EXIT only detaches that shell. It does not stop a shared server
  or other clients' outputs. Send `SAFE_OFF` or `DISCONNECT` explicitly, or stop
  the server normally with Ctrl+C.

## Requirements And Startup

The declared Python minimum is 3.10; that minimum has not been independently
tested. The recorded test environment used Python 3.12 and pyserial 3.5.
pyserial is required for physical serial access and port enumeration.
Tkinter and matplotlib are not needed.
Importing the module creates no windows, threads, files or serial connections.

Run these commands from the tester repository root, not the Flex Lite root:

```powershell
python -m pip install pyserial
python ".\New folder\FlexTesterApi.py" shell --port COM5
```

Replace COM5 with the correct port. To list ports before connecting:

```powershell
python ".\New folder\FlexTesterApi.py" shell
```

```text
PORTS
CONNECT COM5
STATUS
```

Default serial settings are 115200, 8N1, flow control disabled, DTR/RTS lowered,
LF command ending. Startup also accepts `--baudrate 115200` and
`--line-ending LF|CRLF|CR`. The current firmware is configured for 115200.

`--json` prints one JSON result per command to stdout. Prompts/errors go to
stderr in ordinary mode. An invalid command does not terminate the shell;
the shell exits with code 1 if any command failed. Startup codes distinguish
validation (2), connection/dependency (3), timeout (4), firmware (5), conflict (6),
unsupported feature (7), and unsafe shutdown (8).

### Startup Options

| Mode / option | Required | Default | Behavior |
| --- | --- | --- | --- |
| `shell` or `serve` | Yes | None | Select direct/remote CLI or local HTTP service |
| `--port <port>` | No | Disconnected | Connect at startup and reset outputs OFF |
| `--baudrate <baud>` | No | `115200` | Startup serial speed; the board must match |
| `--line-ending <LF\|CRLF\|CR>` | No | `LF` | Startup command terminator |
| `shell --json` | No | Disabled | Newline-delimited result envelopes on stdout |
| `shell --server <url>` | No | Direct mode | Use an existing loopback HTTP service |
| `serve --http-port <port>` | No | `8765` | Local TCP port; zero requests an ephemeral port |
| `-h` / `--help` | No | Disabled | Display startup or subcommand usage |

`--server` and `--port` are mutually exclusive. Baud rate and line-ending
options apply to a startup serial connection, not remote-server configuration.
Interactive `CONNECT <port>` has no baud/ending parameters and uses its own
115200/LF defaults. Use Python/HTTP connection arguments for other settings.

## CLI Reference

Commands and channel names are case-insensitive. In the syntax table, `<n>`
means 1, 2, 3 or 4; angle brackets identify required values and square brackets
identify optional argument groups. Do not type the brackets. All arguments not
explicitly marked optional are required. Integer fields reject nonintegral
fractions, out-of-range values, NaN and infinity. Use integer literals such as
`1000`, not `1000.0`: integer-valued floats are accepted by validation but are
not consistently normalized before serial formatting in the legacy interface
(a known defect). The new channel-batch interface normalizes integer fields.

| Exact syntax | Required arguments | Optional arguments / defaults | Expected result | Realistic example |
| --- | --- | --- | --- | --- |
| `PORTS` | None | None | Port/description/hwid list, possibly empty | `PORTS` |
| `CONNECT <port>` | Port name | None; 115200/LF | Safe connection; full status snapshot | `CONNECT COM5` |
| `DISCONNECT` | None | None | Verified shutdown and close | `DISCONNECT` |
| `STATUS` | None | None | Cached full snapshot, not forced refresh | `STATUS` |
| `CAPABILITIES` | None | None | Feature flags and limits | `CAPABILITIES` |
| `HELP` | None | None | Object containing the grouped CLI help lines | `HELP` |
| `SAFE_OFF` | None | None | Global shutdown verification result | `SAFE_OFF` |
| `EXIT` | None | None | No result printed; direct exit or remote detach | `EXIT` |
| `ON WM<n>` | WM channel | None | Steady HIGH, or no-op if already HIGH | `ON WM1` |
| `OFF WM<n>` | WM channel | None | Stop and drive LOW | `OFF WM1` |
| `START WM<n> [CYCLE_MS <ms>]` | WM channel | Cycle: 1000ms; allowed 20..3600000 | Begin continuous pulses | `START WM1 CYCLE_MS 1000` |
| `STOP WM<n>` | WM channel | None | Stop and drive LOW; retain period | `STOP WM1` |
| `MODE VAI<n> <MANUAL\|AUTOMATIC>` | VAI and mode | None; initial mode manual | Host configuration only | `MODE VAI1 MANUAL` |
| `SET VAI<n> MV <mv>` | VAI and 0..15000mV | None; initial presets 5000/7500/10000/15000 | Update manual host setpoint, not output | `SET VAI1 MV 5000` |
| `SCALE VAI<n> X1 <x1> X2 <x2> Y1 <y1> Y2 <y2>` | VAI and all four points | None; initial points 0/15000/0/100 | Update host scaling, not output | `SCALE VAI1 X1 0 X2 10000 Y1 0 Y2 100` |
| `VALUE VAI<n> <value>` | VAI and engineering value | None; requires automatic mode | Updated configuration and calculated mV/warning | `VALUE VAI1 50` |
| `ON VAI<n>` | VAI channel | Uses configured manual/scaled voltage | Enable selected sensor and verify supply | `ON VAI1` |
| `OFF VAI<n>` | VAI channel | None | Disable selected manual output or cancel its pulse | `OFF VAI1` |
| `PULSE VAI<n> MV <mv> DURATION_MS <ms>` | VAI, 0..15000mV, 10..3600000ms | None; no CLI wait flag | Running operation record and ID | `PULSE VAI1 MV 5000 DURATION_MS 2000` |
| `STOP VAI<n>` | VAI channel | None | Cancel timed pulse, or return idle; manual output needs OFF | `STOP VAI1` |
| `VIN AI<n>` | AI channel | None | One fresh sample | `VIN AI1` |
| `VIN ALL` | Literal ALL | None | Four sequential fresh sample records | `VIN ALL` |
| `SAMPLE <AI<n>...\|ALL> <ON\|OFF>` | Channels and state | None; all four initially selected | Add/remove channels and return selection | `SAMPLE AI1 AI2 ON` |
| `AUTO VAI<n> ON [DURATION_MS <ms>]` | VAI and ON | Duration 5000ms; allowed 10..3600000 | Arm VIN-trigger service, not immediate activation | `AUTO VAI1 ON DURATION_MS 5000` |
| `AUTO VAI<n> OFF [DURATION_MS <ms>]` | VAI and OFF | Duration accepted/validated but unused | Disarm and cancel its queued/active AUTO pulse | `AUTO VAI1 OFF` |
| `TIME GET` | Literal GET | None | Board time string | `TIME GET` |
| `TIME SET <HH:MM>` | Time, 00:00..23:59 | None | Acknowledge accepted time | `TIME SET 14:30` |
| `SYSTEM INIT` | Literal INIT | None | Explicit init surrounded by safe shutdown | `SYSTEM INIT` |
| `FIRMWARE HELP` | Literal HELP | None | Help-request acknowledgment; raw help in events | `FIRMWARE HELP` |
| `WAIT <operation_id> TIMEOUT_MS <ms>` | Operation ID and timeout | None in CLI; timeout 0..3700000ms | Terminal operation record or wait-timeout error | `WAIT 11111111111111111111111111111111 TIMEOUT_MS 10000` |
| `EVENTS AFTER <id>` | Cursor 0..9223372036854775807 | No CLI timeout option; immediate read | Event records, gap flag and last cursor | `EVENTS AFTER 0` |

The Python `wait_operation` method defaults to 10000ms, but CLI WAIT requires
the `TIMEOUT_MS` pair explicitly. `SAMPLE ... ON` adds channels; it does not
replace the selection. To sample only AI1, first `SAMPLE ALL OFF`, then
`SAMPLE AI1 ON`. `VIN ALL` performs separate reads, not a simultaneous snapshot.

Successful direct-shell output is the result object/list encoded as JSON.
With `--json`, it is wrapped in api_version/id/ok/status/result/error/timestamp.
Startup `--port COM5` does not print an interactive CONNECT result.

### WM Semantics

Only WM1..WM4 exist in this firmware. WM ON is not implemented as an
unconditional toggle: the client reads status, toggles only from stopped, and
does nothing if already HIGH. If pulses are running/armed, ON returns conflict;
use STOP first. START intentionally selects pulse mode even from steady HIGH.

The host period policy is 20..3600000ms. This is a validation policy, not a
timing-accuracy guarantee. Firmware uses nominal 5% HIGH / 95% LOW timing, and
can resume a saved partial phase after STOP/START. Do not assume a fresh first
edge or a reset pulse counter. The old GUI graph is a simulation, not a
hardware measurement. Valve-based TRIGGER is not offered: the current firmware
calls `wm.Task(false)` and cannot respond to a real valve trigger.

### Sensor Scaling And Shared Supply

VAI1..VAI4 share one VSEN voltage. This client permits one selected manual
sensor at a time and one timed pulse globally. Another owner's command returns
conflict rather than silently changing its voltage. OFF is not a global
emergency stop; SAFE_OFF is the explicit global action.

Manual voltage defaults match the GUI: 5000, 7500, 10000, 15000mV.
Default scaling is X1=0, X2=15000mV, Y1=0, Y2=100. Settings and mode changes
only change host configuration. ON or PULSE is always required to energize.
Configuration is in memory; explicit persistent JSON configuration is not part
of this version. Disarm a channel's AUTO before changing its settings.

```text
mv = X1 + (value - Y1) * (X2 - X1) / (Y2 - Y1)
engineering = Y1 + (mv - X1) * (Y2 - Y1) / (X2 - X1)
```

Y endpoints must differ, and X endpoints must differ for inverse/manual
scaling. Automatic results use Python round, matching the GUI. Out-of-engineering
range results carry a warning; nonfinite results or values outside 0..15000mV
are rejected. Sensor timed duration is 10..3600000ms. Zero mV means OFF, including
zero-mV timed pulses. The firmware calibration interval is 334..10120mV;
outside it, accuracy is not established. A requested voltage or ACK is not a
physical voltage measurement. VIN is a separate analog input and only measures
an output when the test wiring connects it appropriately.

### VIN And AUTO

All four inputs start background sampling after a successful connection.
One selected input is read approximately every 250ms, so four inputs get
approximately one sample per second each, depending on command traffic.
STATUS includes sample timestamps, ages, raw values, validity and saturation.
Supply and WM cache ages are reported separately. STATUS's top-level timestamp
is the time the snapshot was made, not proof of fresh board measurements.

VIN range is 0..10076mV and raw ADC is 0..4095. Raw4095 is saturation and
cannot trigger AUTO. AUTO requires VIN strictly greater than 1000mV, sample age
at most two seconds, and a fresh sample after completion before retriggering.
It uses AI1 -> VAI1, AI2 -> VAI2, AI3 -> VAI3 and AI4 -> VAI4.
The resolved manual/scaled output voltage is captured when AUTO is armed;
VIN is a trigger input, not the output-voltage setpoint. Multiple channels use
a FIFO; membership, validity, threshold and freshness are checked before dispatch.
AUTO-required inputs keep polling even if general sampling is turned off.
Manual supply operations are rejected while AUTO is armed; WM operations remain
independent. Disarming cancels that channel's queued/active AUTO pulse.

ADC errors, timeout or reset disarm AUTO. A timed operation is only completed
after a board completion event and supply-OFF verification, not by a host timer.
If the completion event is missing but the link is synchronized, the client
forces sensor OFF and verifies it, then reports failure. An unsynchronized/lost
link instead leaves the outcome unknown and requires reconnect.

FIFO holds at most one entry per channel and serves one pulse globally.
A fresh sample at or below 1000mV, or a saturated/invalid sample, removes that
channel's queued entry. A stale entry is discarded before dispatch. Falling VIN
does not cancel a pulse already running. Following normal completion, the
channel's cached VIN is removed, so a new sample is required to rejoin the tail;
VIN does not need to drop below threshold first. Other channels can remain armed
when one is disabled. Changing settings on an armed channel is rejected.

SAFE_OFF clears all AUTO selections and the FIFO, but leaves background sampling
enabled. A communication fault clears AUTO/FIFO/VIN, invalidates WM/supply state
and marks an active pulse outcome unknown. AUTO never automatically rearms.
After recovery, explicitly DISCONNECT, CONNECT and re-enable desired AUTO channels.

Normal timed completion and STOP disable sensor rails/booster/PWM, but firmware
may retain the previous requested supply mV. SAFE_OFF explicitly sends zero.
Physical decay of output voltage depends on load and capacitance.

## Python Usage

Run from the new module's directory, or include that directory in your test
runner's import path:

```python
from FlexTesterApi import TesterClient

with TesterClient() as tester:
    tester.connect("COM5")
    tester.set_scaling(1, x1=0, x2=10000, y1=0, y2=100)
    tester.set_scaling_mode(1, "automatic")
    tester.set_engineering_value(1, 50)
    tester.sensor_on(1)
    sample = tester.read_vin(1)
    print(sample["mv"], sample["valid"])
    tester.sensor_off(1)
    tester.set_wm_output(1, True)
    tester.set_wm_output(1, True)
    tester.stop_wm(1)
    operation = tester.pulse_sensor(1, 5000, 2000, wait=True)
    assert operation["status"] == "completed"
```

`TesterError` carries `code`, `outcome` and `to_dict()`. `get_status(refresh=True)`
queries WM and supply status; ordinary get_status returns a cache snapshot.
`configure_sampling([1,2], enabled=True)`, `configure_auto(1, True, 5000)`,
`get_operation(id)`, `wait_operation(id, timeout_ms=10000)` and
`get_events(after=0, timeout_ms=0)` are also available.

Events contain timestamped raw serial TX/RX and VIN samples. The ring holds
2048 events and reports `gap=true` when a cursor predates available history.
Consume/record them during long tests. This version does not open log/CSV files
automatically; test scripts can use the standard json/csv libraries to export
samples. Completed operation records are bounded to 1024 entries.

## Local HTTP Service

```powershell
python ".\New folder\FlexTesterApi.py" serve --port COM5 --http-port 8765
```

Omit `--port` to start disconnected. Connect later using the API or a remote
shell. The service binds only 127.0.0.1. It rejects browser Origin headers and
non-loopback Host headers; there is no remote-network/authentication support.
This is a local test-bench service, not a production web server. It supports
16 concurrent HTTP requests and 32 executing/waiting library operations in total.
At the HTTP request limit, a connection may be closed without a JSON503 response.

```powershell
python ".\New folder\FlexTesterApi.py" shell --server http://127.0.0.1:8765
```

The remote shell never opens COM. Multiple HTTP clients share one serial
owner and one serialized action dispatcher. Do not start a second direct
serial shell while the server owns that port.

| Endpoint | Result |
| --- | --- |
| `GET /api/v1/ports` | Available ports |
| `GET /api/v1/status` | Timestamped cache, connection, configuration, AUTO and operation |
| `GET /api/v1/capabilities` | Supported channels/features and limits |
| `GET /api/v1/operations/{id}` | Operation status |
| `GET /api/v1/events?after=0&timeout_ms=0` | Events; optional long-poll up to 30000ms |
| `POST /api/v1/commands` | Execute a typed command |

Example from PowerShell:

```powershell
$body = @{id="wm-high-001"; action="wm.on"; args=@{channel=1}} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/v1/commands -ContentType application/json -Body $body
```

Example command body:

```json
{"id":"pulse-001","action":"sensor.pulse","args":{"channel":1,"mv":5000,"duration_ms":2000}}
```

HTTP200 means the handler successfully returned a result. Mutating actions
perform their documented logical verification; reading an operation record can
return HTTP200/ok=true even when that record describes a failed/unknown operation.
A pulse returns HTTP202, `status=running` and `result.id`; follow its operation
resource until completed/cancelled/failed/unknown. HTTP requests cannot request
blocking `wait=true` pulses or operation.wait; the library and shell provide
waiting. AUTO configuration acknowledges arming, not a completed pulse.

Every response has api_version, id, ok, status, result, error and timestamp.
Failures include a stable error.code/message/outcome. HTTP codes include 400
validation, 403 forbidden, 404 missing resource, 409 conflict/disconnected,
422 firmware/unsupported, 503 unavailable/unsafe, and 504 timeout.

POST accepts either the legacy id/action/args format or the RequestId/Commands
channel-batch format documented below. Mixing these formats is rejected;
unknown fields and arguments are rejected.
The fixed wire deadline is 1.5s by default (configurable in TesterClient), not
a per-HTTP timeout_ms field. HTTP IDs are host-side correlation/deduplication,
not firmware request IDs. Within a process, repeating the same ID and payload
returns its original result without repeating the command; changed arguments
return409. The cache holds up to 1024 IDs, evicts completed records and is lost
on restart. Never assume durable/exactly-once execution after eviction, restart
or lost connectivity. Track operation IDs for pulse completion.

### Combined VAI, WM And AI JSON Requests

The same POST /api/v1/commands endpoint now accepts a single request containing
VAI, WM and AI operations in a Commands array. The legacy interface remains
available. The directly sendable example is
[FlexTesterApi.examples.json](FlexTesterApi.examples.json).
Its previous example-test-plan contents have been replaced by this batch.

```json
{
  "RequestId": "batch-auto-vai1-wm1-001",
  "Commands": [
    {
      "Port": "VAI", "PortNum": 1, "Action": "Configure",
      "X1": 0, "Y1": 0, "X2": 10000, "Y2": 100,
      "Output_Value": 50, "Operation_Mode": "Automatic",
      "Manual_voltage": null, "Auto_Enabled": true,
      "Cycle_ms": null, "Duration_ms": 5000
    },
    {
      "Port": "WM", "PortNum": 1, "Action": "Start",
      "X1": null, "Y1": null, "X2": null, "Y2": null,
      "Output_Value": null, "Operation_Mode": null,
      "Manual_voltage": null, "Auto_Enabled": null,
      "Cycle_ms": 1000, "Duration_ms": null
    }
  ]
}
```

This maps 50 engineering units to 5000mV, arms VAI1 AUTO with a 5000ms pulse
duration, then starts WM1 at a 1000ms period. VAI1 waits for a fresh, valid AI1
reading strictly above 1000mV before pulsing. It can retrigger on new readings
after completion while VIN remains high. WM1 starts independently of VIN.
Only send this file after approving the load, wiring and voltage limits.
Do not append a manual VAI On after arming AUTO; manual supply commands conflict
while AUTO is armed. Successful arming does not prove a pulse has occurred.

Start the server in the first PowerShell terminal from the tester root:

```powershell
python ".\New folder\FlexTesterApi.py" serve --port COM5 --http-port 8765
```

Release COM5 from the GUI first, replace the port as appropriate, and restart
any old API server process so it loads the updated implementation. In a second
PowerShell terminal, send the file as the body itself (no extraction required):

```powershell
$body = Get-Content ".\New folder\FlexTesterApi.examples.json" -Raw
$reply = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/v1/commands" -ContentType "application/json" -Body $body
$reply | ConvertTo-Json -Depth 20
```

Change RequestId for each new intended execution, especially after modifying
the file. Repeating an existing ID and identical body returns the cached
response without re-executing it; changed content with the same ID returns409.
For a delivery-uncertain retry, keep the same ID/body. This remains bounded,
in-memory deduplication, not persistent exactly-once delivery.

To stop both kinds of output after observing the successful request:

```powershell
$stop = @{id=[guid]::NewGuid().ToString(); action="safety.off"; args=@{}} | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/v1/commands" -ContentType "application/json" -Body $stop
```

#### Batch Field Contract

- The root contains only RequestId and Commands. RequestId is a nonempty string
  of at most 128 characters. Commands contains 1..32 objects.
- Each command requires Port, PortNum and Action. Port is VAI, WM or AI;
  PortNum is 1..4. Port/Action values are case-insensitive; field names are exact.
- Use null for unused fields. Omitted optional fields also mean no update.
  Required fields cannot be null. Zero is an actual voltage value, not omission.
- A known field with a non-null value inappropriate to its action is rejected.
  Unknown fields are rejected even if null. State and WM_Action are replaced
  by Action; DI is not an alias for WM.
- Configure updates host settings. Without Auto_Enabled=true it does not activate
  a new output. Auto_Enabled=true explicitly arms future VIN-triggered pulses;
  these can begin after the batch releases the operation lock. Applying manual
  voltage still requires On, and an already active manual output is not updated
  merely by changing its host settings.
- Configure merges all non-null fields into a candidate configuration and
  validates the final result together, rather than validating intermediate
  mode/value combinations. Partial scaling updates retain other endpoints.
- Automatic (also accepted as Auto) means engineering conversion, not VIN AUTO.
  Auto_Enabled independently controls VIN AUTO; the legacy auto.configure action
  remains available too.

#### Auto_Enabled And Duration_ms

Auto_Enabled is optional and accepts JSON true, false or null, not strings or
numeric 0/1. It is meaningful only in VAI / Configure. On WM, AI and other VAI
actions it must be null or omitted. Older requests that omit it remain valid.

| Value | Behavior |
| --- | --- |
| true | Arm matching AI-to-VAI AUTO using the final resolved output voltage. An already armed channel with unchanged settings stays armed without restarting its pulse, queue or fresh-sample state. |
| false | Disarm this channel, remove queued work and cancel its active AUTO pulse. It does not stop unrelated WM outputs or act as OFF for an unrelated manual sensor output. |
| null or omitted | Preserve AUTO state. This is not cancellation or reset. |

In Configure, non-null Duration_ms is permitted only with Auto_Enabled=true.
Its range is 10..3600000ms. On a newly armed channel, null/omitted duration uses
5000ms. On an already armed channel, null/omitted preserves its current duration.
Passing the same duration again is allowed, but a different duration or changed
voltage/scaling while armed requires an explicit disarm first. A runtime
conflict still invokes the batch's global failure-cleanup policy.

To disable AUTO in a later request, use VAI / Configure with Auto_Enabled=false,
Duration_ms=null and other unused fields null. You can also supply new manual
settings in that same Configure: the active AUTO pulse is cancelled before
changed settings are applied. A following On can then select manual output,
provided no other channel still owns AUTO/the shared supply. SAFE_OFF and
communication faults continue to disarm AUTO; it never rearms by itself.

The input is sampled even below the threshold. AUTO controls the output pulse,
not whether sampling occurs. Exactly 1000mV does not trigger, stale samples
older than two seconds and raw4095 saturation do not trigger, and FIFO permits
one sensor pulse globally. An active pulse finishes even if VIN falls. After
completion, a new qualifying sample can retrigger without a falling edge.

| Port / Action | Allowed non-null optional fields | Required values and defaults |
| --- | --- | --- |
| VAI / Configure | X1, Y1, X2, Y2, Output_Value, Operation_Mode, Manual_voltage, Auto_Enabled, Duration_ms | Finite scale; unequal Y endpoints; unequal X endpoints for manual inverse scaling. Manual_voltage=0..15000 only in Manual mode; Output_Value only in Automatic mode. Duration_ms requires Auto_Enabled=true; initial default 5000ms. Unchanged settings retained. |
| VAI / On | None | Use configured manual/scaled voltage; do not pass Manual_voltage here. |
| VAI / Off | None | Disable the selected manual sensor or cancel its manual pulse, subject to ownership. |
| VAI / Stop | None | Cancel timed output; manually enabled sensors need Off. |
| VAI / Pulse | Manual_voltage, Duration_ms | Duration_ms required, 10..3600000. Manual_voltage optionally overrides the pulse voltage, 0..15000; null uses the configured resolved voltage. Does not change the stored preset/mode. |
| WM / Start | Cycle_ms | Null or omitted uses 1000; allowed 20..3600000. |
| WM / On, Off, Stop | None | Steady HIGH, LOW or stop using the existing WM semantics. |
| AI / Read | None | Read a fresh VIN sample from the selected channel. |

Trigger returns unsupported. Batch connection/system/time/sampling operations
are not defined; use the legacy request format for those actions. Direct Python
callers may use tester.execute_channel_batch(commands) with the same Commands
array; HTTP supplies RequestId deduplication.

#### Execution, Errors And Responses

The tester must already be connected and ready. The complete array's schema,
numeric arguments and prospective scaling configurations are validated before
any batch command is applied. Static validation errors return400 (or422 for
unsupported Trigger), with no batch commands executed and no cleanup action.
Existing outputs are therefore not changed merely because validation failed.
Runtime hardware/resource/ownership conditions are checked during execution.

One exclusive operation lock covers the batch. Other requests and background
polling cannot interleave between its commands. Commands execute sequentially;
this is not simultaneous hardware activation or a hardware-atomic transaction.
Queued shutdown requests are checked at command boundaries. Long batches can
delay other requests and background sampling, so keep batches short.

On runtime failure, later commands are skipped and a global SAFE_OFF sequence
is attempted while still holding ownership. Cleanup can turn off outputs that
were active before this request. Configuration updates already applied are not
rolled back. Logical OFF is only claimed if cleanup verification succeeds.
If serial synchronization is lost, no ambiguous mutating retries are sent;
cleanup is reported unverified and overall outcome unknown/unsafe.

The normal result object has status, commands, cleanup and error. Each command
entry contains zero-based index, Port, PortNum, Action, status, result and error.
Configure returns the merged configuration plus resolved_mv, warning,
Auto_Enabled and Duration_ms. Duration_ms is null when this channel is disarmed.
Arming returns HTTP200 as a completed configuration action, not proof of a
completed pulse; inspect status/events for subsequent AUTO activity.
Other commands retain their existing result shapes. A successful batch has
cleanup=null/error=null. Runtime failures retain per-command results even when
the outer envelope has ok=false; skipped commands have null result/error.
Successful entries describe steps that executed, not a promise that their
outputs stayed active after a later global cleanup.

HTTP200 indicates completion of the requested commands. If a sensor pulse is
still accepted/running, HTTP202 and status=running are returned, with its ID at
result.commands[index].result.id. Follow GET /api/v1/operations/{id}; batches do
not wait for physical pulse duration. Repeating the batch ID returns its
original cached response, not a refreshed operation status.

On failure, the original per-command error remains in that command entry.
The outer error reflects that failure when cleanup succeeded, or unsafe when
cleanup failed. result.cleanup contains attempted, verified and error. Check
all of these fields; do not treat a successful earlier step as proof of final
electrical state. Connection loss still cannot guarantee physical shutdown.

This is a channel-command batch adapter, not the earlier general-purpose JSON
test-plan runner: test_programs, delays, assertions, variable substitutions and
operator checkpoints are not accepted in this request format.

### Actions And Arguments

The dispatcher exposes these actions consistently to local/remote callers:

| Action | Arguments |
| --- | --- |
| `ports`, `capabilities`, `help` | none |
| `connection.connect` | port, optional baudrate/line_ending |
| `connection.disconnect`, `safety.off` | none |
| `status` | optional refresh boolean |
| `wm.on`, `wm.off`, `wm.stop` | channel |
| `wm.start` | channel, optional cycle_ms |
| `sensor.on`, `sensor.off`, `sensor.stop` | channel |
| `sensor.pulse` | channel, mv, duration_ms; HTTP is asynchronous |
| `sensor.voltage` | channel, mv |
| `scaling.configure` | channel, x1, x2, y1, y2 |
| `scaling.mode` | channel, mode: manual or automatic |
| `scaling.value` | channel, value |
| `vin.read` | channel |
| `sampling.configure` | channels array, optional enabled boolean |
| `auto.configure` | channel, enabled, optional duration_ms |
| `supply.status`, `system.init`, `time.get`, `firmware.help` | none |
| `time.set` | value: HH:MM |
| `operation.get` | operation_id |
| `events` | optional after/timeout_ms |

## Wire Protocol

Only the serial transport reads bytes. All writers, including polling and
AUTO, use the same exclusive operation lock. Compound operations cannot be
interleaved. The transport accepts CR/LF response framing and fragmented data;
command echoes are not acknowledgements. It processes unsolicited reset and
pulse events separately. Buffers are bounded, and no raw mutating passthrough
is exposed.

| High-level behavior | Existing firmware request |
| --- | --- |
| WM pulses / stop | `start wm 1 1000` / `stop wm 1` |
| Steady WM HIGH | `get status`, conditional `toggle wm 1`, `get status` |
| WM status | `get status` |
| Safe sensor reset | `set vsen 0` |
| Manual sensor ON | safe zero, `set vsen 5000`, `set vsen_en on`, `set vai 1 on`, `get vsen` |
| Timed pulse | `pulse vai 1 5000 2000` |
| Cancel pulse | `stop vai 1` |
| Supply status | `get vsen` |
| VIN | `get ain 1` |
| Time / init | `get time`, `set time 14:30`, `system init` |

Example replies include `wm 1 manual on`, `ain 1 raw=2032 mv=5000`,
`vai 1 ON pulse_ms=2000`, and later `vai 1 OFF pulse complete`.
Timed ACKs/completions also include a separate vsen status line. Firmware errors
are propagated rather than treating a write or an echo as success.

## Verification And Limits

```powershell
python -m unittest discover -s ".\New folder" -p test_flex_tester_api.py -v
python -m py_compile ".\New folder\FlexTesterApi.py" ".\New folder\test_flex_tester_api.py"
```

Tests use a fake serial device and actual ephemeral loopback HTTP sockets;
they do not energize hardware. Coverage includes scaling, echoes and fragmented
lines, safe lifecycle, idempotent/concurrent WM ON, sensor ownership and cleanup,
zero-voltage/cancelled/completed pulses, serial loss/timeouts, FIFO AUTO,
threshold/freshness/saturation, reset disarming, CLI subprocesses, HTTP duplicate
IDs/validation, local access restrictions and event cursor gaps.

Physical COM operation, output voltage accuracy, pulse timing and wiring still
require explicit hardware acceptance testing with safe loads and appropriate
measurement equipment. No firmware was changed or flashed. Excluded features:
FLEX second-port CLI, Log Analyzer, GUI migration, WM5, legacy DAC controls,
and valve-trigger operation. No plotting, persistent configuration or automatic
file export is provided in this version.

## CLI Output Examples

These are independent examples, not one continuous session. Real measurements
depend on external wiring. Timestamps and identifiers are illustrative. Ordinary
shell output is compact one-line JSON; examples are formatted for readability.

### PORTS

```json
[
  {
    "port": "COM5",
    "description": "USB Serial Port (COM5)",
    "hwid": "USB VID:PID=0403:6001 SER=FT123456"
  }
]
```

The adapter identity is illustrative, not a required device. No ports returns
`[]`. CONNECT returns the complete status structure in
[Complete Status Response](#complete-status-response), without the outer HTTP
envelope. Immediately after connection its VIN object is normally empty,
outputs are stopped and sampling is `[1,2,3,4]`. STATUS returns the same result
shape using cached data. CAPABILITIES returns the capability result documented
in [HTTP Response Examples](#http-response-examples).

### SUPPLY STATUS

```json
{
  "enabled": false,
  "mv": 0,
  "ccr4": 0,
  "duty_percent": 0.0,
  "pwm": "run",
  "rails": {"1": "off", "2": "off", "3": "off", "4": "off"},
  "calibration": "off",
  "timestamp": "2026-10-15T12:00:00+00:00"
}
```

`pwm=run` with duty zero is compatible with disabled outputs. Requested `mv`
is not a voltage measurement, and can be nonzero after a timed pulse ends.

### VIN AI1 And VIN ALL

`VIN AI1`:

```json
{
  "channel": 1,
  "raw": 2032,
  "mv": 5000,
  "saturated": false,
  "valid": true,
  "timestamp": "2026-10-15T12:00:03.250000+00:00",
  "monotonic": 1000.0
}
```

`VIN ALL`:

```json
[
  {"channel":1,"raw":2032,"mv":5000,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.250000+00:00","monotonic":1000.0},
  {"channel":2,"raw":1016,"mv":2500,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.500000+00:00","monotonic":1000.25},
  {"channel":3,"raw":0,"mv":0,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.750000+00:00","monotonic":1000.5},
  {"channel":4,"raw":4064,"mv":9999,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:04+00:00","monotonic":1000.75}
]
```

Direct VIN results do not include age_seconds. STATUS adds age_seconds to cached
samples. A fresh VIN request does not substitute a cached sample.

### WM Output And Pulse Control

```text
tester> ON WM1
{"channel":1,"state":"manual on","changed":true}
tester> ON WM1
{"channel":1,"state":"manual on","changed":false}
tester> OFF WM1
{"channel":1,"state":"stopped","cycle_ms":1000}
tester> START WM1 CYCLE_MS 1000
{"channel":1,"state":"started","cycle_ms":1000}
tester> STOP WM1
{"channel":1,"state":"stopped","cycle_ms":1000}
```

### Sensor Configuration And Output

```text
tester> MODE VAI1 MANUAL
{"mv":5000,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":33.333333333333336}
tester> SET VAI1 MV 5000
{"mv":5000,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":33.333333333333336}
tester> ON VAI1
{"channel":1,"mv":5000,"warning":null,"supply":{"enabled":true,"mv":5000,"ccr4":21031,"duty_percent":32.09,"pwm":"run","rails":{"1":"on","2":"off","3":"off","4":"off"},"calibration":"interpolated","timestamp":"2026-10-15T12:00:00+00:00"},"calibration_warning":false}
tester> OFF VAI1
{"channel":1,"supply":{"enabled":false,"mv":0,"ccr4":0,"duty_percent":0.0,"pwm":"run","rails":{"1":"off","2":"off","3":"off","4":"off"},"calibration":"off","timestamp":"2026-10-15T12:00:01+00:00"}}
tester> PULSE VAI1 MV 5000 DURATION_MS 2000
{"id":"11111111111111111111111111111111","channel":1,"mv":5000,"duration_ms":2000,"status":"running","automatic":false,"timestamp":"2026-10-15T12:00:02+00:00","deadline":1003.5}
```

The ON example reflects the firmware calibration table, not a new physical
measurement. For an active timed pulse, OFF returns the STOP-shaped result
instead of the manual supply object. STOP while idle returns idle:

```text
tester> STOP VAI1
{"channel":1,"state":"stopped"}
tester> STOP VAI1
{"channel":1,"state":"idle"}
```

### Scaling Example

```text
tester> SCALE VAI1 X1 0 X2 10000 Y1 0 Y2 100
{"mv":5000,"scaling":{"x1":0,"x2":10000,"y1":0,"y2":100},"scaling_mode":"manual","value":33.333333333333336}
tester> MODE VAI1 AUTOMATIC
{"mv":5000,"scaling":{"x1":0,"x2":10000,"y1":0,"y2":100},"scaling_mode":"automatic","value":33.333333333333336}
tester> VALUE VAI1 50
{"mv":5000,"scaling":{"x1":0,"x2":10000,"y1":0,"y2":100},"scaling_mode":"automatic","value":50.0,"warning":null}
```

An explicit ON is still required. In automatic mode the returned mv is resolved
from the engineering value; the stored manual preset remains separate.

### AUTO, WAIT, EVENTS And SAFE_OFF

```text
tester> AUTO VAI1 ON DURATION_MS 5000
{"channel":1,"duration_ms":5000,"mv":5000,"threshold_mv":1000,"enabled":true}
tester> AUTO VAI1 OFF
{"channel":1,"enabled":false}
tester> WAIT 11111111111111111111111111111111 TIMEOUT_MS 10000
{"id":"11111111111111111111111111111111","channel":1,"mv":5000,"duration_ms":2000,"status":"completed","automatic":false,"timestamp":"2026-10-15T12:00:04+00:00","deadline":1003.5,"completion":"complete"}
tester> EVENTS AFTER 42
{"events":[{"id":43,"type":"pulse.completed","timestamp":"2026-10-15T12:00:04+00:00","operation_id":"11111111111111111111111111111111","channel":1}],"gap":false,"last_id":43}
tester> SAFE_OFF
{"safe_off":true,"verified":true}
tester> DISCONNECT
{"connected":false,"safe_off":true}
```

WAIT above refers to an earlier manual pulse. A cancelled operation may contain
`completion=cancelled`; SAFE_OFF cancellation can omit completion. No prior
verified shutdown can produce safe_off=null on an already-disconnected client.
TIME GET may return `{"time":"12:34:0"}` without zero padding; TIME SET returns
the accepted HH:MM string. SYSTEM INIT returns initialized=true/safe_off=true.

## Common Error Responses

Ordinary CLI errors use `ERROR <code>: <message>` on stderr. In JSON mode they
use a result envelope with result=null and an error object. Driver-dependent
messages below are representative; punctuation and OS details are not stable.
Connection/read/write ambiguity normally has outcome=unknown, not failed.

| Condition | Representative ordinary CLI response | Typical HTTP code / outcome |
| --- | --- | --- |
| Missing pyserial | `ERROR dependency: Install pyserial: python -m pip install pyserial` | 503 / failed |
| Port not found | `ERROR connection: could not open port 'COM99': FileNotFoundError(2, 'The system cannot find the file specified.', None, 2)` | 503 / unknown |
| Port already owned by another program | `ERROR connection: could not open port 'COM5': PermissionError(13, 'Access is denied.', None, 5)` | 503 / unknown |
| This client already connected | `ERROR conflict: Disconnect the current session before connecting.` | 409 / failed |
| Serial response timeout | `ERROR timeout: No complete response to: toggle wm 1` | 504 / unknown |
| Invalid command | `ERROR validation: Unrecognized command. Type HELP.` | CLI validation; unknown HTTP action is 400 |
| Invalid CLI channel, e.g. ON WM5 | `ERROR validation: Unrecognized command. Type HELP.` | CLI validation |
| Invalid numeric API channel 5 | `ERROR validation: channel must be 1..4.` | 400 / failed |
| WM running while steady HIGH requested | `ERROR conflict: Stop WM pulses before selecting steady HIGH.` | 409 / failed |
| Different sensor owns supply | `ERROR conflict: A different sensor owns the shared supply.` | 409 / failed |
| Manual supply command while AUTO armed | `ERROR conflict: Sensor supply is owned by AUTO or an active pulse.` | 409 / failed |
| Serial read connection loss | `ERROR connection: Cable removed` in the fake-serial test; actual driver text varies | 503 / unknown |
| Serial write connection loss | `ERROR connection: Serial write failed: <driver error>` | 503 / unknown |
| Command while disconnected/faulted | `ERROR disconnected: Connect to the tester; faults require reconnect.` | 409 / failed |
| Disconnect on unsynchronized link | `ERROR unsafe: Link is unsynchronized; outputs remain unknown.` | 503 / unknown |
| Failed shutdown sequence | `ERROR unsafe: Safe shutdown incomplete: [...]` | 503 / unknown |
| Wait timeout | `ERROR timeout: Wait expired; operation may still be running.` | Local wait error; HTTP operation.wait is rejected |

There is no separate port-not-found or port-busy error code. Both are connection
errors from the OS/serial driver. Background service failures can appear only in
events/status until a subsequent command fails. Startup/shutdown errors can
print plain stderr messages even with --json; shutdown failure may appear as
`WARNING shutdown: Link is unsynchronized; outputs remain unknown.`

## HTTP Response Examples

Every JSON block below is a complete body. Requests must use the explicit
loopback Host and port. All GET response IDs are null. POST response IDs echo
the caller's ID. Envelopes do not establish physical electrical safety.

### GET /api/v1/ports - HTTP 200

```json
{
  "api_version":"1", "id":null, "ok":true, "status":"completed",
  "result":[{"port":"COM5","description":"USB Serial Port (COM5)","hwid":"USB VID:PID=0403:6001 SER=FT123456"}],
  "error":null, "timestamp":"2026-10-15T12:00:00+00:00"
}
```

### GET /api/v1/capabilities - HTTP 200

```json
{
  "api_version": "1",
  "id": null,
  "ok": true,
  "status": "completed",
  "result": {
    "api_version": "1",
    "wm_channels": [1,2,3,4],
    "sensor_channels": [1,2,3,4],
    "voltage_mv": [0,15000],
    "pulse_duration_ms": [10,3600000],
    "wm_cycle_ms_host_policy": [20,3600000],
    "vin_max_mv": 10076,
    "calibrated_mv": [334,10120],
    "trigger_wm": false,
    "trigger_limitation": "Firmware calls wm.Task(false); valve triggering is unavailable.",
    "safe_off_on_connect_and_disconnect": true,
    "shared_sensor_supply": true,
    "physical_voltage_verified": false
  },
  "error": null,
  "timestamp": "2026-10-15T12:00:00+00:00"
}
```

### Complete Status Response

GET /api/v1/status returns HTTP200 even while disconnected. This complete
connected example includes four cached input samples. Python dictionaries use
integer channel keys; JSON object keys are strings.

```json
{
  "api_version": "1",
  "id": null,
  "ok": true,
  "status": "completed",
  "result": {
    "connection": "ready",
    "port": "COM5",
    "timestamp": "2026-10-15T12:00:04+00:00",
    "wm": {
      "1": {"state":"stopped","cycle_ms":1000},
      "2": {"state":"stopped","cycle_ms":1000},
      "3": {"state":"stopped","cycle_ms":1000},
      "4": {"state":"stopped","cycle_ms":1000}
    },
    "supply": {
      "enabled": false,
      "mv": 0,
      "ccr4": 0,
      "duty_percent": 0.0,
      "pwm": "run",
      "rails": {"1":"off","2":"off","3":"off","4":"off"},
      "calibration": "off",
      "timestamp": "2026-10-15T12:00:03+00:00"
    },
    "outputs_known": true,
    "wm_age_seconds": 1.0,
    "supply_age_seconds": 1.0,
    "last_safe_off": true,
    "vin": {
      "1": {"channel":1,"raw":2032,"mv":5000,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.250000+00:00","monotonic":1000.0,"age_seconds":0.75},
      "2": {"channel":2,"raw":1016,"mv":2500,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.500000+00:00","monotonic":1000.25,"age_seconds":0.5},
      "3": {"channel":3,"raw":0,"mv":0,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:03.750000+00:00","monotonic":1000.5,"age_seconds":0.25},
      "4": {"channel":4,"raw":4064,"mv":9999,"saturated":false,"valid":true,"timestamp":"2026-10-15T12:00:04+00:00","monotonic":1000.75,"age_seconds":0.0}
    },
    "config": {
      "1": {"mv":5000,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":33.333333333333336},
      "2": {"mv":7500,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":50.0},
      "3": {"mv":10000,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":66.66666666666667},
      "4": {"mv":15000,"scaling":{"x1":0,"x2":15000,"y1":0,"y2":100},"scaling_mode":"manual","value":100.0}
    },
    "sampling": [1,2,3,4],
    "auto": {},
    "auto_queue": [],
    "active_operation": null
  },
  "error": null,
  "timestamp": "2026-10-15T12:00:04+00:00"
}
```

### Status Field Dictionary

| Field | Meaning |
| --- | --- |
| Envelope api_version | String API contract identifier, currently 1 |
| Envelope id | POST correlation ID, or null for GET |
| Envelope ok | No exception occurred while handling this request; not an electrical safety flag |
| Envelope status | Handler/operation outcome; completed, running, accepted, cancelled, failed or unknown |
| Envelope result | Returned data; usually null on errors, but runtime batch failures retain command/cleanup details |
| Envelope error | null or code/message/outcome object |
| Envelope timestamp | UTC response-creation time |
| result.connection | disconnected, connecting, safe_reset, ready or fault; transient states may not be externally observable while the lock is held |
| result.port | Selected or last attempted port; not cleared by disconnect |
| result.timestamp | UTC snapshot-creation time, not the measurement time |
| result.wm | Channel map of cached WM logical status |
| wm[n].state | stopped, manual on, started, triggered or running (triggered) |
| wm[n].cycle_ms | Retained full period; not a counter or measured edge interval |
| result.supply | Last parsed supply status, or null when absent/invalidated |
| supply.enabled | Reported booster-enable state |
| supply.mv | Requested board setpoint; not measured voltage |
| supply.ccr4 | PWM timer compare count |
| supply.duty_percent | Duty calculated from compare/timer period |
| supply.pwm | Timer run/stopped state; run does not imply nonzero output |
| supply.rails[n] | on, off or pend (requested while master is disabled) |
| supply.calibration | off, interpolated, extrapolated, or unknown for older status without the field |
| supply.timestamp | UTC time the host parsed that supply observation |
| result.outputs_known | Exactly connection == ready; does not prove physical measurements or freshness |
| result.wm_age_seconds | Age of the last parsed WM observation, or null |
| result.supply_age_seconds | Age of the last parsed supply observation, or null |
| result.last_safe_off | Historical safety bookkeeping: true, false or null; see stale-fault defect |
| result.vin | Cached channel samples; initially empty after connection |
| vin[n].channel | AI channel ID |
| vin[n].raw | ADC count 0..4095 |
| vin[n].mv | Converted nominal VIN, 0..10076mV; input operating range remains 0..10V |
| vin[n].saturated | True for raw4095 |
| vin[n].valid | False for saturation; true does not prove wiring/reference accuracy |
| vin[n].timestamp | UTC time the sample was parsed by the host |
| vin[n].monotonic | Host monotonic clock seconds, not an absolute date |
| vin[n].age_seconds | Snapshot-time age of the cached sample |
| result.config | Host-only per-channel settings; not board readback |
| config[n].mv | Stored manual preset; can differ from resolved automatic voltage |
| config[n].scaling.x1/x2 | Voltage endpoints in mV |
| config[n].scaling.y1/y2 | Engineering-unit endpoints |
| config[n].scaling_mode | manual or automatic engineering conversion; separate from AUTO triggering |
| config[n].value | Stored desired engineering value |
| result.sampling | General polling selection; AUTO channels may additionally be sampled |
| result.auto | Armed channel map with duration_ms, captured mv, threshold_mv=1000, enabled=true |
| result.auto_queue | FIFO of channel IDs, not operation IDs |
| result.active_operation | null or the pulse operation record described below |

For a fresh WM/supply query use POST action status with args `{"refresh":true}`.
GET status does not force fresh measurements. After disconnect, wm/vin/auto
are empty, supply/active_operation/ages are null, sampling/auto_queue are empty,
and outputs_known is false. Configuration, port, operations and event history
can remain available. After a fault, ages/last_safe_off may be stale due to the
documented defect; they must not override fault/outputs_known=false.

### GET /api/v1/operations/{id} - HTTP 200

```json
{
  "api_version":"1", "id":null, "ok":true, "status":"completed",
  "result":{
    "id":"11111111111111111111111111111111",
    "channel":1, "mv":5000, "duration_ms":2000, "status":"completed",
    "automatic":false, "timestamp":"2026-10-15T12:00:04+00:00",
    "deadline":1003.5, "completion":"complete"
  },
  "error":null, "timestamp":"2026-10-15T12:00:04+00:00"
}
```

Operation id is distinct from the HTTP correlation id. Status is accepted,
running, completed, cancelled, failed or unknown. Automatic is true for an AUTO
pulse. Timestamp is initially creation time and can be updated at completion
or cancellation. Deadline is the host monotonic watchdog deadline, not a UTC
finish time. Completion is added after a complete/cancelled event; failure can
add an error object. A record lookup can succeed with ok=true even when the
returned operation has status failed/unknown. Check both fields.

### GET /api/v1/events?after=42&timeout_ms=0 - HTTP 200

```json
{
  "api_version":"1", "id":null, "ok":true, "status":"completed",
  "result":{
    "events":[{
      "id":43, "type":"pulse.completed",
      "timestamp":"2026-10-15T12:00:04+00:00",
      "operation_id":"11111111111111111111111111111111", "channel":1
    }],
    "gap":false, "last_id":43
  },
  "error":null, "timestamp":"2026-10-15T12:00:04+00:00"
}
```

Default after=0 and timeout_ms=0. Long polling allows 0..30000ms and returns
an empty events array on an ordinary wait expiration, not an HTTP504. Cursor
IDs are monotonically increasing within the client object. A gap indicates
history was overwritten. Event-specific fields vary; serial.tx/rx carry line,
vin carries sample, and faults carry error/outputs.

### POST Successful Command - HTTP 200

Request body: `{"id":"wm-on-001","action":"wm.on","args":{"channel":1}}`.

```json
{
  "api_version":"1", "id":"wm-on-001", "ok":true, "status":"completed",
  "result":{"channel":1,"state":"manual on","changed":true},
  "error":null, "timestamp":"2026-10-15T12:00:00+00:00"
}
```

### POST Accepted Timed Pulse - HTTP 202

Request body: `{"id":"pulse-001","action":"sensor.pulse","args":{"channel":1,"mv":5000,"duration_ms":2000}}`.

```json
{
  "api_version":"1", "id":"pulse-001", "ok":true, "status":"running",
  "result":{
    "id":"11111111111111111111111111111111",
    "channel":1, "mv":5000, "duration_ms":2000, "status":"running",
    "automatic":false, "timestamp":"2026-10-15T12:00:02+00:00",
    "deadline":1003.5
  },
  "error":null, "timestamp":"2026-10-15T12:00:02+00:00"
}
```

AUTO arming is a completed configuration action (HTTP200), not HTTP202.
HTTP rejects operation.wait and truthy wait arguments for sensor.pulse. Follow
the operation resource for completion. Closing an HTTP connection does not
implicitly stop the serial session or cancel other clients' outputs.

### POST Resource Conflict - HTTP 409

```json
{
  "api_version":"1", "id":"conflict-001", "ok":false, "status":"failed",
  "result":null,
  "error":{"code":"conflict","message":"Stop WM pulses before selecting steady HIGH.","outcome":"failed"},
  "timestamp":"2026-10-15T12:00:00+00:00"
}
```

Reusing a request ID with different arguments also returns conflict, with
message `Request id was already used for different arguments.`

### POST Validation Error - HTTP 400

```json
{
  "api_version":"1", "id":"invalid-001", "ok":false, "status":"failed",
  "result":null,
  "error":{"code":"validation","message":"channel must be 1..4.","outcome":"failed"},
  "timestamp":"2026-10-15T12:00:00+00:00"
}
```

### POST Serial Timeout - HTTP 504

```json
{
  "api_version":"1", "id":"timeout-001", "ok":false, "status":"unknown",
  "result":null,
  "error":{"code":"timeout","message":"No complete response to: toggle wm 1","outcome":"unknown"},
  "timestamp":"2026-10-15T12:00:00+00:00"
}
```

### POST Command While Disconnected - HTTP 409

```json
{
  "api_version":"1", "id":"disconnected-001", "ok":false, "status":"failed",
  "result":null,
  "error":{"code":"disconnected","message":"Connect to the tester; faults require reconnect.","outcome":"failed"},
  "timestamp":"2026-10-15T12:00:00+00:00"
}
```

### Additional HTTP Outcomes

| Error code | HTTP status |
| --- | --- |
| validation | 400 |
| forbidden | 403 |
| not_found | 404 |
| conflict, disconnected, cancelled | 409 |
| firmware, unsupported | 422 |
| internal | 500 |
| protocol | 502 |
| connection, dependency, busy, unsafe, reset | 503 |
| timeout | 504 |

Unsupported HTTP methods use the standard server's HTTP501 response and may
return HTML rather than a JSON envelope. Host must be `127.0.0.1:<port>` or
`localhost:<port>`; every Origin header is rejected. Body length is limited to
65536 bytes, Content-Length is required for POST, and chunked POST is rejected.
Request IDs are 1..128 characters. Unknown arguments are rejected by signature
binding. This is not a complete production-grade JSON/schema security boundary.

RemoteClient generates a new ID for each command, so repeating a remote-shell
command is not a retry-by-ID interface. For uncertain HTTP delivery, retain and
reuse the same ID/payload while its cache entry remains available. Neither
cache persistence nor durable exactly-once execution is guaranteed.

## Test Record

The last recorded automated execution passed all 43 tests using Python 3.12.
The implementation environment also had pyserial 3.5 installed. Syntax
compilation and editor diagnostics passed during the initial implementation.
The batch update reran the full suite against fake serial and loopback HTTP;
it did not perform hardware testing.

The current test inventory is:

| Test class | Passing test method names, with the common test_ prefix omitted |
| --- | --- |
| CoreTests (5) | scaling; bad_scaling; status; vin; import_has_no_gui_or_serial_side_effects |
| ClientTests (12) | connect_and_disconnect_safe; wm_idempotent_and_conflicts; configuration_does_not_send_commands; failed_sensor_sequence_cleanup; pulse_completion_and_cancel; timeout_echo_not_ack_and_no_retry; concurrent_wm_on; time_help; serial_loss_marks_outputs_unknown; status_snapshots_are_independent; failed_handshake_closes_without_claiming_safe; event_history_is_bounded_and_reports_gap |
| AutoTests (6) | vin_read_and_poll_selection; threshold_saturation_and_fifo; stale_and_fresh_retrigger; auto_forces_sampling_and_error_disarms; reset_invalidates_and_never_rearms; missing_completion_forces_sensor_off |
| CliTests (2) | grammar; shell_subprocess_no_hardware |
| HttpTests (18) | commands_duplicate_id_and_conflict; pulse_accepted_and_completed; validation_and_loopback; remote_cli_and_events; channel_batch_combines_vai_and_wm; channel_batch_prevalidates_every_command; channel_batch_conflict_stops_remaining_and_cleans_up; channel_batch_example_file; channel_batch_atomic_config_and_null_preservation; channel_batch_pulse_is_accepted_without_blocking; channel_batch_normalizes_integer_valued_floats; channel_batch_invalid_shapes_and_fields_have_no_side_effects; channel_batch_timeout_reports_unsafe_cleanup; channel_batch_duplicate_id_conflict; channel_batch_auto_enable_disable_and_null; channel_batch_auto_input_validation; channel_batch_auto_threshold_cancel_and_manual_transition; channel_batch_auto_duration_change_requires_disarm |

Serial traffic is generated by FakeSerial. HTTP tests use real ephemeral
loopback sockets, not physical serial. AUTO tests use a controllable host clock.
The simulator does not reproduce physical PWM calibration, electrical decay,
UART timing, power-up behavior or actual cable-driver behavior. No API test
opened a physical tester port or established voltage/pulse accuracy. Previously
documented calibration measurements are not new API hardware acceptance tests.

## Known Defects

The following are source-inspection findings. They remain unfixed in the code
baseline documented here and are not all covered by the passing test suite.

| Finding | Effect and operational guidance |
| --- | --- |
| Stale fault safety bookkeeping | _fault clears WM/supply/VIN and marks outputs unknown, but does not invalidate last_safe_off or observation timestamps. A read failure after verified OFF can leave last_safe_off=true. Disconnect can emit a verified_off event while also raising unsafe. Treat fault/outputs_known=false and unsafe errors as authoritative. |
| Legacy integer-valued float formatting | The legacy CLI/Python/id-action-args paths can accept 1.0 or 5000.0 without consistently normalizing before serial formatting. Use integer literals there. The new batch adapter normalizes its integer fields; this does not repair every legacy entry point. |
| SAFE_OFF has no reserved queue capacity or priority | The 32-slot admission limit includes executing and waiting operations. SAFE_OFF can return busy if full and cannot preempt a running command. It invalidates previously queued ordinary work but is not an emergency-stop guarantee. |
| Legacy scaling configuration can invalidate an existing automatic value | set_scaling stores endpoints without resolving the current automatic value immediately. A later ON/AUTO enable can fail. New batch Configure validates the merged final configuration before applying it, but legacy setters retain this limitation. |

Additional source-inspection risks, not independently reproduced runtime bugs:

- HTTP handlers are daemon threads; normal server teardown does not explicitly
  join all handlers or prevent every new action from an already accepted
  request during shutdown. Concurrent shutdown/connection ownership needs
  additional qualification.
- sensor_on returns a nested supply object shared with the internal cache;
  library callers should not mutate returned objects. Other snapshot paths
  use defensive copies, but this path is not covered by the snapshot test.
- A context-manager cleanup failure can mask an exception raised inside the
  with block. Preserve both failure causes in test-runner reporting.
- Extreme/malformed inputs, unusual firmware responses and response
  serialization are not comprehensively hardened. Passing validation tests
  do not establish exhaustive protocol or security robustness.

This is a known-findings list, not a claim that every possible bug has been
identified. Do not describe the tool as production-certified or physically
failsafe based on these tests.

## Operational Limitations

- Only one process may own the tester COM port. GUI migration to this API is
  not implemented; simultaneous direct GUI/server access is unsupported.
- No firmware identity/version or serial transaction IDs exist. A matching
  response syntax is compatibility evidence, not authenticated board identity.
- No automatic reconnect/replay/rearm occurs after fault. A lost connection can
  leave continuous WM outputs or steady HIGH active indefinitely.
- Pulse timing is polled by firmware and affected by command traffic. The host
  cycle limit is policy, not a measurement or timing guarantee. Stop/start can
  retain phase/history; system init is not a cold power-up reset.
- Supply voltage is open-loop calibrated. Requested mv, timer duty and an ACK
  are not measured output voltage. Physical OFF voltage/decay is unverified.
- The service is local IPv4 only: no remote bind, authentication, TLS or browser
  support. No production web-server deployment is included.
- Runtime state/configuration is in memory. Event history holds 2048 records;
  operations and HTTP IDs hold up to 1024 records. Eviction/restart can lose
  records and deduplication guarantees. Record events externally for long tests.
- No raw mutating passthrough, automatic file export, plots, persistent JSON
  configuration, WM5, legacy DAC controls, FLEX second port, Log Analyzer or
  functional valve-trigger operation is included.
- The default serial ACK timeout is 1.5 seconds, configurable only when creating
  TesterClient. HTTP commands do not accept a per-request timeout_ms field.
- GET status is cached. A successful GET operation can describe a failed
  operation. Check connection, timestamps, operation status and errors together.

## Hardware, Drivers And Wiring

Repository evidence: [Analog Input Integration](../ANALOG_INPUT_INTEGRATION.md),
[Board Pin Definitions](../Core/Inc/main.h),
[USART Configuration](../Core/Src/usart.c), and
[WM Trigger Validation](../WM1_WM4_TRIGGER_VALIDATION.md).
Older migration reports contain historical statements superseded by the
current firmware and newer integration/verification notes.

### PC Serial Interface

The tester command interface is USART2, TX on PD5 and RX on PD6, configured for
115200/8N1 without flow control. Use a voltage-compatible UART adapter, not
direct RS-232 voltage levels. Confirm actual board connector routing before
connecting adapter TX to tester RX, tester TX to adapter RX and common ground.
An MCU pin name does not identify a verified accessible connector pin.

The repository does not establish a required USB adapter model, VID/PID,
connector pin-number diagram or Windows driver package. Install the COM driver
appropriate to the actual adapter and confirm the port in Windows Device
Manager. Do not infer that ST-LINK VCP, FTDI, CH340 or CP210x is required from an
illustrative PORTS response. ST-LINK/CubeProgrammer may be relevant to flashing,
but flashing tools are not runtime dependencies of this API.

The adjacent Flex Lite project's USB CDC diagnostic console is a separate
interface. Do not select it merely because it appears as another COM port.
The API requires the tester firmware and Main Controller protocol.

### Analog Inputs And Sensor Supply

| Input / output function | MCU mapping / documented role |
| --- | --- |
| AI1 | PA5, ADC1 channel 10; PA5 is reserved for AI1, not DAC2 |
| AI2 | PA1, ADC1 channel 6 |
| AI3 | PC2, ADC3 channel 3 |
| AI4 | PC3, ADC3 channel 4 |
| VAI1 enable | PC7; control GPIO, not the analog output connector itself |
| VAI2 enable | PB9; control GPIO |
| VAI3 enable | PB8; control GPIO |
| VAI4 enable | PG2; control GPIO |
| Shared VSEN enable / PWM | PC6 / PC9 |
| WM1 / WM2 / WM3 / WM4 | PF8 / PE15 / PD11 / PD12 |

Apply sensor signals only through the board's conditioned 0..10V analog input
connectors, with common signal ground. Never apply 10V directly to an STM32
pin. A floating input is not a reliable zero. Firmware assumes a 2.5V reference
and 10kohm/3.3kohm divider; confirm the actual board revision and VREF+ wiring.
The integration notes assume R66 is unpopulated and warn against enabling the
internal reference buffer against an external VREF+ source. Nominal ADC full
scale 10.076V is not permission to exceed the specified 0..10V input range.

There is no verified connector-level VAI-to-AI loopback diagram in the inspected
repository. To exercise AUTO, provide a suitable known signal above 1V at the
matching conditioned AI input. Only connect a VAI output back to an AI input
after verifying connector mapping, voltage compatibility, grounding, load and
conditioning. A permitted 15000mV supply setpoint does not permit applying 15V
to a 0..10V input. Do not short UART TX/RX as a substitute for the tester:
an echo alone cannot satisfy the command/response handshake.

WM pulses use internal UART/application control; no external trigger is
required. Output connector polarity, level shifting and receiving-device
compatibility must be verified from the actual board schematic and hardware.
Measure physical waveforms with appropriate equipment before relying on timing
or electrical OFF behavior. None of these checks were performed by fake-serial
tests, and this documentation update does not change or flash firmware.