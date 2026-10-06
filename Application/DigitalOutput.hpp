/*
 * DigitalOutput.hpp
 *
 *  Created on: Sep 10, 2026
 */

#pragma once

#include "gpio.h"

struct DigitalOutput
{
	GPIO_TypeDef *_port;
	int _pin;
	int _id;
	bool _isHigh = false;

	void Set(bool isHigh);
};
