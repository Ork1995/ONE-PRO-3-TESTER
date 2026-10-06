# WM1–WM4 Code Verification

Date: 2026-10-06. Analysis only. Only this requested report was created; no source, configuration, previous report, or build artifact was modified. No board programming, hardware capture, or firmware execution test was performed.

Product requirement: internal application/UART control only. `start wm n 1000` should run the selected output at approximately 1 Hz, 50 ms HIGH and 950 ms LOW; `stop wm n` stops that channel. **EXTERNAL TRIGGER REQUIRED: NO.** Historical optional valve-gated states are not missing product functionality and do not require implementation.

## 1. Overall Result

**CODE VERIFICATION: PARTIAL**

The inspected valid-command path, four GPIO mappings, 1000 ms timing arithmetic, and state/pin isolation pass source verification. The implementation is suitable for a controlled unchanged-firmware bench test, but cannot be described as universally correct or as guaranteeing exact physical pulse widths or reset electrical safety.

Reasons for PARTIAL rather than unconditional PASS:

- Pulse generation is polled by the application task, so scheduling and UART work can delay edges; 50/950 ms are scheduled durations, not measured guarantees.
- There are inherited real input-validation/overflow defects for malformed or out-of-range cycle commands. They do not invalidate the valid `1000` arithmetic.
- Stop/restart and `system init` retain phase/cycle/count history; they are not equivalent to a clean cold start.
- Software initializes output latches LOW before output mode and before tasks start, but source alone cannot prove connector voltage/no glitches during reset before initialization. Existing shared DAC initialization also needs board-safety consideration.

The last verified full build/link passed with 0 errors and 3 existing indentation warnings; the ELF already exists. This documentation-only verification did not rebuild or alter that baseline.

### Evidence and verification method

Conclusions follow executable statements, not explanatory comments. Current/legacy SHA-256 comparison found byte-identical `WaterMeterSimulator.cpp`, `WaterMeterSimulator.hpp`, `Clock.cpp`, `Comm.cpp`, `TextScanner.cpp`, and `BufferView.hpp`. Compiler predefined macros confirmed the installed ARM target has 4-byte `int`, `long`, and pointers. Arithmetic examples were evaluated without writing test code; they are not runtime or hardware tests.

