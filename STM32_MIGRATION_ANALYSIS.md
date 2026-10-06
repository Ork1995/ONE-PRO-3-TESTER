# ONE PRO 3 TESTER – MIGRATION ANALYSIS

Status: analysis only. No source code changes, no valve removal, and no Git commit have been executed yet. This analysis is the review document to approve before migration work begins.

---

## 1. Project architecture

This project is a tester firmware built around an STM32L496 microcontroller and a CubeMX-generated C/C++ application. The intended architecture is:

```
PC GUI / Python terminal
   ↓
Serial command stream (UART)
   ↓
STM32 USART2
   ↓
Application layer (C++ in Application/)
   ↓
Hardware abstraction (GPIO, UART, timers, ADC, DAC)
   ↓
MCU peripherals and board I/O
```

The existing `Application/` code is a reusable command-driven firmware layer that was originally designed around a board with:

- 16 valve inputs
- 5 water-meter pulse outputs
- 5 static outputs
- DAC outputs
- a plain text CLI over UART

The new CubeMX project is materially different:

- There are no valve pins in the `.ioc` or generated headers.
- There are no 16 valve GPIO definitions.
- The WM outputs are now only four simulator outputs named `WM_SIM_1` ... `WM_SIM_4`.
- UART is on `USART2` with a different pin map.
- The code still contains the old valve and WM model and therefore must be migrated to the new board mapping.

---

## 2. New MCU configuration

### MCU and clocking

- MCU: `STM32L496Z(E-G)Tx`
- Package: `LQFP144`
- Core: STM32L4
- Clock source: HSE + PLL, with ADC common clock configured through PLLSAI2.

### UART configuration

Derived from `Core/Src/usart.c` and `ONE PRO 3 TESTER.ioc`:

- Peripheral: `USART2`
- TX pin: `PD5`
- RX pin: `PD6`
- GPIO alternate function: `AF7` (USART2)
- Baud rate: `115200`
- Word length: `8 bits`
- Stop bits: `1`
- Parity: `none`
- Flow control: `none`
- Mode: `TX + RX`
- RX DMA: `DMA1_Channel6` in circular mode
- DMA request: `DMA_REQUEST_2`
- RX DMA configuration: `DMA_PERIPH_TO_MEMORY`, `MEM_INC_ENABLE`, `PINC_DISABLE`, byte alignment, circular
- Interrupts enabled: `USART2_IRQn` and `DMA1_Channel6_IRQn`
- `Uart::Restart()` calls `HAL_UART_Receive_DMA()` and expects a circular DMA receiver.

Important mismatch:

- The current generated code only enables DMA for RX.
- The application still calls `HAL_UART_Transmit_DMA()` in `Uart::Send()`.
- The generated `.ioc`/`usart.c` does not configure a TX DMA channel, so the current UART abstraction is not fully aligned with the actual CubeMX configuration.

### GPIO / pin map relevant to the tester

| Function | MCU pin | Peripheral | Direction | Status |
|---|---|---|---|---|
| WM1 / `WM_SIM_1` | `PF8` | GPIO output | Output | Active output pin, configured as push-pull |
| WM2 / `WM_SIM_2` | `PE15` | GPIO output | Output | Active output pin, configured as push-pull |
| WM3 / `WM_SIM_3` | `PD11` | GPIO output | Output | Active output pin, configured as push-pull |
| WM4 / `WM_SIM_4` | `PD12` | GPIO output | Output | Active output pin, configured as push-pull |
| UART TX | `PD5` | USART2_TX | Output | Active |
| UART RX | `PD6` | USART2_RX | Input | Active |
| WAKE_NINT | `PA0` | EXTI0 | Input | Active interrupt input |
| SENS1_INP_ADC | `PA5` | ADC1 input | Analog input | Active |
| SENS2_INP_ADC | `PA1` | ADC1 input | Analog input | Active |
| VAI1_VEN / VAI2_VEN / VAI3_VEN / VAI4_VEN | various | GPIO output | Output | Board-control signals, not tester CLI/output pins |

