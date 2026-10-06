/*
 * RealTimer.hpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#pragma once

#include <stdint.h>

class RealTimer
{
public:
	RealTimer();

	void Set(int hour, int minute, int second);
	bool Get(int &hour, int &minute, int &second);

private:
	int _hour;
	int _minute;
	int _second;
	bool _isSet;
	uint32_t _tSet;
};
