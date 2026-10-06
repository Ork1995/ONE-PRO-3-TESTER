/*
 * ValveDetector.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#include <ValveDetector.hpp>

void ValveDetector::Init()
{
	_prevState = Read();
	_lastRawState = _prevState;
	_debounceCount = 0;
}

bool ValveDetector::Read()
{
	bool state = HAL_GPIO_ReadPin(_port, _pin) != GPIO_PIN_RESET;
	return _activeLow ? !state : state;
}

bool ValveDetector::IsChanged()
{
	bool rawState = Read();
	
	if (rawState != _lastRawState) {
		_debounceCount = 0;
		_lastRawState = rawState;
	}
	else {
		if (_debounceCount < 5) { // Wait for 5 stable samples
			_debounceCount++;
			if (_debounceCount == 5) {
				if (rawState != _prevState) {
					_prevState = rawState;
					return true;
				}
			}
		}
	}
	
	return false;
}

void ValveDetector::PrintStatus(TextPrinter &printer)
{
	printer << "valve " << _id << " " << (_prevState ? "open" : "close");
}