| Evidence | Actual function / statement establishing the conclusion |
|---|---|
| [Core/Src/usart.c](Core/Src/usart.c#L32) | `MX_USART2_UART_Init()` sets USART2 115200/8N1; `HAL_UART_MspInit()` binds TX PD5/RX PD6 AF7 and circular RX DMA1_Channel6/request 2 |
| [Application/Board.cpp](Application/Board.cpp#L11) | `Board::Board()` constructs `_commUart { huart2 }` |
| [Application/Uart.cpp](Application/Uart.cpp#L23) | `Restart()` starts circular DMA; `Recv()` reads bytes using DMA CNDTR; `Send()` performs current blocking HAL transmit |
| [Application/Comm.cpp](Application/Comm.cpp#L30) | `Task()` accumulates a line, echoes it, sets `_isCmdReady`, releases semaphore; `ReceiveCommand()` copies and clears the pending command under mutex |
| [Application/TextScanner.cpp](Application/TextScanner.cpp#L18) | Token `operator>>` parses `start`/`wm`; numeric `operator>>(long&)` calls `strtol(token, &endPtr, 0)` |
| [Application/App.cpp](Application/App.cpp#L199) | `HandleCommand()` checks ID 1..4 and calls only `_wmSim[id - 1].SetStatus(Started, (uint32_t)cycleTimeMs)` |
| [Application/App.cpp](Application/App.cpp#L209) | Stop branch calls only `_wmSim[id - 1].SetStatus(Stopped, 0)` |
| [Application/App.cpp](Application/App.cpp#L14) | `App::App()` binds four separate instances to four port/pin macros and IDs 1..4 |
| [Application/WaterMeterSimulator.cpp](Application/WaterMeterSimulator.cpp#L38) | `SetStatus()` computes HIGH interval, stores cycle/state, sets initial/resumed phase and time reference |
| [Application/WaterMeterSimulator.cpp](Application/WaterMeterSimulator.cpp#L144) | `Task()` computes current phase and elapsed time, advances reference and calls `Set(!_isHigh)` |
| [Application/WaterMeterSimulator.cpp](Application/WaterMeterSimulator.cpp#L18) | `Set()` updates `_isHigh` and calls `HAL_GPIO_WritePin(_port, _pin, (GPIO_PinState)isHigh)` |
| [Drivers/STM32L4xx_HAL_Driver/Src/stm32l4xx_hal_gpio.c](Drivers/STM32L4xx_HAL_Driver/Src/stm32l4xx_hal_gpio.c#L427) | `HAL_GPIO_WritePin()` writes selected mask to BSRR for HIGH or BRR for LOW; it does not overwrite the whole port |
| [Core/Inc/main.h](Core/Inc/main.h#L60), [Core/Src/gpio.c](Core/Src/gpio.c#L43) | Actual pin definitions, initial RESET writes, port clocks, output mode/pull/speed |
| [Application/Clock.cpp](Application/Clock.cpp#L15), [Core/Inc/FreeRTOSConfig.h](Core/Inc/FreeRTOSConfig.h#L69) | Kernel ticks multiplied by `1000/configTICK_RATE_HZ`; rate 1000 Hz, `configUSE_16_BIT_TICKS=0` |
| [Core/Src/main.c](Core/Src/main.c#L99), [Core/Src/freertos.c](Core/Src/freertos.c#L116), [Application/appProxy.cpp](Application/appProxy.cpp#L6) | GPIO/peripheral setup precedes scheduler; default task calls C bridge then `App::Instance().Task()` |

## 2. WM1

- **UART command:** `start wm 1 1000` followed by CR, LF, or CRLF on USART2; expected acknowledgement `wm 1 started\r\n`. Reception is `Uart::Recv()` -> `Comm::Task()` -> `Comm::ReceiveCommand()`.
- **Parser:** `App::HandleCommand()` creates `TextScanner`; token extraction matches `start` and `wm`; `operator>>(long&)` obtains ID 1 and decimal cycle 1000. The actual ID guard is `!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT`, where count is 4.
- **Start function:** `_wmSim[0].SetStatus(WaterMeterSimulator::Status::Started, (uint32_t)1000)`, in [App.cpp](Application/App.cpp#L200). No separate WM1 start routine exists.
- **Timing mechanism:** `WaterMeterSimulator::SetStatus()` computes `_periodMs=50`, `_cycleTimeMs=1000`. On a fresh start it sets LOW and `_tLastSwitch=Clock::GetTimeMsec()`. `App::ControlWaterMeters()` polls this object's `Task(false)` from defaultTask; LOW phase is 950 ms and HIGH phase 50 ms. No WM timer/callback/PWM/DMA toggles PF8.
- **GPIO function:** `WaterMeterSimulator::Task()` -> `Set()` -> `HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, GPIO_PIN_SET/RESET)`. HIGH uses GPIOF BSRR; LOW uses GPIOF BRR with only bit 8 masked.
- **GPIO pin:** `_wmSim[0]` uses `WM_SIM_1_GPIO_Port=GPIOF`, `WM_SIM_1_Pin=GPIO_PIN_8`, ID 1. Actual output is PF8, matching expectation.
- **Stop function:** `stop wm 1` selects `_wmSim[0].SetStatus(Stopped, 0)` at [App.cpp](Application/App.cpp#L210). Started-to-Stopped transition saves phase, updates status, and calls `Set(false)`. Later `Task(false)` takes no pulse-generating branch for Stopped.
- **Startup behavior:** `MX_GPIO_Init()` writes PF8 RESET before its push-pull output initialization; tasks start later. Cold object initialization yields Stopped/LOW software state; no unsolicited PF8 HIGH is scheduled by startup code. Before GPIO initialization, electrical level is not proven by this source.
- **Legacy comparison:** old logical WM1 used PC0/`WM_SIM_0`, not old `WM_SIM_1`; the shared pulse implementation and valid start/stop command selection logic are unchanged. New output macro mapping intentionally selects PF8.
- **Issues:** no wrong pin/index found; shared polling jitter, input-validation, and restart/reset findings in section 12 apply. No external gate is required.

## 3. WM2

- **UART command:** `start wm 2 1000`; `Comm` assembles the line and `App::Task()` consumes it; response `wm 2 started\r\n`.
- **Parser:** same `App::HandleCommand()`/`TextScanner` path; ID 2 passes the 1..4 guard, maps to index `2 - 1 = 1`.
- **Start function:** `_wmSim[1].SetStatus(Started, 1000)`; only this object is reconfigured by the command.
- **Timing mechanism:** independent `_status`, `_cycleTimeMs=1000`, `_periodMs=50`, `_isHigh`, `_tLastSwitch`, and resume fields. Same defaultTask polling gives nominal 950 ms LOW/50 ms HIGH, approximately 1 Hz; actual scheduling intervals are not guaranteed.
- **GPIO function:** `Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOE, GPIO_PIN_15, level)`, with only bit 15 written.
- **GPIO pin:** [App::App()](Application/App.cpp#L18) binds `_wmSim[1]` to `WM_SIM_2_GPIO_Port=GPIOE`, `WM_SIM_2_Pin=GPIO_PIN_15`, ID 2; actual output PE15.
- **Stop function:** `stop wm 2` -> `_wmSim[1].SetStatus(Stopped, 0)`; transitioning from running forces PE15 LOW, leaves other object states unchanged.
- **Startup behavior:** `MX_GPIO_Init()` clears the PE15 latch in the GPIOE mask before output initialization. Grouping it with `V_SNS1_10K_Pin` only affects initial LOW setup, not later individual WM writes. Scheduler/App run afterward.
- **Legacy comparison:** old logical WM2 used PC1/`WM_SIM_1`; new mapping PE15 is correct. Shared timing/state/parser implementation matches legacy as detailed in section 11.
- **Issues:** no index/pin isolation defect found; shared section-12 findings apply. No external input is required.

## 4. WM3

- **UART command:** `start wm 3 1000`, assembled by `Comm::Task()` and parsed in `App::HandleCommand()`; acknowledgement `wm 3 started\r\n`.
- **Parser:** ID 3 and cycle 1000 are parsed as long; guarded ID maps to index 2.
- **Start function:** `_wmSim[2].SetStatus(Started, 1000)`; does not set WM4's status.
- **Timing mechanism:** own 1000/50 ms cycle/HIGH fields, own phase/reference; polled as the third simulator in `App::ControlWaterMeters()` from defaultTask. Scheduled LOW/HIGH are 950/50 ms; no pin timer AF or interrupt generator.
- **GPIO function:** `WaterMeterSimulator::Task()` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_11, level)`. GPIOD BSRR/BRR bit 11 writes cannot set/reset bit 12 merely because it shares the port.
- **GPIO pin:** [App::App()](Application/App.cpp#L19) binds `_wmSim[2]` to `WM_SIM_3_GPIO_Port=GPIOD`, `WM_SIM_3_Pin=GPIO_PIN_11`, ID 3; actual PD11.
- **Stop function:** `stop wm 3` selects index 2 -> `SetStatus(Stopped, 0)` -> `Set(false)` on running-to-stopped transition; only PD11 is driven LOW.
- **Startup behavior:** `MX_GPIO_Init()` initially clears PD11 and PD12 together, then configures their output modes before scheduler startup. After startup, WM3 writes only PD11. No code makes it run without a start command.
- **Legacy comparison:** old WM3 used PC2/`WM_SIM_2`; new PD11 is correct. Old PC2 is now a sensor input in the new configuration, not a pulse output to restore.
- **Issues:** no shared-port corruption found. The common task can delay all running channels while handling a command; that is timing coupling, not unintended WM4 activation. Shared risks in section 12 apply.

## 5. WM4

- **UART command:** `start wm 4 1000`; `Uart::Recv()` -> `Comm::Task()` -> App parsing; acknowledgement `wm 4 started\r\n`.
- **Parser:** ID 4 passes the guard and maps to index 3, the last valid array element. ID 5 is rejected in the migrated project.
- **Start function:** `_wmSim[3].SetStatus(Started, 1000)`; no other channel's state is assigned.
- **Timing mechanism:** independent `_cycleTimeMs=1000`, `_periodMs=50`, phase/reference in the shared fourth polling call. Nominal 950 ms LOW/50 ms HIGH, approximately 1 Hz; no dedicated task/timer callback or hardware PWM.
- **GPIO function:** `Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, level)`; pin-mask BSRR/BRR writes leave PD11 unchanged.
- **GPIO pin:** [App::App()](Application/App.cpp#L20) binds index 3 to `WM_SIM_4_GPIO_Port=GPIOD`, `WM_SIM_4_Pin=GPIO_PIN_12`, ID 4; actual PD12.
- **Stop function:** `stop wm 4` -> index 3 -> `SetStatus(Stopped, 0)` -> LOW on the transition; stopped state prevents subsequent periodic writes.
- **Startup behavior:** PD12 output latch is cleared before GPIO output mode and before scheduler/App startup; no normal startup HIGH path exists before an accepted start command.
- **Legacy comparison:** old WM4 used PC3/`WM_SIM_3`; new PD12 is correct. Current simulator arithmetic/state implementation matches the old one; physical scheduling parity is still to be measured.
- **Issues:** no index/mask conflict found. Shared section-12 issues apply; no external activation mechanism is needed.

## 6. Execution Flow

### Common reception, parsing and execution

```text
USART2 RX PD6 / DMA1_Channel6 circular buffer
 -> Board::_commUart (huart2)
 -> Uart::Recv(&rxByte, 1) [reads DMA CNDTR and buffer byte]
 -> Comm::Task() [_cmd.Append(byte); line ending sets _isCmdReady]
 -> osSemaphoreRelease(_cmdReady)
 -> App::Task() -> Comm::ReceiveCommand(cmdBuf, 10)
 -> osSemaphoreAcquire() -> mutex -> copy _cmd -> clear pending command
 -> App::HandleCommand(cmdBuf)
 -> TextScanner::operator>>(BufferView<char>&) ["start", "wm"]
 -> TextScanner::operator>>(long&) [id, cycleTimeMs]
 -> ID guard 1..4 -> _wmSim[id - 1].SetStatus(Started, 1000)
 -> response "wm n started\r\n"
 -> Comm::SendResponse() -> Uart::Send() -> HAL_UART_Transmit() -> PD5
 -> App::ControlWaterMeters() -> each simulator.Task(false)
 -> elapsed kernel milliseconds meet current phase
 -> Set(!_isHigh) -> HAL_GPIO_WritePin(selected port, selected pin, level)
```

The start acknowledgement is sent before the next `ControlWaterMeters()` call, but the selected software state/initial LOW write was already performed by `SetStatus()`. An acknowledgement is not physical edge telemetry.

### Channel-specific final paths

| WM | Parsed command -> exact selected state call | Timing -> physical write |
|---|---|---|
| WM1 | `start wm 1 1000` -> ID 1 -> `_wmSim[0].SetStatus(Started, 1000)` | `_wmSim[0].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, level)` -> PF8 |
| WM2 | `start wm 2 1000` -> ID 2 -> `_wmSim[1].SetStatus(Started, 1000)` | `_wmSim[1].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOE, GPIO_PIN_15, level)` -> PE15 |
| WM3 | `start wm 3 1000` -> ID 3 -> `_wmSim[2].SetStatus(Started, 1000)` | `_wmSim[2].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_11, level)` -> PD11 |
| WM4 | `start wm 4 1000` -> ID 4 -> `_wmSim[3].SetStatus(Started, 1000)` | `_wmSim[3].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, level)` -> PD12 |

Stop follows the same reception/parser path but parses only the ID and selects `SetStatus(Stopped, 0)`. `system init` intentionally uses a loop over all channels; it is not the single-channel stop path.

## 7. GPIO Mapping

| WM | Expected Pin | Actual Code Pin | Status |
|---|---|---|---|
| WM1 | PF8 | index 0, ID 1, GPIOF + GPIO_PIN_8 (mask 0x0100) | PASS |
| WM2 | PE15 | index 1, ID 2, GPIOE + GPIO_PIN_15 (mask 0x8000) | PASS |
| WM3 | PD11 | index 2, ID 3, GPIOD + GPIO_PIN_11 (mask 0x0800) | PASS |
| WM4 | PD12 | index 3, ID 4, GPIOD + GPIO_PIN_12 (mask 0x1000) | PASS |

Three sources agree: `App::App()` binding, generated `main.h` port/pin values, and [ONE PRO 3 TESTER.ioc](ONE%20PRO%203%20TESTER.ioc) labels/signals. `MX_GPIO_Init()` configures all four as `GPIO_MODE_OUTPUT_PP`, `GPIO_NOPULL`, `GPIO_SPEED_FREQ_LOW`, initial RESET. No WM alternate function, PWM/output-compare channel, waveform DMA, or pin IRQ is selected.

`_pin` is stored as int but all masks fit the HAL uint16_t argument, including PE15 mask 32768. Boolean false/true converted to `GPIO_PinState` corresponds to HAL RESET=0 and SET=1. No signed-pin overflow or wrong-port write was found.

Physical connector mapping/voltage are not verified by these source agreements.

## 8. Timing Verification

### Actual arithmetic for 1000

`TextScanner::operator>>(long&)` calls `strtol(..., 0)`. The literal `1000` has no leading-zero/hex prefix and parses as decimal 1000. `HandleCommand()` converts that positive long to uint32_t without changing its value. In `SetStatus()`:

```text
onTimeMs = 1000 * 5 / 100 = 50
newPeriodMs = 50
_cycleTimeMs = 1000
_periodMs = 50
```

The variable `_periodMs` holds HIGH width, not full period. In `Task()`:

```text
onTimeMs = _periodMs = 50
offTimeMs = _cycleTimeMs - _periodMs = 950
currentPhaseMs = _isHigh ? 50 : 950
if (tNow - _tLastSwitch >= currentPhaseMs):
    _tLastSwitch += currentPhaseMs
    Set(!_isHigh)
```

On a fresh start LOW with reference T, ideal polling at deadlines yields HIGH at T+950, LOW at T+1000, next HIGH at T+1950. Rise-to-rise interval is 1000 ms. Thus:

$$f_{nominal}=\frac{1000}{1000}=1\ \mathrm{Hz},\qquad D_{HIGH}=\frac{50}{1000}=5\%.$$

These calculations come from statements actually used by `Task()`, not the comment or unused `offTimeMs` local in `SetStatus()`.

| WM | Command | Period | HIGH | LOW | Frequency | Status |
|---|---|---|---|---|---|---|
| WM1 | `start wm 1 1000` | 1000 ms | 50 ms scheduled | 950 ms scheduled | Approximately 1 Hz target | Arithmetic PASS; physical timing pending |
| WM2 | `start wm 2 1000` | 1000 ms | 50 ms scheduled | 950 ms scheduled | Same | Same |
| WM3 | `start wm 3 1000` | 1000 ms | 50 ms scheduled | 950 ms scheduled | Same | Same |
| WM4 | `start wm 4 1000` | 1000 ms | 50 ms scheduled | 950 ms scheduled | Same | Same |

### Task, ticks and limits

- [freertos.c](Core/Src/freertos.c): `MX_FREERTOS_Init()` creates normal-priority defaultTask with 2048-byte stack; `StartDefaultTask()` calls `runAppTask()`.
- [appProxy.cpp](Application/appProxy.cpp): `runAppTask()` calls `App::Instance().Task()`; its loop calls `ControlWaterMeters()` after command handling or timeout. There is no WM RTOS software timer or timing callback.
- [Clock.cpp](Application/Clock.cpp): `GetTimeMsec()` returns `osKernelGetTickCount() * (1000 / configTICK_RATE_HZ)`. Current rate is 1000; multiplier is exactly 1. Therefore 1000 means 1000 ms, not 1000 seconds or a CPU clock count.
- `ReceiveCommand(..., 10)` passes 10 directly to `osSemaphoreAcquire()` (ticks, despite the parameter name `timeoutMs`). At the current rate this is 10 ms, so no present tick/ms mismatch is found. It is a timeout, not a fixed periodic WM schedule.
- FreeRTOS uses 32-bit ticks; `_tLastSwitch`/`tNow`/phase fields are uint32_t. Unsigned elapsed subtraction supports ordinary single-wrap timing at a 1000 ms interval; no rollover defect is demonstrated for that normal case. It is not proof for delays spanning whole tick-counter cycles.
- Polling deadlines, command processing, mutex waits and UART blocking TX can delay transitions. One phase is processed per call; preserving the scheduled reference reduces accumulated ideal-period drift but cannot synthesize missed historical physical edges.
- Example proving the limitation: if the first poll after fresh start is at T+1000 instead of T+950, it sets HIGH late, then the next poll can set LOW because the stored deadline is already T+1000. The physical HIGH need not last 50 ms. This follows from the scheduled reference increment, not a hardware measurement.

## 9. Start/Stop Isolation

**State and pin isolation: PASS for correctly received valid commands.**

1. `WM_SIM_COUNT=4` in [App.hpp](Application/App.hpp#L26); the ID guard precedes array access in both start and stop branches.
2. Exactly one object is selected by `_wmSim[id - 1]`. State/configuration fields are per-instance, not static/shared.
3. `SetStatus()` accesses only that object's fields and `_port`/`_pin`; it does not iterate other WMs.
4. `Set()` sends only that object's one-bit mask to `HAL_GPIO_WritePin()`, whose BSRR/BRR writes affect selected bits only. PD11/PD12 sharing GPIOD does not introduce whole-port read/modify/write corruption.
5. Although `ControlWaterMeters()` polls all four, other Stopped instances do not enter pulse-generating branches. An already Started different channel continues normally; continuing is not accidental activation.
6. `Comm` supplies commands but does not mutate WM objects. Current start/stop and waveform state mutation are owned by App/defaultTask, so no second WM task/ISR races those state changes in the inspected path.

| Command pair | Selected object/pin | Other channel statuses | Result |
|---|---|---|---|
| `start/stop wm 1` | index 0 / PF8 | Not changed | PASS |
| `start/stop wm 2` | index 1 / PE15 | Not changed | PASS |
| `start/stop wm 3` | index 2 / PD11 | Not changed | PASS |
| `start/stop wm 4` | index 3 / PD12 | Not changed | PASS |

This is not a guarantee of timing independence: all channels share the same task, and response work for one channel can delay physical edges on the others. It also assumes successfully received input; the source has no complete serial-overrun/command-corruption guarantee under arbitrary traffic.

`SetStatus(Stopped, 0)` from Started immediately drives the selected pin LOW when handled, regardless of whether it was HIGH or LOW. It saves the prior remaining phase, updates `_status`, and preserves the old cycle when argument 0 is passed. Repeated stop on an already Stopped object does not necessarily issue another GPIO write; the normal stopped invariant is already LOW. No later periodic edge occurs unless a subsequent command starts it. Command-arrival-to-stop latency is not fixed.

## 10. Startup/Reset Safety

### Normal cold-start sequence, proven from source

1. [main.c](Core/Src/main.c) calls HAL/clock setup, then `MX_GPIO_Init()` before DMA/UART/other peripheral setup, `osKernelInitialize()`, `MX_FREERTOS_Init()` and `osKernelStart()`.
2. [gpio.c](Core/Src/gpio.c) enables GPIOF/GPIOE/GPIOD clocks and writes WM latch masks RESET before calling `HAL_GPIO_Init()` for output push-pull mode. Thus switching to output mode uses an already LOW output latch; the code does not first set a HIGH latch.
3. The generated timer/ADC/UART configurations do not reassign the WM pins; they have no WM output AF or start callback.
4. [App.hpp](Application/App.hpp) uses function-local `static App _instance`; App construction occurs on the default task's first call through `runAppTask()`, after all GPIO initialization. Each `_wmSim` aggregate initializes its specified port/pin/ID; omitted scalar members are zero-initialized, and explicit defaults initialize count/resume flags. `Status::Stopped` is the first enumerator (value 0), `_isHigh=false`, and cycle/phase/reference begin at zero. There is no initial random Started state in this construction.
5. [App.cpp](Application/App.cpp), `App::Task()`, runs `Init()` before processing any received command. `Init()` calls `SetStatus(Stopped, 0)` for all four. On an already Stopped fresh object, `SetStatus()` may perform no LOW write because status and period are unchanged; hardware LOW at this point is established by `MX_GPIO_Init()`, not by an assumed unconditional `Set(false)` in App initialization.
6. Comm's constructor creates its receive task, but that task does not activate WM hardware. Buffered commands are handled only after App initialization. Under no start command, Stopped `Task(false)` never raises a WM pin. No software-generated unsolicited WM pulse was found in this normal startup path.

### Limits and software reset distinctions

- **All four initialized LOW: PASS after GPIO initialization. GPIO configured before WM execution: PASS.**
- **No unwanted pulse throughout physical reset/power-up: NOT PROVEN.** Before this initialization executes, firmware does not actively establish these connector levels; boot path, external circuitry and power/reset electrical behavior require a trace. This is a verification limit, not evidence that a glitch occurs.
- Hardware reset/cold boot reconstructs the software object; `system init` does not. `App::Init()` sets Stopped but does not clear `_pulseCount`, `_cycleTimeMs`, `_hasResumeState` or the saved phase. A later start with the same period may resume HIGH immediately rather than repeat a full initial LOW interval. This follows from `SetStatus()` and must be compared with the intended product reset contract.
- `App::Init()` stops all WMs intentionally; this all-channel behavior must not be confused with isolated `stop wm n`.
- Existing [DacControl.cpp](Application/DacControl.cpp), `DacControl::Init()`, enables DAC1 and analog PA4/PA5; App initialization invokes it and writes both DAC values to zero. New CubeMX assigns PA5 to `SENS1_INP_ADC`. It does not overlap WM output pins, but board-wide startup/reset electrical safety cannot be approved solely from WM code. Do not attach sensitive affected loads without reviewing that existing condition.
- A host sending a valid start command during boot may have it buffered and handled after initialization. A fresh boot is not an instruction to discard all host commands. For idle startup capture, keep the serial host from automatically sending starts.

## 11. Legacy Comparison

| Component / behavior | Legacy | Current migrated code | Result |
|---|---|---|---|
| Pulse state machine and fields | `WaterMeterSimulator.cpp/.hpp` | Byte-identical SHA-256 | Software algorithm parity PASS, including inherited limitations |
| Kernel-clock conversion | `Clock.cpp`, 1000 Hz ticks | Byte-identical source, rate still 1000 Hz | Millisecond-unit parity PASS |
| Line assembly, command semaphore/mutex | `Comm.cpp` | Byte-identical SHA-256 | Receiver logic parity PASS |
| Numeric parsing and BufferView | `TextScanner.cpp`, `BufferView.hpp` | Byte-identical SHA-256 | Parser behavior parity PASS, not proof of robust malformed-input handling |
| Valid start/stop selection | `id - 1`, range check, SetStatus calls | Same function logic, count now 4 | WM1-WM4 command semantics PASS |
| Output pins for logical 1..4 | PC0/PC1/PC2/PC3 via labels `WM_SIM_0..3` | PF8/PE15/PD11/PD12 via `WM_SIM_1..4` | Intentional correct remap, no off-by-one found |
| Channel count | 5 WM objects | 4 objects | Intentional product scope; old ID 5 rejected |
| CPU clock | 80 MHz | 32 MHz | Does not change clock conversion, but execution latency needs measurement |
| UART pins | USART2 PA2/PA3 AF7 | USART2 PD5/PD6 AF7 | Intentional hardware remap; baud remains 115200/8N1 |
| UART transmission | Copy into `_txBuffer`, `HAL_UART_Transmit_DMA()`; TX DMA configured | `HAL_UART_Transmit(..., txBuf.begin(), ..., 100)`; no TX DMA configured | Existing migration difference can change polling latency; no edit made here |
| RX DMA | DMA1_Channel6/request 2, circular | Same receive mechanism | Compatible source/config path; runtime success not established here |
| Legacy valve polling | App samples valves before WM loop; optional gated states | Removed from App; WMs receive false argument | Not a defect for Started/free-running product behavior; no external gating required |
| Status text | Valve bitmap + five WM states | `wm status` + four WM states | Existing protocol/status difference; not a reason to restore valve hardware |
| HAL tick servicing | TIM6 HAL timebase | SysTick advances HAL and kernel tick | Different timeout servicing; WM scheduling still uses kernel ticks |
| Startup DAC code | PA4/PA5 DAC outputs on old board | Same App-side DAC use despite new PA5 sensor assignment | Board startup-safety review remains necessary; not a WM pin conflict |

Legacy App evidence: [App.cpp initialization](../FlexTesterRepo/Nucleo/Application/App.cpp#L35) and [start/stop selection](../FlexTesterRepo/Nucleo/Application/App.cpp#L256). Physical waveform parity is PARTIAL until measured: identical simulator source does not eliminate differing polling work, UART blocking time and CPU execution latency.

## 12. Bugs / Risks

Only findings supported by inspected statements are listed. No incorrect WM port/pin mapping, valid-ID off-by-one, current 1000 Hz tick conversion defect, or unwanted cross-channel state assignment was found.

| Finding | Evidence / concrete effect | Classification / scope |
|---|---|---|
| Zero/negative cycle accepted | `App::HandleCommand()` checks ID but not cycle. Zero on first start leaves `_cycleTimeMs/_periodMs=0`; `Task()` can toggle once per poll with zero phase deadlines. Negative long converts to uint32_t | Inherited input-validation bug; valid 1000 command unaffected |
| 32-bit multiplication overflow | `SetStatus()` evaluates uint32_t `cycleTimeMs * 5` before division. Parsed positive C=858993460 is representable by target long; product wraps to 4, yielding HIGH=0 instead of about 42949673 ms | Inherited arithmetic/input-bound bug; 1000*5 is safely 5000 |
| Very short requested HIGH becomes zero or unachievable | Integer division gives HIGH=0 for positive C<20; even positive short HIGH durations can fall between App polling opportunities | Inherited timing/input-range limitation; bench target C=1000 is nonzero and reasonable to measure |
| Parser does not enforce full valid numeric token or detect ERANGE | `TextScanner::operator>>(long&)` uses `strtol(..., 0)` and only tests whether any conversion occurred. Trailing numeric junk is not rejected by App; leading zero uses octal semantics (e.g. `01000` is 512, unlike `1000`) | Inherited parser limitation; use exact decimal command for baseline |
| Overlong numeric token can lose its terminator | Numeric parsing uses `Buffer<30>`; `Append()` drops bytes at capacity. Thirty stored numeric characters leave no room for appended NUL, but `strtol` receives the buffer pointer anyway | Inherited malformed-input memory-safety risk; do not send oversized test tokens |
| Polling can shorten/stretch physical phases after delayed service | `Task()` advances one scheduled phase per call, not a hardware edge deadline; App calls it after waits/command work. Current `Uart::Send()` blocks for readiness/transmit; Comm response/echo locking can stall App | Shared scheduling limitation; latency differs from legacy TX DMA; actual timing requires bench capture |
| Restart/software init are not fresh-reset operations | `SetStatus()` retains cycle and saved phase on stop; `App::Init()` does not clear count/history. Same-cycle restart can restore a saved HIGH phase immediately; repeated `start` while already Started does not necessarily reset phase | Inherited state semantics, not automatically a defect without the product reset contract; requires verification |
| Pulse-count signed overflow has no policy | `_pulseCount` is int (32-bit target) and `Task()` uses `_pulseCount++`; direct start/stop/system init do not reset it | Inherited long-run risk after INT_MAX rising edges; not a short 1 Hz bench blocker |
| UART/runtime setup success is not checked by the application | `_rxDmaStatus` stores HAL result without an App check; Comm creates semaphore/mutex/thread without checking returned handles; `_uart.Send()` result is ignored by Comm | Commands/responses can fail under setup/allocation/UART faults; source cannot prove live communication |
| RX backlog can be overwritten without a WM-command delivery guarantee | `Uart::Recv()` tracks DMA CNDTR only; it does not detect whole-ring overwrite. `Comm` holds one pending command and delays receiving while it is pending | Existing shared reception risk under excess traffic; not an array mapping defect for correctly received commands |
| Pre-initialization electrical safety and startup DAC ownership are not settled by WM logic | `main()` configures WM LOW only when GPIO initialization runs; `App::Init()` invokes direct DAC setup on PA5 assigned to sensor ADC in CubeMX | Startup/reset verification limit and existing board-level side effect; isolated/high-impedance bench precautions required |

No source fix is authorized by this report. The findings are not permission to fix multiple shared modules, redesign UART/RTOS, alter pin configuration, or add external gates. First collect the controlled baseline; propose a separate minimal fix only for an approved, demonstrated requirement failure.

## 13. Conclusion

**Ready for physical bench testing: YES, for a controlled unchanged-firmware start/stop baseline.** This is not production acceptance or an unconditional startup/timing safety certification.

Use the existing ELF with approved safe wiring and high-impedance probes; keep sensitive board loads isolated as appropriate. For each n=1..4, issue the exact decimal `start wm n 1000`, measure the mapped MCU output against approximately 1 Hz/50 ms HIGH/950 ms LOW, then `stop wm n` and confirm LOW with no later edges. Check other channels remain in their previous states. Begin a fresh-start timing capture before that channel has run since boot, because later restarts can resume phase.

Then capture startup/reset, `system init`, restart at HIGH/LOW phases, and concurrent running under ordinary UART traffic. Use real traces, not GUI-generated pulse graphs. Do not use malformed/zero/negative/overlong cycle inputs for a connected-hardware baseline. No external gate, GPIO interrupt, new timer or DMA waveform path is required.

The previous [migration analysis](WM1_WM4_MIGRATION_ANALYSIS.md) and [validation procedure](WM1_WM4_TRIGGER_VALIDATION.md) remain the supporting documents; this report gives the current source-level qualification and inherited risks, not new firmware changes.

CODE VERIFICATION: PARTIAL

WM1: VALID-COMMAND PATH PASS; PF8; PHYSICAL TIMING/RESET TEST PENDING

WM2: VALID-COMMAND PATH PASS; PE15; PHYSICAL TIMING/RESET TEST PENDING

WM3: VALID-COMMAND PATH PASS; PD11; PHYSICAL TIMING/RESET TEST PENDING

WM4: VALID-COMMAND PATH PASS; PD12; PHYSICAL TIMING/RESET TEST PENDING

GPIO MAPPING: PASS FOR ALL FOUR IN SOURCE/CONFIGURATION

TIMING LOGIC: PASS FOR 1000 MS ARITHMETIC; PHYSICAL SCHEDULING PARTIAL; INVALID-INPUT RISKS DOCUMENTED

START/STOP: PASS FOR VALID-COMMAND STATE/PIN ISOLATION; RESTART RETAINS PHASE

STARTUP SAFETY: PARTIAL; LOW INITIALIZED BEFORE TASKS, PRE-INIT ELECTRICAL LEVELS AND RESET CONTRACT REQUIRE VERIFICATION

LEGACY PARITY: SHARED ALGORITHM/PARSER SOURCES IDENTICAL; RUNTIME TIMING PARITY PARTIAL DUE TO EXISTING TRANSPORT/CLOCK DIFFERENCES

CODE CHANGED: NO

READY FOR HARDWARE TEST: YES