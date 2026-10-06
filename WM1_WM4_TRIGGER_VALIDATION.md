# WM1–WM4 Trigger Validation

Date: 2026-10-06. Scope: read-only investigation of the current STM32L496ZG firmware and CubeMX configuration, compared with the available STM32L476RG legacy project. Only this document was created. No firmware, GUI, GPIO, UART, FreeRTOS, timer, DMA, or CubeMX settings were changed. No board was flashed or instrumented during this step.

**Validation boundary:** configuration and execution paths are verified from source; physical signals are NOT VERIFIED. The existing successful build/ELF remains the baseline, not proof of hardware operation. This report supplements [WM1_WM4_MIGRATION_ANALYSIS.md](WM1_WM4_MIGRATION_ANALYSIS.md).

**Confirmed product requirement (2026-10-06 correction):** WM1-WM4 use internal application/UART control, not an external trigger or gate. `start wm n 1000` must start the selected output at approximately 1 Hz, 50 ms HIGH and 950 ms LOW; `stop wm n` stops it. EXTERNAL TRIGGER REQUIRED: NO. No external input, gate logic, GPIO interrupt, or hardware-interface extension is required or permitted for WM activation. Earlier conclusions treating absent external gates as migration blockers are superseded.

## Proven Shared Behavior

### What activates and generates the output

1. On normal startup, `MX_GPIO_Init()` initializes each WM output LOW. `App::Init()` sets all four software statuses to `Stopped`; they do not automatically run at power-up.
2. USART2 receives `start wm <id> <cycle_ms>`. `Comm::Task()` assembles the line, signals the command semaphore, and `App::Task()` consumes it through `Comm::ReceiveCommand()`.
3. `App::HandleCommand()` selects `_wmSim[id - 1]` and calls `SetStatus(Status::Started, cycleTimeMs)`. IDs 1..4 select the four outputs independently.
4. `App::ControlWaterMeters()` calls each `WaterMeterSimulator::Task(false)` in the default application task. In `Started`, the argument is ignored and pulses are free-running until another command changes the status.
5. `Task()` checks elapsed milliseconds from `Clock::GetTimeMsec()` and calls `Set(!_isHigh)` when the current phase has elapsed. `Set()` calls `HAL_GPIO_WritePin(_port, _pin, level)`.

Thus the current mechanism is **UART-enabled, free-running software GPIO pulse generation executed by the App task**. It is not hardware PWM, output compare, timer-generated GPIO output, a DMA waveform, or a GPIO interrupt-driven generator. The kernel tick provides a time reference; it does not autonomously toggle the WM pins. `HAL_GPIO_TogglePin()` is not used: the code explicitly writes the new level.

The execution architecture is unchanged:

```text
main() -> MX_GPIO_Init()/other peripheral initialization
       -> osKernelInitialize() -> MX_FREERTOS_Init() -> osKernelStart()
       -> StartDefaultTask() -> runAppTask() -> App::Instance().Task()
       -> ReceiveCommand() -> HandleCommand() -> SetStatus()
       -> ControlWaterMeters() -> WM.Task(false) -> Set()
       -> HAL_GPIO_WritePin(channel port, channel pin, level)
```

`Comm` is a separate normal-priority task for serial reception/echo. It does not independently toggle WM outputs. All four simulators execute sequentially within `defaultTask`, not in four dedicated WM tasks.

### Frequency, width, duty cycle, and software states

For a valid positive cycle `C` in milliseconds, without overflow in `C * 5`, the requested timing is:

$$
t_{HIGH} = \left\lfloor \frac{5C}{100} \right\rfloor\ \mathrm{ms},\quad
t_{LOW} = C - t_{HIGH},\quad
f_{nominal} = \frac{1000}{C}\ \mathrm{Hz},\quad
D_{HIGH} = \frac{t_{HIGH}}{C}.
$$

The constants request approximately **5% HIGH / 95% LOW**; integer rounding can change the exact ratio. Each channel receives its cycle over UART. The user-confirmed behavior for `start wm n 1000` is approximately 1 Hz, 50 ms HIGH, 950 ms LOW, 5% HIGH duty; this is now the validation target, not an inferred requirement.

