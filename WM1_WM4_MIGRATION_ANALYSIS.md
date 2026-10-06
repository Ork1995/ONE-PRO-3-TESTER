# WM1–WM4 Migration Analysis

Date: 2026-10-06. Phase: ANALYSIS ONLY. No firmware, GUI, build configuration, or CubeMX configuration changed for this analysis.

Scope: active `ONE PRO 3 TESTER` firmware, compared with `FlexTesterRepo/Nucleo` and its `FlexTesterGui.py`. The current source and generated peripheral configuration take precedence over the earlier general migration report, which describes some now-obsolete application/build states.

**Confirmed product requirement (2026-10-06 correction):** WM1-WM4 are controlled internally through the application/UART commands. `start wm n 1000` must start only the selected output at approximately 1 Hz, 50 ms HIGH and 950 ms LOW. `stop wm n` must stop that output. EXTERNAL TRIGGER REQUIRED: NO. Do not add external inputs, GPIO interrupts, gate logic, or hardware-interface changes for WM activation. Legacy valve-gated states are historical implementation details, not missing migration functionality.

Evidence limits: this is a source/configuration analysis, not a board test. Connector routing, external output circuitry, electrical polarity, receiving-device voltage limits, oscillator population, and real pulse accuracy cannot be established from the available CubeMX files alone. An output label is not proof of electrical compatibility. No board was flashed and no physical waveform was measured.

## 1. Current Build Status

