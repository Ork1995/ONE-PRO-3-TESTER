/*
 * DacControl.hpp
 *
 *  Created on: Dec 22, 2025
 *      Author: Copilot
 */

#pragma once

#include "stm32l4xx.h"

class DacControl
{
public:
	DacControl();

	void Init();
	void SetValue(uint16_t value); // 0-4095, DAC1 Channel 1 (PA4)
	void SetVoltage(float voltage); // 0.0 - 3.3V, DAC1 Channel 1 (PA4)
	void SetValue2(uint16_t value); // 0-4095, DAC1 Channel 2 (PA5)
	void SetVoltage2(float voltage); // 0.0 - 3.3V, DAC1 Channel 2 (PA5)

private:
	bool _isInitialized;
};
