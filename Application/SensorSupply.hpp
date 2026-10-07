/*
 * SensorSupply.hpp
 *
 *  Created on: Oct 7, 2026
 */

#pragma once

#include <stdint.h>
#include "tim.h"
#include "DigitalOutput.hpp"

/**
 * Sensor-supply controller: the boosted (~15 V) sensor rail and its four per-input
 * enables (VAI1..VAI4).
 *
 *   PWM  : TIM8 CH4 -> PC9 (VSEN_PWM), sets the booster output voltage (open loop)
 *   VSEN : PC6 (VSEN_ONF)  booster enable, active high
 *   VAIn : PC7 / PB9 / PB8 / PG2 (VAI1..VAI4_VEN)  per-input rail enable, active high
 *
 * Model: VSEN_ONF is the master switch, VAIn are channel switches behind it.
 *  - SetVoltage_mV() stores the setpoint; the PWM only carries it while the booster is
 *    enabled. With the booster disabled the PWM is held at 0 %.
 *  - SetVaiEnable() records which rails are wanted. A rail's pin only goes high while the
 *    booster is enabled, so a VAIn pin is never high without VSEN_ONF.
 *  - Enable order : duty -> VSEN_ONF -> VAIn.   Disable order: VAIn -> VSEN_ONF -> duty 0.
 *
 * The class knows nothing about UART/GUI; callers (e.g. App::HandleCommand) just use this API.
 * It is not thread-safe: call it from one task only.
 */
class SensorSupply
{
public:
	static constexpr uint8_t VAI_COUNT = 4;

	// Allowed setpoint range. Lower bound = 14 % duty (carried over from the Flex Lite
	// firmware's 14..100 % limit), upper bound = booster full scale.
	static constexpr uint32_t MIN_MV = 2100;
	static constexpr uint32_t MAX_MV = 15000;

	// Nominal transfer function: Vout = FULL_SCALE_MV * duty. See VoltageToDutyPercent().
	static constexpr uint32_t FULL_SCALE_MV = 15000;

	/// Hardware binding, supplied by the board-specific code (see App::App()).
	struct Config
	{
		TIM_HandleTypeDef *timer;        // timer configured for PWM (already initialised by CubeMX)
		uint32_t channel;                // TIM_CHANNEL_x carrying VSEN_PWM
		DigitalOutput vsenOnf;           // booster enable
		DigitalOutput vaiVen[VAI_COUNT]; // VAI1..VAI4 rail enables, index 0 = VAI1
	};

	explicit SensorSupply(const Config &config);

	/**
	 * Drive every enable low, start the PWM at 0 % and reset the setpoint to MIN_MV.
	 * Safe to call again (e.g. on 'system init'); the PWM is only started once.
	 * @return true if the PWM is running. When false, SetVsenEnable(true) is refused.
	 */
	bool Init();

	/**
	 * Set the requested booster voltage. The value is clamped to [MIN_MV, MAX_MV].
	 * If the booster is enabled the PWM is updated immediately, otherwise it is applied
	 * on the next SetVsenEnable(true).
	 * @return the value actually used (after clamping)
	 */
	uint32_t SetVoltage_mV(uint32_t mv);

	/**
	 * Enable/disable the booster. Enabling loads the PWM with the setpoint first, then raises
	 * VSEN_ONF, then raises the VAIn rails that were requested. Disabling lowers the VAIn
	 * pins, then VSEN_ONF, then sets the PWM to 0 %; the per-rail requests are kept.
	 * @return false only if enabling was refused because the PWM is not running
	 */
	bool SetVsenEnable(bool enable);

	/**
	 * Request/release one VAI rail.
	 * @param channel 1..VAI_COUNT
	 * @return false if the channel is out of range
	 */
	bool SetVaiEnable(uint8_t channel, bool enable);

	/// Everything off: VAIn low, VSEN_ONF low, PWM 0 %, all rail requests cleared. Keeps the setpoint.
	void AllOff();

	// ---- State ----
	uint32_t GetRequestedVoltage_mV() const { return _requestedMv; }
	bool IsPwmRunning() const { return _pwmRunning; }
	bool IsVsenEnabled() const { return _vsenEnabled; }
	bool IsVaiRequested(uint8_t channel) const;   // rail wanted by the caller
	bool IsVaiActive(uint8_t channel) const;      // rail pin is actually high
	uint32_t GetCompareValue() const;             // live CCR of the PWM channel
	uint32_t GetDutyPercentX100() const;          // live duty in 0.01 % units (5000 = 50.00 %)

	// ---- Conversion (the one place that maps voltage to PWM) ----
	static float VoltageToDutyPercent(uint32_t mv);                  // mV -> duty [0..100] %
	static uint32_t DutyPercentToCompare(float percent, uint32_t arr); // duty % -> CCR for a counter with auto-reload 'arr'

private:
	TIM_HandleTypeDef *_timer;
	uint32_t _channel;
	DigitalOutput _vsenOnf;
	DigitalOutput _vai[VAI_COUNT];

	bool _pwmRunning = false;
	bool _vsenEnabled = false;
	bool _vaiRequested[VAI_COUNT] = {};
	uint32_t _requestedMv = MIN_MV;

	void WriteCompare(uint32_t compare);
	uint32_t CompareForVoltage(uint32_t mv) const;
};
