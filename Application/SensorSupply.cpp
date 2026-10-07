/*
 * SensorSupply.cpp
 *
 *  Created on: Oct 7, 2026
 */

#include "SensorSupply.hpp"

SensorSupply::SensorSupply(const Config &config):
	_timer(config.timer),
	_channel(config.channel),
	_vsenOnf(config.vsenOnf)
{
	for (uint8_t i = 0; i < VAI_COUNT; ++i) {
		_vai[i] = config.vaiVen[i];
	}
}

bool SensorSupply::Init()
{
	// Pins first: nothing may be energised while the PWM is still being brought up.
	// On the first call the PWM is not running yet, so this only touches the pins.
	AllOff();
	_requestedMv = MIN_MV;

	// HAL_TIM_PWM_Start() fails on a channel that is already running ('system init'),
	// so only start it once.
	if (!_pwmRunning) {
		__HAL_TIM_SET_COMPARE(_timer, _channel, 0);
		_pwmRunning = (HAL_TIM_PWM_Start(_timer, _channel) == HAL_OK);
	}

	if (_pwmRunning) {
		WriteCompare(0);
	}

	return _pwmRunning;
}

uint32_t SensorSupply::SetVoltage_mV(uint32_t mv)
{
	if (mv < MIN_MV) {
		mv = MIN_MV;
	}
	if (mv > MAX_MV) {
		mv = MAX_MV;
	}

	_requestedMv = mv;

	// While the booster is off the PWM stays at 0 %; the setpoint is applied on enable.
	if (_vsenEnabled) {
		WriteCompare(CompareForVoltage(mv));
	}

	return mv;
}

bool SensorSupply::SetVsenEnable(bool enable)
{
	if (enable) {
		if (!_pwmRunning) {
			return false;
		}
		if (_vsenEnabled) {
			return true;
		}

		WriteCompare(CompareForVoltage(_requestedMv));   // 1. PWM duty
		_vsenOnf.Set(true);                               // 2. booster
		_vsenEnabled = true;
		for (uint8_t i = 0; i < VAI_COUNT; ++i) {         // 3. requested rails
			if (_vaiRequested[i]) {
				_vai[i].Set(true);
			}
		}
	}
	else {
		// Pins are always driven low, even if the state says they already are:
		// Init() relies on this to force a known state.
		for (uint8_t i = 0; i < VAI_COUNT; ++i) {         // 1. rails
			_vai[i].Set(false);
		}
		_vsenOnf.Set(false);                              // 2. booster
		_vsenEnabled = false;
		if (_pwmRunning) {                                // 3. PWM duty 0 %
			WriteCompare(0);
		}
	}

	return true;
}

bool SensorSupply::SetVaiEnable(uint8_t channel, bool enable)
{
	if (channel < 1 || channel > VAI_COUNT) {
		return false;
	}

	const uint8_t i = channel - 1;
	_vaiRequested[i] = enable;
	_vai[i].Set(enable && _vsenEnabled);   // never high without VSEN_ONF

	return true;
}

void SensorSupply::AllOff()
{
	SetVsenEnable(false);

	for (uint8_t i = 0; i < VAI_COUNT; ++i) {
		_vaiRequested[i] = false;
	}
}

bool SensorSupply::IsVaiRequested(uint8_t channel) const
{
	return channel >= 1 && channel <= VAI_COUNT && _vaiRequested[channel - 1];
}

bool SensorSupply::IsVaiActive(uint8_t channel) const
{
	return channel >= 1 && channel <= VAI_COUNT && _vai[channel - 1]._isHigh;
}

uint32_t SensorSupply::GetCompareValue() const
{
	return __HAL_TIM_GET_COMPARE(_timer, _channel);
}

uint32_t SensorSupply::GetDutyPercentX100() const
{
	// duty = CCR / (ARR + 1). TIM8 is a 16-bit timer, so CCR * 10000 cannot overflow 32 bits.
	const uint32_t period = __HAL_TIM_GET_AUTORELOAD(_timer) + 1U;
	return (GetCompareValue() * 10000U + period / 2U) / period;
}

void SensorSupply::WriteCompare(uint32_t compare)
{
	__HAL_TIM_SET_COMPARE(_timer, _channel, compare);

	// CCR is preloaded, so without an update event the new value is only latched at the next
	// counter overflow (up to ~2 ms later) - possibly after VSEN_ONF has already been raised.
	HAL_TIM_GenerateEvent(_timer, TIM_EVENTSOURCE_UPDATE);
}

uint32_t SensorSupply::CompareForVoltage(uint32_t mv) const
{
	return DutyPercentToCompare(VoltageToDutyPercent(mv), __HAL_TIM_GET_AUTORELOAD(_timer));
}

// ---------------------------------------------------------------------------------------
// Voltage -> PWM conversion.
//
// VoltageToDutyPercent() is the only place that encodes how the booster responds to the
// PWM. It currently uses the nominal relation taken from the Flex Lite firmware,
//     Vout = FULL_SCALE_MV * duty
// which has NOT been measured on this hardware. After bench characterisation (offset,
// gain, non-linearity, lookup table) change this function only; everything else calls it.
// ---------------------------------------------------------------------------------------
float SensorSupply::VoltageToDutyPercent(uint32_t mv)
{
	float percent = 100.0f * (float)mv / (float)FULL_SCALE_MV;

	if (percent > 100.0f) {
		percent = 100.0f;
	}

	return percent;
}

// duty = CCR / (ARR + 1). 100 % would need CCR = ARR + 1, which a 16-bit timer cannot hold,
// so full scale is capped at CCR = ARR (99.998 %, one timer tick low per period).
uint32_t SensorSupply::DutyPercentToCompare(float percent, uint32_t arr)
{
	if (!(percent > 0.0f)) {          // also catches NaN
		return 0;
	}
	if (percent >= 100.0f) {
		return arr;
	}

	const uint32_t compare = (uint32_t)(percent * (float)(arr + 1U) / 100.0f + 0.5f);

	return (compare > arr) ? arr : compare;
}