### Valve pins and removed hardware

No valve pins are configured in the new project. Search results show no `VALVE_0..VALVE_15` definitions in the project, no `VALVE_*_Pin` macros, and no valve GPIO group in the generated `main.h` / `gpio.c`.

This means the old 16-valve hardware is no longer connected to the new board, and the old `Application/App.cpp` valve list is obsolete.

---

## 3. New pin map and board reality

The new board is not a drop-in replacement for the old test fixture. The actual generated hardware defines are:

| Label | MCU pin | GPIO group | Functional use |
|---|---|---|---|
| `WM_SIM_1` | `PF8` | GPIOF | WM output channel 1 |
| `WM_SIM_2` | `PE15` | GPIOE | WM output channel 2 |
| `WM_SIM_3` | `PD11` | GPIOD | WM output channel 3 |
| `WM_SIM_4` | `PD12` | GPIOD | WM output channel 4 |
| `UART2_TX` | `PD5` | GPIOD | PC serial TX |
| `UART2_RX` | `PD6` | GPIOD | PC serial RX |
| `WAKE_NINT` | `PA0` | GPIOA | external wake/interrupt |
| `SENS1_INP_ADC` | `PA5` | GPIOA | analog sense 1 |
| `SENS2_INP_ADC` | `PA1` | GPIOA | analog sense 2 |

The old project used a different family / board layout and had valve ports on PB/PC/PA; the new project removed those lines. This is the source-of-truth hardware map that should drive the migration.

---

## 4. Existing APPLICATION architecture

The application folder includes the hand-written app logic and abstracts the hardware. Representative contents are:

| File | What it does | Classification |
|---|---|---|
| `App.cpp` / `App.hpp` | Owns `Board`, `Comm`, valve list, water-meter list, digital outputs, real timer, DAC; parses and dispatches commands | B / MODIFY |
| `Board.cpp` / `Board.hpp` | Thin board wrapper exposing the UART object and other hardware dependencies | B / MODIFY |
| `Uart.cpp` / `Uart.hpp` | DMA-based UART receive/transmit abstraction around `UART_HandleTypeDef` | B / MODIFY |
| `Comm.cpp` / `Comm.hpp` | Line-based UART command assembly, echo, command-ready semaphore, response sending | B / MODIFY |
| `ValveDetector.cpp` / `.hpp` | Reads a digital input with debounce logic and reports transitions | D / REMOVE |
| `WaterMeterSimulator.cpp` / `.hpp` | Generates pulse output with duty cycle and state transitions | B / MODIFY |
| `DacControl.cpp` / `.hpp` | Direct register-driven DAC channel setup on the STM32 DAC peripheral | C / REWRITE |
| `DigitalOutput.cpp` / `.hpp` | Simple GPIO output helper for static ON/OFF digital outputs | A / KEEP with pin map changes |
| `RealTimer.cpp` / `.hpp` | Software timer based on tick count | A / KEEP |
| `Clock.cpp` / `.hpp` | Provides millisecond time from FreeRTOS tick | A / KEEP |
| `TextPrinter.cpp` / `.hpp` | Minimal text output helper | A / KEEP |
| `TextScanner.cpp` / `.hpp` | Minimal parser for ASCII commands | A / KEEP |
| `MutexLock.cpp` / `.hpp` | RAII mutex wrapper | A / KEEP |
| `appProxy.cpp` / `.h` | C++ bridge from FreeRTOS default task | B / MODIFY |
| `CLIManager.cpp` / `.h` | Stub only, not implemented | E / NEW DEVELOPMENT or D if never used |

### Portable vs hardware-coupled logic

Portable application logic:

- `TextPrinter`, `TextScanner`, `Buffer` family, `Clock`, `RealTimer`, `MutexLock`
- command parsing and state machine logic in `App::HandleCommand`
- generic message/response formatting

Hardware-coupled logic:

- `Board.cpp` references the specific `UART_HandleTypeDef huart2`
- `Uart.cpp` touches DMA registers and HAL UART internals (`_huart.hdmarx->Instance->CNDTR`)
- `DacControl.cpp` writes direct DAC and GPIO registers (`RCC->APB1ENR1`, `GPIOA->MODER`, `DAC1->*`)
- `WaterMeterSimulator.cpp` writes direct GPIO output pins and uses a software pulse scheduler tied to `HAL_GPIO_WritePin`
- `ValveDetector.cpp` is tied to specific valve GPIO inputs

---

## 5. Valve functionality

The old application contains a full valve subsystem that should be treated as legacy functionality and preserved before removal.

### Legacy valve functionality in the old app

- `VALVE_COUNT = 16`
- 16 `ValveDetector` objects in `App.hpp`
- `GetValveBitmap()` returns a hex bitmap of valve states
- `CheckValves()` polls every valve and emits notification on transitions
- `ControlWaterMeters()` links each water meter to the paired valve
- `App::HandleCommand` contains valve-related status reporting in `get status`
- `WaterMeterSimulator::Task()` optionally starts/stops based on valve-open conditions
- `Comm` and `TextPrinter` send valve change messages to the PC GUI

### What was removed in the new hardware

- There are no 16 valve I/O pins in the `.ioc` or `main.h`.
- The application still initializes a 16-element valve array in `App::App()` and logs valve status in the active logic.
- Any direct valve-related command path is now obsolete for the new tester board.

### Required handling before code changes

Create a dedicated Git checkpoint containing the original project state before any valve removal. The commit message should clearly indicate this is the backup of the legacy valve functionality, for example:

`Preserve legacy valve functionality before migration`

This should be done only after approval; the current working tree is intentionally unchanged.

---

## 6. WM1–WM4 functionality

The old application treats water-meter channels as software pulse generators. That logic is still present in `WaterMeterSimulator.cpp`.

### Output mode (existing application)

- `WaterMeterSimulator::SetStatus(Status, cycleTimeMs)` drives the output pin HIGH/LOW and calculates pulse ON/OFF times.
- `WaterMeterSimulator::Task(bool isValvesOpened)` toggles the output based on a duty cycle pattern and increments `_pulseCount` on rising edges.
- The duty cycle is fixed to `5% ON / 95% OFF` using software timing.
- Timing is based on `Clock::GetTimeMsec()` using FreeRTOS kernel tick.
- No dedicated timer peripheral is required in the old implementation.
- GPIO state is written directly via `HAL_GPIO_WritePin(_port, _pin, ...)`.

### Input mode

The old project also has valve input detection using `ValveDetector::Read()` and simple debounce logic. A state change is accepted only after 5 stable samples. This matches the old board, not the new board.

### New WM mapping

The generated project defines four outputs, not five and not valve-driven inputs:

| Old app | New board pin | Effective result |
|---|---|---|
| WM1 | `PF8` (`WM_SIM_1`) | output channel 1 |
| WM2 | `PE15` (`WM_SIM_2`) | output channel 2 |
| WM3 | `PD11` (`WM_SIM_3`) | output channel 3 |
| WM4 | `PD12` (`WM_SIM_4`) | output channel 4 |

There is no `WM_SIM_0` in the new generated project. The app still references `WM_SIM_0` in `App.cpp`, which confirms the legacy board mapping still exists in the application and must be corrected.

---

## 7. UART / Python GUI communication analysis

The legacy GUI-to-board communication path is plain-text serial, not binary. This is consistent with the code:

- `FlexTesterGui.py` opens a serial port using `pyserial`.
- It sends command strings such as `get status`, `start wm 1 1000`, or `set dac1 2500`.
- The MCU listens on UART and assembles a line terminated by `\r` or `\n`.
- The `Comm` task echoes characters and then hands the complete command to `App::HandleCommand()`.
- Responses are returned as text strings over the same UART.

### Current new-project UART match

The new MCU config is consistent with a serial PC link on `USART2`:

- `PD5` TX
- `PD6` RX
- 115200 8N1
- no flow control
- DMA RX enabled
- NVIC enabled for RX and USART2

However, the current application is not a clean match to this new hardware because:

- `Uart::Send()` assumes a DMA TX path that is not configured.
- `Board` still binds to `huart2` and therefore is still coupled to the generated handle name.
- `Comm` expects line-based UART behavior abstracted by the `Uart` class, which is still valid in concept but needs validation against the new generated setup.
- `App` still contains legacy valve and water-meter command semantics that were designed around the old board.

### Python/GUI expectation

The old GUI expects the MCU to respond with human-readable ASCII lines. The application logic in `App::HandleCommand` is still aligned with that model, so the command protocol itself is likely reusable, but the board-specific pin mapping and hardware assumptions must be updated.

---

## 8. Old MCU dependencies and migration list

The old application contains numerous direct dependencies on the previous board and MCU configuration. These should be treated as migration risks.

### Hard dependencies to remove or adapt

- `huart2` global handle in `Board.cpp`
- `HAL_UART_Receive_DMA()` / `HAL_UART_Transmit_DMA()` assumptions
- `DMA1_Channel6` / `DMA1_Channel7` assumptions from earlier project
- direct reads of `hdmarx->Instance->CNDTR` in `Uart::Recv()`
- `DacControl.cpp` direct access to `RCC->APB1ENR1`, `GPIOA->MODER`, and `DAC1->DHR12R1` / `DHR12R2`
- `main.h` generated pin defines for valve and WM lines
- `gpio.c` generated initializations for old pins
- `VALVE_*` macros and old port names
- old board-specific semantics in `App::CheckValves()` and `ControlWaterMeters()`
- assumptions that there are 5 WMs and 16 valves

### Migration list

| Dependency | Status |
|---|---|
| `huart2` | Must be validated against new CubeMX handle |
| `DMA1_Channel6` RX | Valid for new config |
| `DMA1_Channel7` TX | Missing from generated config; must be added or reworked |
| `USART2` | Valid for new config |
| `PD5/PD6` pins | Valid for new config |
| valve pins | Obsolete, remove |
| `WM_SIM_1..4` | Use as the active output set |
| `ValveDetector` | Remove |
| `DacControl` | Potentially obsolete or must be remapped to new DAC assignment |
| `App::ControlWaterMeters` | Must be adapted to the new WM mapping |
| `App::CheckValves` | Remove or replace with actual sensor input logic |

---

## 9. Migration matrix

| Existing function | Current implementation | New MCU support | Action | Risk |
|---|---|---|---|---|
| 16-valve input system | `ValveDetector[16]` + GPIO polling + debounce | None | REMOVE | High |
| WM pulse generation | `WaterMeterSimulator` state machine + GPIO output pin toggling | `WM_SIM_1..4` output pins exist | MODIFY | Medium |
| UART command transport | `Comm` + `Uart` + DMA | `USART2` exists, RX DMA present, TX DMA mismatch | MODIFY | High |
| GUI command protocol | Plain ASCII text lines | Same format expected by GUI | KEEP | Low |
| `get status` response | valve bitmap + WM status | WM status still relevant; valves obsolete | MODIFY | Medium |
| Water meter trigger/stop logic | state machine tied to valve open/close | New board has no valve inputs; needs redefinition | REWRITE | High |
| DAC1 output | direct register writes to PA4/PA5 | New board does not expose those pins as DAC in this generated project | NEEDS INVESTIGATION | High |
| `DigitalOutput` static outputs | generic GPIO writes | still valid if outputs are mapped | KEEP | Low |
| `RealTimer` / `Clock` | software time base | still valid | KEEP | Low |
| `TextScanner` / `TextPrinter` | generic parsing and text formatting | still valid | KEEP | Low |
| `Board` wrapper | ties to `huart2` | board-specific but still valid if handle remains `huart2` | MODIFY | Medium |
| app startup task | generated FreeRTOS default task | valid | KEEP | Low |

---

## 10. Risks