- The last complete Clean + Build passed: 0 compiler errors, 3 existing `-Wmisleading-indentation` warnings in `App::AppendStatus()` in [Application/App.cpp](Application/App.cpp#L78).
- The build log contains `Finished building target: ONE PRO 3 TESTER.elf`, successful size/list generation, and normal make completion. The existing ELF was verified during this analysis; no rebuild was needed for a documentation-only task.
- [Debug/ONE PRO 3 TESTER.elf](Debug/ONE%20PRO%203%20TESTER.elf) exists. Its observed size is 2,050,612 bytes; reported firmware sections are text 58,884 bytes, data 96 bytes, BSS 28,560 bytes. File size includes debug information, not just flash payload.
- Previously verified symbols: `appProxy.o` exports `T runAppTask`; `freertos.o` references `U runAppTask`. Application C++ sources are compiled and included in the linker response file.
- The prior UART fix uses `txBuf.begin()` for HAL's `const uint8_t*` transmit parameter. Build architecture is not an outstanding WM migration issue.
- Build success does not prove successful startup, serial communication, or physical WM pulses.

## 2. System Architecture

### Source inventory and ownership

| Files | Responsibility for WM1-WM4 |
|---|---|
| [Application/App.cpp](Application/App.cpp), [Application/App.hpp](Application/App.hpp) | Four channel instances, GPIO/ID binding, initialization, command dispatch, common polling loop, status formatting |
| [Application/WaterMeterSimulator.cpp](Application/WaterMeterSimulator.cpp), [Application/WaterMeterSimulator.hpp](Application/WaterMeterSimulator.hpp) | Shared pulse state machine, output writes, phase timing, rising-edge count, trigger transitions, saved phase state |
| [Application/appProxy.cpp](Application/appProxy.cpp), [Application/appProxy.h](Application/appProxy.h) | C-to-C++ `runAppTask()` bridge; board access for UART callbacks |
| [Application/Board.cpp](Application/Board.cpp), [Application/Board.hpp](Application/Board.hpp) | Own `_commUart` bound to `huart2`; UART handle lookup, not WM pin ownership |
| [Application/Comm.cpp](Application/Comm.cpp), [Application/Comm.hpp](Application/Comm.hpp) | Comm thread, line assembly/echo, command-ready semaphore, shared mutex, response transmission |
| [Application/Uart.cpp](Application/Uart.cpp), [Application/Uart.hpp](Application/Uart.hpp) | Circular RX DMA polling and current blocking UART transmission; shared by all WMs |
| [Application/Clock.cpp](Application/Clock.cpp), [Application/Clock.hpp](Application/Clock.hpp) | Milliseconds from FreeRTOS kernel tick |
| [Application/RealTimer.cpp](Application/RealTimer.cpp), [Application/RealTimer.hpp](Application/RealTimer.hpp) | Software HH:MM:SS for messages; does not use the hardware RTC |
| [Application/TextScanner.cpp](Application/TextScanner.cpp), [Application/TextScanner.hpp](Application/TextScanner.hpp) | Token/numeric command parsing |
| [Application/TextPrinter.cpp](Application/TextPrinter.cpp), [Application/TextPrinter.hpp](Application/TextPrinter.hpp) | Response/status serialization |
| [Application/Buffer.hpp](Application/Buffer.hpp), [Application/BufferView.hpp](Application/BufferView.hpp), [Application/MutexLock.cpp](Application/MutexLock.cpp), [Application/MutexLock.hpp](Application/MutexLock.hpp) | Buffer storage/views and communication locking |
| [Core/Src/main.c](Core/Src/main.c), [Core/Src/freertos.c](Core/Src/freertos.c), [Core/Inc/FreeRTOSConfig.h](Core/Inc/FreeRTOSConfig.h) | Peripheral initialization, task creation, scheduler, 1 kHz timebase |
| [Core/Inc/main.h](Core/Inc/main.h), [Core/Src/gpio.c](Core/Src/gpio.c) | Actual WM pin definitions, port clocks, initial LOW levels, output modes |
| [Core/Src/usart.c](Core/Src/usart.c), [Core/Src/dma.c](Core/Src/dma.c), [Core/Src/stm32l4xx_it.c](Core/Src/stm32l4xx_it.c) | USART2 pin/baud/DMA/IRQ setup and handlers |
| [Core/Src/tim.c](Core/Src/tim.c), [Core/Src/adc.c](Core/Src/adc.c), [Core/Src/rtc.c](Core/Src/rtc.c) | Other initialized board peripherals; not used to produce WM pulses |
| [Application/DacControl.cpp](Application/DacControl.cpp), [Application/DacControl.hpp](Application/DacControl.hpp) | Legacy direct DAC setup still invoked by shared `App::Init()`; indirect startup concern |
| [Application/ValveDetector.cpp](Application/ValveDetector.cpp), [Application/ValveDetector.hpp](Application/ValveDetector.hpp) | Legacy digital-input/debounce helper remains in the source tree, but the active App owns no valve array and calls none of its methods |
| [Application/DigitalOutput.cpp](Application/DigitalOutput.cpp), [Application/DigitalOutput.hpp](Application/DigitalOutput.hpp) | Legacy PS helper; current PS count is zero without the old PS macros, not a WM dependency |
| [ONE PRO 3 TESTER.ioc](ONE%20PRO%203%20TESTER.ioc) | Source-of-truth new MCU/peripheral assignments |
| [Legacy App](../FlexTesterRepo/Nucleo/Application/App.cpp), [Legacy CubeMX](../FlexTesterRepo/Nucleo/TestBoard.ioc), [GUI](../FlexTesterRepo/FlexTesterGui.py) | Original channel/valve behavior, old hardware definitions, host command/graph expectations |

`CLIManager` is not instantiated by the active App (its member is commented out); WM commands go through `Comm`, not a separate CLI task.

### Power-up and task flow

```text
Power-up -> Reset_Handler / C runtime -> main()
  -> HAL_Init()
  -> SystemClock_Config() -> PeriphCommonClock_Config()
  -> MX_GPIO_Init() [all four WM outputs initially LOW]
  -> MX_DMA_Init()
  -> MX_TIM3_Init() -> MX_TIM8_Init() -> MX_ADC1_Init()
  -> MX_USART2_UART_Init() -> MX_ADC3_Init() -> MX_TIM7_Init() -> MX_RTC_Init()
  -> osKernelInitialize()
  -> MX_FREERTOS_Init()
       -> osThreadNew(StartDefaultTask, ..., defaultTask_attributes)
  -> osKernelStart()
  -> StartDefaultTask()
  -> runAppTask()
  -> App::Instance() [function-local singleton constructed on first call]
       -> Board::Board() -> Uart::Uart(huart2) -> Uart::Restart()
            -> HAL_UART_Receive_DMA(..., 512) [circular RX]
       -> Comm::Comm()
            -> osSemaphoreNew(1, 0, NULL), osMutexNew(NULL)
            -> osThreadNew(... Comm::Task(), ..., attrs)
       -> four _wmSim objects bound to their generated GPIO macros
  -> App::Task()
       -> App::Init()
            -> each WM.SetStatus(Stopped, 0)
            -> PS loop [empty on current board]
            -> RealTimer::Set(0, 0, 0)
            -> DacControl::Init(), SetVoltage(0), SetVoltage2(0)
       -> Comm::SendResponse("App Started\r\n")
       -> loop: ReceiveCommand(cmdBuf, 10)
                -> HandleCommand(cmdBuf) if ready
                -> ControlWaterMeters()
                     -> each WM.Task(false)
                     -> Set() -> HAL_GPIO_WritePin(_port, _pin, level)
```

In parallel, `Comm::Task()` calls `Uart::Recv(&rxByte, 1)`, assembles a line, echoes characters/newlines, sets `_isCmdReady`, and releases `_cmdReady`. CR, LF, and CRLF are accepted; the LF following a CR is ignored. `App::HandleCommand()` parses the assembled line and selects `_wmSim[id - 1]`. Replies pass through `Comm::SendResponse()` -> `Uart::Send()` -> `HAL_UART_Transmit()` -> USART2 TX on PD5.

### Shared simulator behavior and limitations

- Four independently stored state machines share one sequential polling loop. There is no WM thread, WM timer interrupt, PWM channel, input capture, or WM DMA transfer.
- `Clock::GetTimeMsec()` is `osKernelGetTickCount() * (1000 / configTICK_RATE_HZ)`. Both projects use 1000 Hz, so current resolution is 1 ms. The new CPU clock is 32 MHz versus legacy 80 MHz; the kernel time unit remains milliseconds.
- For cycle `C` milliseconds, requested HIGH duration is integer `floor(C * 5 / 100)` and LOW duration is the remainder. This is 5% HIGH / 95% LOW, not a 50% square wave.
- A fresh `Started` transition drives LOW and begins with the LOW interval. For `C=1000`, the intended first rising edge is after 950 ms, followed by 50 ms HIGH. Physical HIGH at the MCU pin does not establish active polarity at the external receiver.
- `Task()` advances only one phase per invocation. It increments `_tLastSwitch` by the scheduled phase length, but cannot recreate edges missed during a long scheduling/communication delay. Four writes occur sequentially, not simultaneously.
- Idle App iterations normally wait up to 10 kernel ticks for a command. Parsing, communication mutex waits, UART response/echo work, and scheduling add latency. There is no guaranteed 10 ms fixed period or proven jitter bound.
- Current blocking UART TX can wait for ready state for up to 100 ms, then has a 100 ms HAL transmit timeout. It differs from legacy asynchronous TX DMA and can interfere with software pulse timing under contention/faults. This existing implementation is not changed or proposed for automatic redesign here.
- `Started` runs regardless of the trigger argument. The current `Task(false)` call does not prevent UART-started pulses and is not a migration defect. Legacy `Triggered`/`RunningTriggered` states and their automatic notifications are outside the confirmed product requirement; do not add an input provider to activate them.
- Rising edges increment `_pulseCount`. Direct start/stop commands return immediate acknowledgements, not `StateChange` events. Counters are not reset by these commands or by `system init`; the event path contains resets, but is currently unreachable. There is no periodic pulse-count/edge telemetry.
- `PrintStatus()` prints state and retained cycle time, not pulse count. After stopping, `get status` may still show the previous nonzero cycle, intentionally preserved for resume checks.
- `SetStatus()` saves remaining phase on running-to-stopped transitions and may restore it on restart with the same nonzero cycle. This is not a hardware-timer resume and requires timing tests. `system init` uses the same stop API, so it is not a complete counter/resume-history reset.
- IDs are range-checked 1..4. Cycle times are not range-checked: zero, negative values converted to `uint32_t`, and multiplication overflow are possible. `TextScanner` accepts signed numbers and does not check `strtol` overflow. A first zero-cycle start leaves zero phase durations; a subsequent zero value may retain an earlier cycle. Cycles below 20 ms yield zero requested HIGH duration; even larger cycles can request HIGH durations shorter than the normal polling interval. Do not infer an approved minimum rate from the build.

### Hardware abstraction findings

`WaterMeterSimulator` is generic at the GPIO-port/pin level. Actual channel binding belongs to `App::App()` and uses generated `main.h` macros. No old PC0-PC3 definitions need copying. All new WM pins are GPIO output push-pull, no pull, LOW speed, initial RESET/LOW; GPIOF, GPIOE, and GPIOD clocks are enabled. AF is not applicable to these outputs.

The required activation path is already implemented: `App::HandleCommand()` selects a channel and sets `Started` or `Stopped`; the generic simulator generates pulses on the bound GPIO. No replacement for the old valve state is required. `WAKE_NINT`, sensor ADCs, and other board-control signals must remain unrelated to WM activation. Do not investigate or repurpose them as WM gates.

## 3. WM1

### Purpose

Generate command-controlled water-meter simulator pulses for logical channel 1; it is an output simulator, not a physical flow-sensor input reader.

### Files and functions

Common files/functions are listed in section 2. Channel ownership is `_wmSim[0]` in `App.cpp`/`App.hpp`, ID 1, `WM_SIM_1_GPIO_Port`/`WM_SIM_1_Pin` from `Core/Inc/main.h`. Main methods: `App::Init()`, `App::Task()`, `App::HandleCommand()`, `App::ControlWaterMeters()`, `WaterMeterSimulator::SetStatus()`, `Task()`, `Set()`, `PrintStatus()`, and `App::AppendStatus()` (`wm1=` field).

### Execution flow and initialization

Power-up -> `main()` -> `MX_GPIO_Init()` sets PF8 LOW -> `MX_FREERTOS_Init()` creates defaultTask -> `StartDefaultTask()` -> `runAppTask()` -> `App::Instance().Task()` -> `App::Init()` stops channel 1 -> `Comm::Task()` receives command -> `ReceiveCommand()` -> `HandleCommand()` selects `_wmSim[0]` -> `ControlWaterMeters()` -> `_wmSim[0].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOF, GPIO_PIN_8, level)` -> command acknowledgement or `PrintStatus()` response through USART2. Shared startup clock/peripheral failures prevent this flow.

### UART interaction

`start wm 1 C`, `stop wm 1`, `trigger wm 1 C`; responses `wm 1 started`, `wm 1 stopped`, `wm 1 triggered`, each CRLF-terminated. `get status` includes ` wm 1 <state> <cycle>ms`. Shared transport and asynchronous-message limitations are in sections 2 and 8.

### Hardware dependencies: original and new

- OLD STM32L476RG: WM1 uses `WM_SIM_0` on PC0/GPIOC (not the legacy `WM_SIM_1` label). Output PP, no pull, LOW speed, initial LOW; no AF, pulse timer, WM DMA, or WM IRQ. Its associated valve 1 is `VALVE_0`, PB0/GPIOB, input with pulldown, active-high, polled/debounced by `ValveDetector`.
- NEW STM32L496ZG: `WM_SIM_1`, PF8/GPIOF, same output mode/pull/speed/initial level; `.ioc` says PF8 `GPIO_Output`. No WM AF/timer/DMA/IRQ. Activation is internal/UART; no external input is required.
- Shared dependencies: USART2 PD5/PD6 AF7, RX DMA1 channel 6/request 2, USART2 and DMA IRQs, 1 kHz FreeRTOS tick. ADC/DAC are not used by WM1 pulse generation.

### Missing/incompatible parts and required changes

Output mapping and UART start/stop are compatible by source inspection; no implementation change is currently justified. Verify PF8 produces approximately 1 Hz with 50 ms HIGH/950 ms LOW for `start wm 1 1000`, stops on command, and remains safe through startup/reset. Compare measured timing with legacy free-running behavior. External gating is not required.

## 4. WM2

### Purpose

Generate independently controlled channel-2 pulses using the same state machine as WM1.

### Files and functions

Section-2 common files apply. `_wmSim[1]`, ID 2, uses `WM_SIM_2_GPIO_Port`/`WM_SIM_2_Pin`; `AppendStatus()` selects `_wmSim[1]._pulseCount` for `wm2=`. All shared App/simulator/Comm functions apply; there is no channel-specific driver or thread.

### Execution flow and initialization

Power-up -> `main()` -> `MX_GPIO_Init()` sets PE15 LOW -> `MX_FREERTOS_Init()` -> defaultTask -> `StartDefaultTask()` -> `runAppTask()` -> `App::Instance().Task()` -> `App::Init()` stops channel 2 -> `Comm::Task()`/`Uart::Recv()` -> `ReceiveCommand()` -> `HandleCommand()` selects `_wmSim[1]` -> `ControlWaterMeters()` -> `_wmSim[1].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOE, GPIO_PIN_15, level)` -> USART2 acknowledgement/status.

### UART interaction

`start wm 2 C`, `stop wm 2`, `trigger wm 2 C`; `wm 2 started|stopped|triggered` acknowledgements. `get status` includes channel 2 and retained cycle time. Command echo/framing is shared; no dedicated UART or additional DMA.

### Hardware dependencies: original and new

- OLD STM32L476RG: logical WM2 uses `WM_SIM_1`, PC1/GPIOC, output PP/no pull/LOW speed/initial LOW. Corresponding valve 2 is `VALVE_1`, PB1/GPIOB, input pulldown, active-high, polled/debounced. AF and WM timer/DMA/IRQ: none.
- NEW STM32L496ZG: `WM_SIM_2`, PE15/GPIOE, output PP/no pull/LOW speed/initial LOW; `.ioc` GPIO output and generated GPIOE initialization agree. No pulse AF/timer/DMA/IRQ; activation is internal/UART, with no external input required.
- USART2/RX DMA/IRQs/kernel tick are common. No ADC/DAC dependency in this channel's pulse algorithm.

### Missing/incompatible parts and required changes

No output remap or gate implementation is needed. Verify `start wm 2 1000` selects PE15 alone and produces approximately 1 Hz, 50 ms HIGH/950 ms LOW. Verify stop, legacy timing parity, and startup/reset behavior before proposing any source change.

## 5. WM3

### Purpose

Generate independently controlled channel-3 water-meter simulator pulses.

### Files and functions

Section-2 files/functions apply. `_wmSim[2]`, ID 3, is bound to `WM_SIM_3_GPIO_Port`/`WM_SIM_3_Pin`; `wm3=` snapshots read `_wmSim[2]._pulseCount`. No separate channel task, timer, or UART.

### Execution flow and initialization

Power-up -> `main()` -> `MX_GPIO_Init()` sets PD11 LOW -> `MX_FREERTOS_Init()` -> defaultTask -> `StartDefaultTask()` -> `runAppTask()` -> `App::Instance().Task()` -> `App::Init()` stops channel 3 -> UART circular RX -> `Comm::Task()` -> `ReceiveCommand()` -> `HandleCommand()` selects `_wmSim[2]` -> `ControlWaterMeters()` -> `_wmSim[2].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_11, level)` -> USART2 acknowledgement/status.

### UART interaction

`start wm 3 C`, `stop wm 3`, `trigger wm 3 C`; `wm 3 started|stopped|triggered` acknowledgements, plus channel-3 state/cycle in `get status`. No periodic edge/count notification.

### Hardware dependencies: original and new

- OLD STM32L476RG: logical WM3 uses `WM_SIM_2`, PC2/GPIOC, output PP/no pull/LOW speed/initial LOW. Valve 3 is `VALVE_2`, PB2/GPIOB, input pulldown, active-high, polled/debounced. No pulse AF/timer/DMA/IRQ.
- NEW STM32L496ZG: `WM_SIM_3`, PD11/GPIOD, same GPIO output settings; `.ioc` and `main.h`/`gpio.c` agree. No pulse AF/timer/DMA/IRQ; internal/UART activation needs no external input. Old PC2 is now an ADC3 sensor input, so copying the old output mapping would be incorrect.
- PD11 is separate from USART2 PD5/PD6 and WM4 PD12. Shared GPIO port alone is not a conflict: `HAL_GPIO_WritePin()` acts on the specified pin mask. Shared kernel/serial dependencies remain; ADC/DAC do not generate WM3 pulses.

### Missing/incompatible parts and required changes

Keep PD11 mapping. Verify `start wm 3 1000` and `stop wm 3` control only PD11, with approximately 1 Hz and 50 ms HIGH/950 ms LOW while running. Compare legacy timing and verify startup/reset and PD12 isolation. No external gating work is required.

## 6. WM4

### Purpose

Generate independently controlled channel-4 water-meter simulator pulses; ID 4 is the last accepted channel in the migrated App.

### Files and functions

Section-2 common files/functions apply. `_wmSim[3]`, ID 4, uses `WM_SIM_4_GPIO_Port`/`WM_SIM_4_Pin`; `wm4=` selects `_wmSim[3]._pulseCount`. No separate WM4 thread/driver.

### Execution flow and initialization

Power-up -> `main()` -> `MX_GPIO_Init()` sets PD12 LOW -> `MX_FREERTOS_Init()` -> defaultTask -> `StartDefaultTask()` -> `runAppTask()` -> `App::Instance().Task()` -> `App::Init()` stops channel 4 -> `Comm::Task()` receives UART line -> `ReceiveCommand()` -> `HandleCommand()` selects `_wmSim[3]` -> `ControlWaterMeters()` -> `_wmSim[3].Task(false)` -> `Set()` -> `HAL_GPIO_WritePin(GPIOD, GPIO_PIN_12, level)` -> USART2 acknowledgement/status.

### UART interaction

`start wm 4 C`, `stop wm 4`, `trigger wm 4 C`; `wm 4 started|stopped|triggered` acknowledgements. `get status` includes channel 4; ID 5 is rejected by the active firmware.

### Hardware dependencies: original and new

- OLD STM32L476RG: logical WM4 uses `WM_SIM_3`, PC3/GPIOC, output PP/no pull/LOW speed/initial LOW. Valve 4 is `VALVE_3`, PB10/GPIOB, input pulldown, active-high, polled/debounced. No pulse AF/timer/DMA/IRQ.
- NEW STM32L496ZG: `WM_SIM_4`, PD12/GPIOD, same GPIO settings; no pulse AF/timer/DMA/IRQ. Internal/UART activation needs no external input. Old PC3 is now ADC3 sensor input, not WM4 output.
- Shared serial/tick dependencies are unchanged at the logical channel level. ADC/DAC are not pulse-generation inputs.

### Missing/incompatible parts and required changes

No PD12 remap or external input is required. Verify `start wm 4 1000` selects PD12 alone and produces approximately 1 Hz, 50 ms HIGH/950 ms LOW. Verify stop, legacy timing parity, startup/reset safety, and isolation from PD11.

## 7. Hardware Dependency Matrix

OLD MCU: STM32L476RGTx, LQFP64. NEW MCU: STM32L496ZGTx, LQFP144. For all pulse GPIO rows, OLD and NEW use output PP, no pull, LOW speed, initial LOW; AF is N/A. No PWM/DMA/IRQ is attached to the pulse pin in either project.

| WM | Function | Old MCU Peripheral | Old Pin | New Peripheral | New Pin | Status | Required Action |
|---|---|---|---|---|---|---|---|
| WM1 | Pulse output | GPIOC, `WM_SIM_0`; AF N/A | PC0 | GPIOF, `WM_SIM_1`; AF N/A | PF8 | Mapping implemented | Verify connector/electrical polarity and scope waveform; do not copy PC0 |
| WM2 | Pulse output | GPIOC, `WM_SIM_1`; AF N/A | PC1 | GPIOE, `WM_SIM_2`; AF N/A | PE15 | Mapping implemented | Verify physical output; do not match channels by old macro suffix |
| WM3 | Pulse output | GPIOC, `WM_SIM_2`; AF N/A | PC2 | GPIOD, `WM_SIM_3`; AF N/A | PD11 | Mapping implemented | Verify output; old PC2 is now an analog sensor pin |
| WM4 | Pulse output | GPIOC, `WM_SIM_3`; AF N/A | PC3 | GPIOD, `WM_SIM_4`; AF N/A | PD12 | Mapping implemented | Verify output; old PC3 is now an analog sensor pin |
| WM1 | Required activation | UART start/stop; legacy optional valve gate is historical | UART PA2/PA3 | App command -> `_wmSim[0].SetStatus()` | UART PD5/PD6 | Implemented; external gate not required | Verify selected-channel start/stop; no new input |
| WM2 | Required activation | Same | UART PA2/PA3 | App command -> `_wmSim[1].SetStatus()` | UART PD5/PD6 | Implemented; external gate not required | Same |
| WM3 | Required activation | Same | UART PA2/PA3 | App command -> `_wmSim[2].SetStatus()` | UART PD5/PD6 | Implemented; external gate not required | Same |
| WM4 | Required activation | Same | UART PA2/PA3 | App command -> `_wmSim[3].SetStatus()` | UART PD5/PD6 | Implemented; external gate not required | Same |
| All | UART TX | USART2 AF7, PP/no pull/VERY_HIGH, 115200 8N1 | PA2 | USART2 AF7, PP/no pull/VERY_HIGH, 115200 8N1 | PD5 | Mapped; current blocking TX | Verify external UART adapter/connection; no pin/baud changes required |
| All | UART RX | USART2 AF7, PP/no pull/VERY_HIGH | PA3 | USART2 AF7, PP/pullup/VERY_HIGH | PD6 | Mapped | Verify reception; retain current pull configuration |
| All | Serial RX DMA/IRQ | DMA1_Channel6, request 2, circular byte transfers, priority LOW; IRQ priority 5 | No extra pin (PA3 UART) | Same channel/request/mode; `DMA1_Channel6_IRQHandler()` -> `HAL_DMA_IRQHandler(&hdma_usart2_rx)` | No extra pin (PD6 UART) | Compatible implementation | No WM DMA change; stress-test serial bursts/ring wrap |
| All | Serial TX DMA/IRQ | DMA1_Channel7, request 2, normal byte transfers; IRQ priority 5 | No extra pin (PA2 UART) | None configured or used for TX | No extra pin (PD5 UART) | Intentional current transport difference | Measure timing impact; do not add TX DMA in this phase |
| All | UART IRQ | `USART2_IRQn`, priority 5; HAL handler | PA2/PA3 shared | `USART2_IRQn`, priority 5; `USART2_IRQHandler()` -> `HAL_UART_IRQHandler(&huart2)` | PD5/PD6 shared | Compatible routing | Check runtime RX/error handling, not WM IRQ redesign |
| All | Pulse time reference | FreeRTOS SysTick, 1000 Hz; kernel count; CPU 80 MHz | N/A | FreeRTOS SysTick, 1000 Hz; kernel count; CPU 32 MHz | N/A | Compatible units, timing unmeasured | Measure latency/jitter at the new clock; no CPU-derived period scaling needed |
| All | HAL timeout timebase | TIM6, 1 kHz, `TIM6_DAC_IRQn`; no GPIO AF | N/A | SysTick handler calls `HAL_IncTick()` and `xPortSysTickHandler()` | N/A | Configuration differs | Verify HAL timeout behavior; WM scheduling uses kernel ticks, not TIM6 |
| All | Other timers | No dedicated WM timer | N/A | TIM3/TIM7 base timers, PSC 0/ARR 65535; TIM8 CH4 PWM AF3, PSC 0/ARR 65535/Pulse 0 | PC9 only for TIM8/`VSEN_PWM` | Not used by WM code | No `HAL_TIM_*Start` in active App/Core paths; leave them alone |
| None | Unrelated wake input | Old B1 PC13 falling EXTI | PC13 | `WAKE_NINT`, PA0 rising EXTI, no pull, IRQ priority 5 | PA0 | Outside WM requirements | Leave unchanged; do not use for WM activation |
| All | Startup DAC | DAC1 channels 1/2, analog, no GPIO AF | PA4/PA5 | Direct `DacControl` writes still enable DAC1 channels 1/2; no CubeMX DAC IP | PA4/PA5 | Legacy hardware side effect | Separate board review: PA5 is assigned ADC1_IN10; resolve only after approval |
| None | Unrelated sensor inputs | No ADC dependency for free-running pulses | N/A | CubeMX sensor labels: ADC1_IN10 (SENS1), ADC1_IN6 (SENS2), ADC3_IN3 (SENS3), ADC3_IN4 (SENS4); analog/no AF | PA5/PA1/PC2/PC3 | Outside WM activation path | No ADC acquisition or gate design required for WM1-WM4 |
| All | Human-readable event time | `RealTimer`, software kernel ticks | N/A | Same `RealTimer`; hardware RTC additionally initialized from LSE | N/A | Compatible software path | No RTC dependency/remap needed for WM events |

### ADC/DAC boundary requiring caution

The WM algorithm reads no ADC values and needs no ADC acquisition. Sensor ranks and sensor functionality are outside WM migration scope; no sensor-to-WM activation mapping is required or proposed.

`App::Init()` unconditionally calls the legacy `DacControl` routines even though the new CubeMX IP list omits DAC. Those routines enable PA4/PA5 DAC outputs; PA5 is now designated `SENS1_INP_ADC`. This does not overlap PF8/PE15/PD11/PD12, but remains a startup/reset safety check for the board. It is not a WM activation dependency and does not justify adding gate logic or changing ADC configuration.

## 8. UART Dependency Matrix

`n` means each of WM1, WM2, WM3, WM4 (1..4). `C` is the full cycle in integer milliseconds, not flow in liters. RX is PC -> MCU; TX is MCU -> PC. All commands share USART2: new RX PD6, TX PD5, AF7, 115200/8N1/no flow control. Input ends with CR/LF/CRLF; responses end with CRLF. Character/newline echo can appear before acknowledgements.

| WM | Command | Direction | Function | UART | Expected Data | Response |
|---|---|---|---|---|---|---|
| 1..4 | `start wm n C` | RX -> TX | `HandleCommand()` -> `SetStatus(Started, C)` -> later `Task(false)` | Shared USART2 | ID 1..4; cycle parses as signed long then casts to uint32_t; positivity/range currently unchecked | `wm n started\r\n`; free-running GPIO pulses |
| 1..4 | `stop wm n` | RX -> TX | `SetStatus(Stopped, 0)` | Shared USART2 | ID 1..4 | `wm n stopped\r\n`; output LOW on running-to-stopped transition; retained cycle/count/history |
| Historical only | `trigger wm n C` | RX -> TX | `SetStatus(Triggered, C)` | Shared USART2 | Existing legacy command, not the required product start command | `wm n triggered\r\n`; legacy armed state; no migration requirement to activate it |
| All | `get status` | RX -> TX | `HandleCommand()` -> each `PrintStatus()` | Shared USART2 | Two tokens | `wm status wm 1 <state> <C>ms ... wm 4 <state> <C>ms\r\n`; no counters |
| All | `system init` | RX -> TX | `App::Init()` | Shared USART2 | Two tokens | `OK\r\n`; stops WMs, resets software time; also invokes existing DAC initialization; not full count/history reset |
| All | `set time HH:MM` | RX -> TX | `RealTimer::Set()` | Shared USART2 | Parsed hour/minute, current code lacks bounds validation | `OK\r\n`; affects event timestamp, not pulse period |
| All | `get time` | RX -> TX | `RealTimer::Get()` | Shared USART2 | Two tokens | `sys time H:M:S\r\n` |
| All | `help` | RX -> TX | `HandleCommand()` help branch | Shared USART2 | Parser extracts two tokens before dispatch; an empty second token is not an error | Command lines followed by `OK\r\n` |
| All | Invalid ID/syntax | RX -> TX | `HandleCommand()` fallback | Shared USART2 | ID outside 1..4 or parse failure | `ERROR <cmd>\r\n`, with `(Scanner Error)` for scanner failure |
| All | Startup | TX only | `App::Task()` -> `SendResponse()` | Shared USART2 | No command | `App Started\r\n` |
| Historical only | Automatic valve-gated notifications | TX only | Legacy `Task()` StateChange -> `ControlWaterMeters()` -> `AppendStatus()` | Shared USART2 | Outside the confirmed UART start/stop requirement | Existing event formatting remains unused; do not add gates to emit these messages |

State tokens are `started`, `stopped`, `triggered`, and `running (triggered)`. Example after successful fresh starts: `wm status wm 1 started 1000ms wm 2 stopped 0ms wm 3 stopped 0ms wm 4 stopped 0ms` (actual retained values depend on earlier commands).

### Legacy and GUI compatibility

- Legacy `get status` begins `valves status <hex-bitmap>` and includes five WM entries. Current status begins `wm status`, contains four entries, and has no valve bitmap. This difference already exists; do not silently restore a valve bitmap or change the protocol during WM work.
- Legacy automatic WM gates came from `_valve[wmIdx].Get()`. This is historical comparison only: the new product does not require the old valve inputs, sampling, or valve-event messages. Preserve the legacy free-running pulse implementation, not its optional valve-gated feature.
- `FlexTesterGui.py` sends the same start/stop/trigger commands, but provides five WM channels; channel 5 is incompatible with the current accepted ID range. Host code must not treat it as a working fifth output.
- GUI `read_serial()` recognizes old valve/automatic WM events. Those events are not acceptance criteria for the new product; verify UART start/stop acknowledgements and actual output instead.
- GUI start/stop button handlers update their local graph immediately, without proving the firmware acknowledged success. `_schedule_pulse_toggle()` generates a local 50% graph (`max(50, int(rate / 2))` per toggle), whereas firmware requests 5% HIGH. CSV records these locally generated transitions, not sampled MCU edges.
- GUI positive-rate validation uses float and then `int(rate)`; a positive fractional value below 1 becomes zero on the wire. Firmware-side validation remains necessary even with GUI checks.
- There is no new migrated GUI in the active project. GUI/test-analysis compatibility is a separately approved host task; use serial logs plus a logic analyzer for this phase, not the graph as a waveform oracle.

## 9. FreeRTOS Dependency Matrix

All numbers below describe the current migrated configuration, not an inferred desired configuration.

| WM | Task | Priority | Stack | Period/Event | Dependencies |
|---|---|---|---|---|---|
| WM1 | `defaultTask` -> `StartDefaultTask()` -> `App::Task()` -> `_wmSim[0].Task(false)` | `osPriorityNormal` (24) | 2048 bytes (`512 * 4`) shared with all WM/App work | Up to 10-tick command wait when idle; no fixed WM period | `Clock`, GPIOF, command semaphore/mutex, shared UART responses |
| WM2 | Same task -> `_wmSim[1].Task(false)` | Normal (24) | Same shared 2048 bytes; not a separate allocation | Same sequential loop | `Clock`, GPIOE, shared Comm |
| WM3 | Same task -> `_wmSim[2].Task(false)` | Normal (24) | Same shared 2048 bytes | Same sequential loop | `Clock`, GPIOD, shared Comm |
| WM4 | Same task -> `_wmSim[3].Task(false)` | Normal (24) | Same shared 2048 bytes | Same sequential loop | `Clock`, GPIOD, shared Comm |
| All | `Comm` -> `Comm::Task()` | Normal (24) | 4096 bytes | One-byte receive polling; `osDelay(10)` when no byte or previous command pending | USART2 RX DMA/CNDTR, mutex, semaphore, blocking echo TX |
| All | Kernel/SysTick (not WM task) | SysTick IRQ 15; peripheral UART/DMA IRQs 5 | No dedicated WM stack | 1000 Hz kernel tick | `configUSE_PREEMPTION=1`, FreeRTOS heap 16384 bytes, PendSV/context switching |

`Comm`'s ready semaphore has maximum count 1; command storage is 256 bytes, token buffers 30 bytes, response buffer 200 bytes, RX ring 512 bytes. One pending command is held while App consumes it. Allocation/thread creation and `_rxDmaStatus` success are not checked by the current application; runtime verification must confirm both threads and DMA really started. Stack margin and heap health have not been measured on hardware. The bare-metal main-stack linker allocation is not the defaultTask stack size.

## 10. Migration Risk Assessment

| Item / proposed action | Risk | Why / verification required |
|---|---|---|
| Retain the four existing generated output bindings | LOW | Code and CubeMX agree; no firmware edit required. Verify external routing because software names cannot prove board wiring |
| Verify selected-channel UART activation and stop | MEDIUM | Existing implementation must be confirmed on the new STM32; no external activation interface is required |
| Review start-cycle input validation only if verification warrants a later fix | MEDIUM | Invalid values are an inherited software limitation, not a reason to add gates or alter valid-command behavior; any source fix requires separate approval |
| Decide counter, restart, and `system init` semantics | MEDIUM | Current count/resume retention is not an obvious reset contract. A silent reset change could invalidate quantity-based tests. Document and test before altering anything |
| Verify/reconcile timing at the required minimum cycle | MEDIUM for measurement; HIGH for a scheduling/peripheral redesign | Software polling plus blocking TX may miss deadlines. Integer 5% timing is shared legacy behavior, not automatically a new-board defect; do not redesign unless measurements prove requirements cannot be met |
| Check PA4/PA5 legacy startup DAC side effects | HIGH | PA5 sensor/DAC ownership and external electrical loading affect startup/reset safety, not WM activation; any source change needs separate approval |
| Leave unrelated TIM/ADC/UART/DMA/IRQ configuration unchanged | LOW | No WM pulse peripheral dependency requires their remapping. Verification is appropriate; adding WM timers or TX DMA is not part of the minimum migration |
| Hardware waveform, channel isolation, UART start/stop and reboot tests | MEDIUM | Required to verify the software on the new STM32; build success and GUI animation cannot replace measurements |

Additional inherited risks to record, not silently fix: RX ring overwrite detection and UART error recovery are limited; send failures are ignored by `Comm`; pulse count is signed int and has no overflow policy; parser does not require end-of-input after valid numeric tokens. These warrant later scoped review only if required by the approved acceptance criteria.

### Minimum-change conclusion

No WM source change is currently demonstrated as necessary for the confirmed `start wm n 1000` / `stop wm n` behavior. Existing GPIO bindings and free-running state-machine logic should be bench-verified first against approximately 1 Hz, 50 ms HIGH and 950 ms LOW, including legacy timing parity and safe startup/reset.

External triggering is not required, and its absence is not a migration problem. Do not replace `Task(false)` with an external gate, add inputs/interrupts, restore the removed valve model, or map sensors to WM activation. Any later source fix must address a verified software, timing, selected-channel command, or startup/reset defect and require approval.

## 11. Exact Implementation Plan

This is a proposal for approval, not authorization to edit. Preserve `FreeRTOS -> StartDefaultTask() -> runAppTask() -> App::Instance().Task()`, UART pins/baud/RX DMA, valid-command protocol, and existing simulator architecture.

1. Use the confirmed requirement: application/UART start/stop only, no external gating. Check software bindings PF8/PE15/PD11/PD12 against the physical output routing before attaching probes; do not change the hardware interface.
2. Verify startup/reset safety, including initial LOW, no unsolicited WM pulses, clock startup, and existing PA4/PA5 DAC side effects. Do not modify source or peripheral configuration as part of this verification.
3. With hardware/programming approval, use the existing successful ELF and verify `App Started`, `get status`, and USART2 communication. No flashing was performed during this analysis.
4. For n=1..4, send `start wm n 1000`; verify only the selected pin runs at approximately 1 Hz with 50 ms HIGH/950 ms LOW. Send `stop wm n`; verify that pin remains LOW and other channels are unaffected. Record scope/logic-analyzer traces, not GUI-generated waveforms.
5. Compare measured free-running timing and stop/restart behavior with the legacy implementation. The simulator and command-receiver sources matched in the earlier read-only comparison; the new CPU clock and blocking TX may affect measured scheduling jitter. Check concurrent channels and ordinary UART traffic without redesigning UART/RTOS.
6. Verify power-cycle, reset, `system init`, and stop/restart at different waveform phases. Record whether retained phase/cycle/count behavior matches the intended product reset contract. Any remaining clarification must concern these behaviors, not external signals.
7. If a verified defect appears, report its exact source/path and propose the smallest fix for approval. Do not preemptively change source, valid-command protocol, GPIOs, timers, DMA, interrupts, or the `Task(false)` call.
8. Only after an approved source fix, run focused checks and full Clean + Build, confirm linker/ELF, and repeat affected hardware tests. Stop on unrelated errors. If the unchanged implementation passes, no WM code modification is required. Keep the 3 existing indentation warnings outside scope.

### Analysis outcome

ANALYSIS STATUS: COMPLETE

BUILD STATUS: PASS (last verified full Clean + Build; no rebuild or source changes during analysis)

ELF STATUS: GENERATED (existing artifact verified)

CODE CHANGED: NO (only this report created)

WM1 STATUS: PF8 mapped; internal/UART start/stop implemented; approximately 1 Hz, 50 ms HIGH/950 ms LOW expected at C=1000; hardware/timing/startup verification pending.

WM2 STATUS: PE15 mapped; internal/UART start/stop implemented; same expected waveform; hardware/timing/startup verification pending.

WM3 STATUS: PD11 mapped; internal/UART start/stop implemented; same expected waveform; hardware/timing/startup verification pending.

WM4 STATUS: PD12 mapped; internal/UART start/stop implemented; same expected waveform; hardware/timing/startup verification pending.

EXTERNAL TRIGGER REQUIRED: NO

NEXT RECOMMENDED STEP: Bench-test the existing UART start/stop waveform on all four mapped outputs, compare legacy timing, and verify startup/reset safety before considering any source change.