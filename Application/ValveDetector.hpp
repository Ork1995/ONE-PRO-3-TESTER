/*
 * ValveDetector.hpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include "gpio.h"
#include "TextPrinter.hpp"

struct ValveDetector
{
	GPIO_TypeDef *_port;
	int _pin;
	int _id;
	bool _activeLow; // New flag
	bool _prevState;
	
	// Debounce members
	bool _lastRawState;
	int _debounceCount;

	void Init();
	bool Get() const { return _prevState; }
	bool IsChanged();
	void PrintStatus(TextPrinter &printer);

private:
	bool Read();
};