Both projects configure `configTICK_RATE_HZ=1000`, so the time reference has 1 ms resolution. App normally waits up to 10 ticks for a command before polling the WMs. Serial work, mutex contention, scheduling and existing blocking UART transmission can delay edges. `Task()` switches only one phase per invocation. The requested timing above is not a measured frequency/width guarantee or an established jitter tolerance.

| State / operation | Proven effect |
|---|---|
| `Stopped` | No pulse-generation work in `Task()`; a transition from running to Stopped drives LOW |
| `start wm n C` -> `Started` | Free-running pulse scheduling, regardless of external input; fresh start begins LOW and waits the LOW phase |
| `stop wm n` -> `Stopped` | Stops channel n and drives LOW when changing from running state; prior cycle/count/resume history are retained |
| Legacy `trigger wm n C` / `Triggered` / `RunningTriggered` | Historical optional gated path, not part of the new product requirement; do not implement external activation or alter its code during documentation correction |
| `system init` -> `App::Init()` | Stops WMs and resets software time; invokes existing DAC setup; not a full pulse-count/resume-history reset |

The software variables controlling the waveform are `_status`, `_cycleTimeMs`, `_periodMs` (HIGH duration), `_isHigh`, `_tLastSwitch`, and the saved phase/resume fields. `_pulseCount` increments on rising edges but is not the timing source. Restart with a saved phase may restore HIGH or LOW immediately; fresh-start first-edge timing must not be assumed after an earlier stop/restart. Changing the period of an already Started channel resets the time reference without necessarily forcing LOW.

Cycle validation is incomplete: zero, negative-to-unsigned conversion, multiplication overflow, and sub-millisecond/too-short HIGH phases are not rejected by firmware. Do not use those inputs for the baseline bench test or assume they have valid nominal timing.

### Evidence

