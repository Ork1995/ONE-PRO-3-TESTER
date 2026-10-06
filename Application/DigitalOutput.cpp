/*
 * DigitalOutput.cpp
 *
 *  Created on: Sep 10, 2026
 */
#include "DigitalOutput.hpp"

/**
 * @brief Sets the GPIO output pin to HIGH or LOW and updates the internal state.
 * @param isHigh true = HIGH, false = LOW
 */
void DigitalOutput::Set(bool isHigh)
{
	_isHigh = isHigh;
	HAL_GPIO_WritePin(_port, _pin, (GPIO_PinState) isHigh);
}