1. The application still contains a 16-valve model even though the new board removed the valve hardware. This can cause broken compile-time references or dead logic.
2. The generated UART config provides RX DMA but not TX DMA, while the application expects DMA TX in `Uart::Send()`.
3. There is no explicit board-level `WM1..WM4` naming in the new project; the code still names them by legacy semantics, which increases risk of wrong pin mapping.
4. The old code couples directly to hardware registers and global handles, which makes it less portable to the new MCU.
5. ADC and other sensor-related pins may need a new, separate abstraction layer if the final tester requires them.

---

## 11. Missing information

The following items need confirmation before migration work begins:

1. Which exact tester I/O is required for the final WM1–WM4 channels on the new PCB?
2. Are the four outputs `WM_SIM_1..WM_SIM_4` the final intended WM channels, or are there additional hardware channels not yet exposed in the CubeMX project?
3. Is the serial command protocol from the old GUI still valid, or does the Python GUI need a revised command set?
4. Should the final tester support output-only WM pulse generation, sensor input detection, or both?
5. Are the ADC channels `PA1` / `PA5` used by the tester, and do they belong to the final WM input path or separate measurement functions?
6. Is DAC output still required in the final product, or should that be removed from the new tester configuration?

---

## 12. Step-by-step implementation plan

### Phase 1 — freeze and document the legacy baseline
- Confirm that the existing code is the current baseline.
- Record the legacy valve functionality and command protocol.
- Capture the old project state in a dedicated Git backup commit before any migration changes.

### Phase 2 — define the target board contract
- Treat the CubeMX `.ioc` and generated `main.h` / `gpio.c` as the source of truth.
- Document the final active pins:
  - WM1..WM4 = `WM_SIM_1..WM_SIM_4`
  - UART = `USART2` on `PD5/PD6`
  - relevant ADC / EXTI pins
- Confirm which signals are still required by the tester and which are obsolete.

### Phase 3 — remove valve scope from the active design
- Remove valve hardware assumptions from `App.cpp`.
- Remove or disable the valve array and valve-derived status reporting.
- Eliminate any code path that ties WM behavior to a valve-open condition unless that behavior is still required.
- Do not touch the legacy code in the backup commit.

### Phase 4 — adapt the hardware abstraction layer
- Keep the application protocol layer intact but replace the board-level mapping.
- Update the UART abstraction so it matches the new DMA and interrupt configuration.
- Add or correct DMA TX handling if the final design requires DMA-based transmit.
- Reconcile `Board.cpp` and `App.hpp` with the real `huart2` and pin map.

### Phase 5 — adapt WM1–WM4 to the new board
- Replace the old WM pin macros with `WM_SIM_1..4` definitions.
- Maintain the generic pulse-generation state machine but map it to the new physical outputs.
- Decide whether the final WM channels are output-only or also support input detection.

### Phase 6 — validate UART and command flow
- Confirm the GUI can talk to the MCU on `USART2` at 115200 8N1.
- Verify the command parser and response strings still match the GUI contract.
- Validate echo and command termination handling.

### Phase 7 — compile and assess build issues
- Build the firmware after the migration-layer changes.
- Fix any compile-time mismatches caused by removed valve symbols or stale old pin names.

### Phase 8 — run hardware-level tests
- Verify each WM output line toggles correctly.
- Verify serial response strings match the expected command API.
- If the board uses input detection, test the ON/OFF state detection separately.

### Phase 9 — final functional verification
- Validate the final tester workflow from GUI → UART → STM32 → hardware response → GUI result.
- Confirm that the final app no longer contains active valve logic unless deliberately retained for support/debug use.

---

## 13. Summary

The key conclusion is that the new project is not a direct hardware port of the old application. The old code is still heavily centered on a 16-valve / 5-WM / DAC-based board, while the actual generated CubeMX project defines a different set of only four WM outputs and a different UART layout.

The migration plan therefore must:

1. preserve the original valve functionality in Git first,
2. remove valve dependencies from the active design,
3. map the old app logic to the new `WM_SIM_1..4` output pins,
4. validate UART transport against the real `USART2` configuration,
5. and only then proceed with compile and hardware validation.

This analysis is intentionally documentation-only. No source code modification or migration work begins until the plan is reviewed and approved.