- [Application/App.cpp](Application/App.cpp#L14): channel binding, initialization, command state changes, and the controlling `wm.Task(false)` call.
- [Application/WaterMeterSimulator.cpp](Application/WaterMeterSimulator.cpp#L18) and [Application/WaterMeterSimulator.hpp](Application/WaterMeterSimulator.hpp): GPIO writes, 5/95 timing, statuses, and the gated state machine.
- [Application/Clock.cpp](Application/Clock.cpp), [Core/Inc/FreeRTOSConfig.h](Core/Inc/FreeRTOSConfig.h), [Core/Src/freertos.c](Core/Src/freertos.c): kernel timebase and task execution.
- [Core/Inc/main.h](Core/Inc/main.h#L60), [Core/Src/gpio.c](Core/Src/gpio.c#L43), [ONE PRO 3 TESTER.ioc](ONE%20PRO%203%20TESTER.ioc): actual pin assignments, generated modes and initial levels.
- [Core/Src/tim.c](Core/Src/tim.c), [Core/Src/dma.c](Core/Src/dma.c), [Core/Src/usart.c](Core/Src/usart.c), [Core/Src/stm32l4xx_it.c](Core/Src/stm32l4xx_it.c): timer, DMA and interrupt boundaries.

## WM1

- **Pin:** PF8/GPIOF, `WM_SIM_1_Pin = GPIO_PIN_8`; `_wmSim[0]`, logical ID 1.
- **Current configuration:** `.ioc` PF8 is locked `GPIO_Output`, label `WM_SIM_1`. Generated GPIO mode `GPIO_MODE_OUTPUT_PP`, push-pull output, `GPIO_NOPULL`, `GPIO_SPEED_FREQ_LOW`, initial `GPIO_PIN_RESET`/LOW. GPIOF clock is enabled. Alternate function: N/A; no AF is selected for WM1. Timer channel/clock: N/A for this output. WM DMA: none. WM pin interrupt: none. LOW is guaranteed by the initialization code after `MX_GPIO_Init()`, not throughout reset before that initialization.
- **Trigger source:** internal application/UART `start wm 1 C` via USART2. External trigger/gate is not required; no activation source is missing for the product requirement.
- **Output mechanism:** `App::HandleCommand()` -> `_wmSim[0].SetStatus(Started, C)` -> `ControlWaterMeters()` -> `Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, level)`. Software GPIO pulses; no PWM/OC channel, no waveform DMA.
- **Frequency:** command-dependent nominal `1000/C` Hz in Started; no configured fixed frequency. Test `start wm 1 1000` targets 1 Hz. Triggered/Stopped produce no periodic edges in the current App.
- **Pulse width:** requested HIGH `floor(C*5/100)` ms, LOW remainder; test targets 50 ms HIGH and 950 ms LOW, 5% HIGH duty. Actual timing unmeasured.
- **Idle state:** LOW after GPIO initialization; LOW when stopped/armed from a normal running-state transition.
- **Active state:** alternating MCU logic HIGH and LOW while Started. `_isHigh=true` requests `GPIO_PIN_SET`. Voltage and downstream active polarity are unknown.
- **Hardware verification:** NOT PERFORMED. Probe PF8 relative to verified board ground and execute the common bench procedure with channel ID 1. Expect the other three outputs to remain idle during the individual test.
- **Unknowns:** whether physical PF8 routing and measured timing match the expected waveform and legacy behavior; whether selected-channel start/stop and startup/reset are safe. External gate design is not an open question.

## WM2

- **Pin:** PE15/GPIOE, `WM_SIM_2_Pin = GPIO_PIN_15`; `_wmSim[1]`, logical ID 2.
- **Current configuration:** `.ioc` PE15 is locked `GPIO_Output`, label `WM_SIM_2`. Generated mode `GPIO_MODE_OUTPUT_PP`, push-pull, `GPIO_NOPULL`, `GPIO_SPEED_FREQ_LOW`; initial RESET/LOW. GPIOE clock enabled. AF: N/A; timer channel/clock: N/A; WM DMA: none; WM pin IRQ: none. Its grouped GPIO initialization with `V_SNS1_10K` does not make that separate output a trigger input.
- **Trigger source:** internal application/UART `start wm 2 C` activates free-running mode. No external input or gate is required or missing.
- **Output mechanism:** command selects `_wmSim[1]`; App task polls `Task(false)`; `Set()` writes PE15 with `HAL_GPIO_WritePin(GPIOE, GPIO_PIN_15, level)`. No hardware pulse generator.
- **Frequency:** nominal `1000/C` Hz when Started; `start wm 2 1000` targets 1 Hz. No boot-time fixed pulse frequency; Triggered remains idle.
- **Pulse width:** requested `floor(C*5/100)` ms HIGH; `C - HIGH` ms LOW; for the test, 50/950 ms, 5% HIGH duty. Measured values unknown.
- **Idle state:** LOW after `MX_GPIO_Init()` and on normal stop/arming transitions; reset-before-init state is not asserted by this report.
- **Active state:** alternating MCU logic HIGH/LOW; external electrical interpretation unverified.
- **Hardware verification:** NOT PERFORMED. Probe PE15, use ID 2 in the common procedure, and check PF8/PD11/PD12 do not start unexpectedly.
- **Unknowns:** whether PE15 routing, measured waveform/legacy timing parity, UART selection/start/stop, and startup/reset behavior pass verification.

## WM3

- **Pin:** PD11/GPIOD, `WM_SIM_3_Pin = GPIO_PIN_11`; `_wmSim[2]`, logical ID 3.
- **Current configuration:** `.ioc` PD11 is locked `GPIO_Output`, label `WM_SIM_3`. Generated mode `GPIO_MODE_OUTPUT_PP`, push-pull, `GPIO_NOPULL`, `GPIO_SPEED_FREQ_LOW`; initial RESET/LOW. GPIOD clock enabled. AF: N/A; WM timer channel/clock: N/A; waveform DMA: none; pin IRQ: none. PD11 shares the GPIO port with WM4 and UART pins, but each WM write uses its individual pin mask.
- **Trigger source:** internal application/UART `start wm 3 C` activates Started; no external gate is required or missing.
- **Output mechanism:** `_wmSim[2].SetStatus()` -> App task polling -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_11, level)`. Timer AF capabilities of PD11, if any, are not selected or used by this firmware.
- **Frequency:** Started target `1000/C` Hz; `start wm 3 1000` targets 1 Hz. No active waveform in Stopped or current gated Triggered mode.
- **Pulse width:** integer 5% HIGH request; test targets 50 ms HIGH, 950 ms LOW, 5% HIGH duty. Real width/jitter are not verified.
- **Idle state:** LOW after configured GPIO initialization and on normal stop/arming transitions.
- **Active state:** periodic MCU HIGH/LOW while Started; downstream active polarity and voltage unknown.
- **Hardware verification:** NOT PERFORMED. Probe PD11 with ID 3; monitor PD12 separately for cross-channel isolation if the analyzer supports it.
- **Unknowns:** whether PD11 routing, expected waveform and legacy timing parity, UART start/stop/isolation from PD12, and startup/reset behavior pass verification. Old PC2 remains unrelated to WM activation.

## WM4

- **Pin:** PD12/GPIOD, `WM_SIM_4_Pin = GPIO_PIN_12`; `_wmSim[3]`, logical ID 4.
- **Current configuration:** `.ioc` PD12 is locked `GPIO_Output`, label `WM_SIM_4`. Generated `GPIO_MODE_OUTPUT_PP`, push-pull, `GPIO_NOPULL`, `GPIO_SPEED_FREQ_LOW`; RESET/LOW initially. GPIOD clock enabled. AF: N/A; WM timer channel/clock: N/A; WM DMA: none; WM pin interrupt: none. No TIM4 or other timer output is selected merely because the physical pin may offer timer alternatives.
- **Trigger source:** internal application/UART `start wm 4 C` enters Started; no external gate is required or missing.
- **Output mechanism:** App task polls `_wmSim[3].Task(false)` and calls `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, level)`. Same software generator as WM1-WM3.
- **Frequency:** Started target `1000/C` Hz; the confirmed `start wm 4 1000` behavior is approximately 1 Hz.
- **Pulse width:** requested `floor(C*5/100)` ms HIGH; test 50 ms HIGH/950 ms LOW, 5% HIGH duty; physical measurements pending.
- **Idle state:** LOW after initialization and normal stop/arming transitions.
- **Active state:** alternating MCU logic HIGH/LOW while Started; no evidence establishing receiving-device active level.
- **Hardware verification:** NOT PERFORMED. Probe PD12 with ID 4 and check PD11 isolation. ID 5 is outside this firmware's accepted WM range.
- **Unknowns:** whether PD12 routing, measured waveform and legacy timing parity, UART-selected start/stop, and startup/reset behavior pass verification. No new activation hardware is needed.

## Product Activation and Legacy Comparison

The required source is already implemented for all four channels: UART command -> `App::HandleCommand()` -> selected WM `SetStatus(Started, C)` or `SetStatus(Stopped, 0)`. `Task(false)` does not inhibit the Started state. No external gate search, design, or implementation is needed.

The earlier source comparison found the same `WaterMeterSimulator.cpp` pulse implementation in both projects. Legacy free-running `start wm` behavior ignores the valve-state argument just as current Started behavior does. Preserve that software timing and command behavior; verify actual timing on the new CPU and under existing UART load.

| Logical WM | Legacy free-running pulse output | New output | Required control |
|---|---|---|---|
| WM1 | PC0, `WM_SIM_0` | PF8, `WM_SIM_1` | Internal/UART start/stop |
| WM2 | PC1, `WM_SIM_1` | PE15, `WM_SIM_2` | Internal/UART start/stop |
| WM3 | PC2, `WM_SIM_2` | PD11, `WM_SIM_3` | Internal/UART start/stop |
| WM4 | PC3, `WM_SIM_3` | PD12, `WM_SIM_4` | Internal/UART start/stop |

The old optional `trigger wm` command and valve-gated states remain historical code only. Their inactivity is not a migration blocker. Do not wire new inputs to them, change `Task(false)`, add GPIO interrupts, or modify the hardware interface.

Existing TIM3/TIM7 base timers and TIM8 CH4 PWM on PC9 are unrelated to these GPIO pulses; no timer remapping is required. SysTick provides the 1 kHz software time reference. Existing RX DMA/USART2 interrupts support UART communication, not external WM activation. Keep these configurations unchanged.

## Trigger Matrix

`C` is a valid positive, non-overflowing commanded cycle in milliseconds. Frequency/width values below are requests, not measurements. Test values use C=1000 only.

| WM | Pin | Trigger Source | Generation Method | Frequency | Pulse Width | Hardware Verified | Status |
|---|---|---|---|---|---|---|---|
| WM1 | PF8 | Internal/UART `start wm 1 C`; external trigger not required | App-task GPIO writes, not PWM/OC | Nominal 1000/C Hz; C=1000: approximately 1 Hz | HIGH floor(C*5/100) ms; C=1000: 50 ms | NO | Mapping/control implemented; waveform/start-stop/startup validation pending |
| WM2 | PE15 | Internal/UART `start wm 2 C`; external trigger not required | App-task GPIO writes | Same | Same | NO | Same |
| WM3 | PD11 | Internal/UART `start wm 3 C`; external trigger not required | App-task GPIO writes | Same | Same | NO | Same |
| WM4 | PD12 | Internal/UART `start wm 4 C`; external trigger not required | App-task GPIO writes | Same | Same | NO | Same |

## Minimal Unchanged-Firmware Bench Test

### Safety and instruments

- Verify physical test points and ground from the board schematic/connector documentation before probing. MCU signal names alone do not locate an accessible pad or establish that a connector carries the same polarity.
- Start with sensitive receiving hardware disconnected or safely isolated. Existing `App::Init()` enables legacy DAC outputs on PA4/PA5; new CubeMX assigns PA5 as a sensor ADC input. This independent startup side effect must be understood before connecting sensor loads; do not change it or assume it is safe here.
- Use a high-impedance oscilloscope probe with correctly rated/common ground, or a voltage-compatible logic analyzer. Confirm actual board I/O voltage and analyzer threshold/rating. Do not drive external signals into push-pull WM output pins. Do not assume 5 V compatibility.
- Use the existing verified ELF. Programming the board, if necessary, is a separate user-approved hardware action; it has not been done in this step. No firmware changes are required to issue existing start/stop commands.
- Serial command interface: USART2 RX PD6/TX PD5, AF7, 115200 baud, 8 data bits, no parity, 1 stop bit, no flow control. Use a compatible UART-level adapter, not direct RS-232 voltage levels. Terminate commands with CR, LF, or CRLF. Firmware echoes input; identify the acknowledgement after the echo.

### Per-channel test points and target observations

| WM | Probe | Command | Idle | Running MCU levels | Nominal test frequency | Nominal test HIGH/LOW | Expected stop |
|---|---|---|---|---|---|---|---|
| WM1 | PF8 relative to board ground | `start wm 1 1000` | LOW after initialization | HIGH then LOW repeatedly | 1 Hz | 50 ms / 950 ms, 5% HIGH | `stop wm 1`: LOW, no further periodic edges |
| WM2 | PE15 relative to board ground | `start wm 2 1000` | LOW after initialization | Same | 1 Hz | 50 ms / 950 ms | `stop wm 2`: LOW |
| WM3 | PD11 relative to board ground | `start wm 3 1000` | LOW after initialization | Same | 1 Hz | 50 ms / 950 ms | `stop wm 3`: LOW |
| WM4 | PD12 relative to board ground | `start wm 4 1000` | LOW after initialization | Same | 1 Hz | 50 ms / 950 ms | `stop wm 4`: LOW |

### Procedure for each WM

1. Boot the approved unchanged image with safe wiring. Check `App Started` and `get status`; confirm all four pins settle LOW after initialization. Begin individual tests before that channel has ever run since this boot, so saved resume state does not affect its first start.
2. Use only the required start/stop path for this baseline; do not send `trigger wm` or inject external activation signals. No firmware or GPIO configuration change is needed.
3. Send the matching `start wm n 1000`. Verify `wm n started` and `get status` reports channel n `started 1000ms`. Other stopped channels must remain LOW. Avoid repeated commands during the first timing capture.
4. On the oscilloscope, trigger on a rising edge and capture at least 10 rising-edge intervals; measure rise-to-rise period, HIGH width, LOW width, duty, and actual voltage. A timebase around 100-200 ms/div is a starting setup, not a requirement. Zoom in to inspect the HIGH interval and edge quality.
5. Alternatively, use a logic analyzer with a threshold selected for the verified I/O level. A proposed capture rate of at least 100 ksample/s and at least 10 seconds gives ample resolution for the 50 ms test HIGH phase; it does not prove analog voltage/rise quality. Measure intervals from recorded edges, not GUI animation.
6. For a fresh start, the code intends to begin LOW and rise after the 950 ms LOW phase. Command transport and scheduling affect observed latency from the PC timestamp. Measure inter-edge timing directly rather than requiring exactly 950 ms from serial write completion. On restart after stop, saved phase can change first-edge timing.
7. Send `stop wm n`, confirm `wm n stopped`, and observe LOW with no periodic edges for at least two test cycles. Stopping during HIGH should terminate that phase when the command is handled. Do not assume the response arrives at the exact moment of the GPIO change.
8. Repeat independently for n=1,2,3,4, using the pins above. Record trace files and min/mean/max period and HIGH width per channel. No numeric jitter pass limit can be assigned until the required tolerance is supplied. Missing waveform, wrong pin activation, failure to stop, or coupled channel activation contradicts the inspected implementation and should be investigated before editing.

After individual checks, an optional second capture can run all four at the same test cycle and apply ordinary serial traffic to expose scheduling sensitivity. Do not promise phase synchronization: commands and GPIO writes are sequential. A GUI-generated local 50% graph is not a measurement of the firmware's requested 5% output. No test in this report has been executed.

Also capture power-cycle/reset and `system init` behavior: outputs should return to the intended safe stopped condition with no unsolicited restart. Test stop during HIGH/LOW and restart with the same cycle, noting existing saved-phase behavior. Compare these observations with the intended startup/reset contract and legacy software behavior before proposing a source fix.

### Explicitly unverified assumptions

- **ASSUMPTION – NOT VERIFIED:** accessible board test points/connectors preserve the named MCU signal and are suitable for direct probing; require schematic/continuity confirmation.
- **ASSUMPTION – NOT VERIFIED:** receiver-side pulse polarity matches MCU HIGH; external drivers may invert it.
- **ASSUMPTION – NOT VERIFIED:** available bench equipment and external loads accept the actual output voltage; require supply/interface specifications or measurement.
- **ASSUMPTION – NOT VERIFIED:** real pulse timing meets the receiving device's tolerance under RTOS/serial load; require measured traces and acceptance criteria.

The 1000 ms command waveform is a confirmed product expectation. Instrument settings are test recommendations. External triggering is explicitly not required; no new timer or input mapping is proposed.

## Required Decisions

The activation requirement is settled: internal/UART start/stop only. Remaining verification questions are limited to:

1. Does the existing WM software operate correctly on the new STM32, independently for all four channels and under ordinary application/UART load?
2. Do physical outputs match WM1 PF8, WM2 PE15, WM3 PD11 and WM4 PD12? Verify accessible probe routing without modifying the hardware interface.
3. Does measured timing match the legacy free-running implementation and the confirmed approximately 1 Hz, 50 ms HIGH/950 ms LOW expectation for C=1000? If a numeric jitter tolerance is needed for acceptance, clarify it within this timing question.
4. Does `start wm n 1000` start only the selected WM, and does `stop wm n` stop it without affecting other channels?
5. Are startup, hardware reset, `system init`, and stop/restart behavior safe and consistent with the intended product contract, including retained phase/count state and existing PA4/PA5 DAC startup side effects? No source/configuration edit is authorized here.

No open question concerns an external trigger, gate input, new GPIO interrupt, or new hardware activation interface.

## Validation Summary

VALIDATION STATUS: COMPLETE FOR SOURCE/CONFIGURATION; PHYSICAL BENCH VALIDATION NOT PERFORMED

CODE CHANGED: NO; DOCUMENTATION ONLY

TRIGGER SOURCES FOUND: INTERNAL APPLICATION/UART START/STOP FOR ALL FOUR; NO EXTERNAL SOURCE REQUIRED

HARDWARE CONFIGURATION VERIFIED: YES FROM CUBEMX/GENERATED SOURCE; ALL FOUR GPIO OUTPUTS VERIFIED, PHYSICAL HARDWARE NOT VERIFIED

OPEN QUESTIONS: SOFTWARE OPERATION ON NEW STM32, PHYSICAL GPIO MAPPINGS, LEGACY TIMING PARITY, SELECTED-CHANNEL UART START/STOP, STARTUP/RESET SAFETY

EXTERNAL TRIGGER REQUIRED: NO

RECOMMENDED NEXT STEP: BENCH-VERIFY EXISTING-FIRMWARE UART START/STOP AT C=1000 ON PF8, PE15, PD11 AND PD12, THEN LEGACY TIMING PARITY AND STARTUP/RESET SAFETY; NO SOURCE CHANGES YET