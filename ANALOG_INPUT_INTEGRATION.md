# Analog Input Integration

## Wiring and Pin Ownership

| Input | MCU pin | ADC peripheral/channel |
| --- | --- | --- |
| AI1 | PA5 | ADC1 / channel 10 |
| AI2 | PA1 | ADC1 / channel 6 |
| AI3 | PC2 | ADC3 / channel 3 |
| AI4 | PC3 | ADC3 / channel 4 |

PA5 is reserved for AI1. The Tester initializes its DAC with channel 2 disabled
and rejects `set dac2` commands. DAC1 on PA4 remains available. Do not connect a
DAC2 output source to AI1 while measuring an external sensor.

Connect each sensor's 0-10 V signal to the corresponding board analog input
connector, THROUGH the input conditioning circuit, with a common signal ground.
Never apply 10 V directly to an STM32 pin. A floating input is not a reliable
zero reading. Sampling does not automatically enable sensor supply outputs;
use an appropriate external supply or the existing Sensor Supply controls.

## Adaptation from Flex Lite

The source implementation is `Core/Src/main.c` in Netafim_Flex_Lite:
`Configure_AI`, `ADC_Read`, `ADC_Read_Avg`, and the 0-10 V menu operation.

For every input the Tester selects voltage mode: `I_SNSx_SEL=0`,
`V_SNSx_10K=0`, `V_SNSx_3K3=1`, and waits 50 ms for settling at initialization.
ADC1 and ADC3 are calibrated once at initialization. The generated 16-rank
sequence is shortened to a single conversion. Each request selects rank 1,
uses 247.5-cycle sampling and averages eight independent software-triggered
conversions. HAL errors return an error response rather than a numeric value.

The Tester now enables the same 2.5 V VREFBUF as Flex Lite, before calibration.
It disables the buffer before configuring scale 1 and clearing high impedance,
then waits for HAL to report buffer readiness. A shared `ANALOG_VREF_MV=2500`
constant is used by ADC and DAC voltage scaling:

`input_mV = round(raw * 2500 * (13.3 / 3.3) / 4095)`

This assumes the same hardware as Flex Lite: R66 is not populated and the
buffer is the only source for VREF+. Before flashing, verify that VREF+ is NOT
tied to an external voltage source; enabling the buffer against another source
can cause contention. VDDA must be at least 2.8 V for this buffer setting.
Confirm the same 10 kohm / 3.3 kohm input divider on the actual board.
Full ADC scale is nominally 10.076 V with this reference; that is NOT
permission to exceed the specified 0-10 V input range. Readings are not clamped
to 10 V, and raw 4095 is displayed as `ADC full scale`.

The Tester now disables all digital-input pull-ups using `MCU_AI2DIx_NEN`:
AI1 PD15, AI2 PD3, AI3 PE0, AI4 PB6 are initialized as push-pull outputs HIGH
by `App::InitAnalogInputs`. Definitions are in the user section of `main.h`.
Verify these connections against the actual board revision.

DAC1 remains available, but its maximum output is now 2.5 V. Firmware clamps
requests to 0-2500 mV and reports the applied setpoint; the GUI uses the same
limit. DAC2 remains disabled to reserve PA5 for AI1.

## Commands and GUI

`get ain 1`, `get ain 2`, `get ain 3`, and `get ain 4` sample individual inputs.

Example response: `ain 1 raw=2032 mv=5000`.

Errors include `ERROR ain 1 not ready`, `config`, `conversion`, and `stop`.
Startup reports `ADC init=ready configured_vref=2500mV`, or `init=failed` if
the reference or calibration failed. The reference field is the configured
value, not a physical measurement of VREF+.

In `New folder/FlexTesterGui.py`, connect the Tester through Main Controller,
and sampling starts automatically. Each of the four Sensor Supply rows shows
the corresponding measured input as `VIN: 5000 mV`, separately from the supply
voltage preset. Analog Inputs mirrors these VIN values, raw ADC counts and status.
Read samples one channel; Read selected samples checked rows; Auto sample
cycles through checked rows. Requests are serialized at 250 ms intervals,
approximately one update per second per input when all four are selected.
Selecting only one row samples it approximately four times per second.
Timeouts (1.5 seconds) and ADC errors clear the affected reading but polling
continues. Unsupported firmware stops auto sampling and displays an update
requirement. Disconnect, reconnect, system initialization and board restart
clear previous readings; reconnect and initialization restart auto sampling. FLEX CLI's
second serial port is not used for ADC requests.

## Hardware Acceptance

1. Build and flash the Tester firmware, not the Flex Lite firmware.
2. Check startup reports ADC ready, measure VREF+ at approximately 2.5 V,
   and verify PD15, PD3, PE0 and PB6 are HIGH.
3. Apply known 0 V, 5 V and 10 V signals to each input separately and compare
   with a multimeter. Nominal raw counts are 0, 2032 and 4064 respectively.
4. Confirm that changing one signal does not change the other three readings.
5. Verify DAC1 still works; DAC2 must remain disabled while PA5 is AI1.
6. Test auto sampling together with water-meter simulation and sensor supply.

Software checks do not replace these physical measurements. No board was
flashed or measured as part of this integration.