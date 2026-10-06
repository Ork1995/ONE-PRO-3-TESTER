/*
 * RealTimer.cpp
 *
 *  Created on: Apr 2, 2025
 *      Author: Igor
 */

#include <RealTimer.hpp>
#include "Clock.hpp"

RealTimer::RealTimer():
	_hour(0), _minute(0), _second(0), _isSet(false), _tSet(0)
{
}

void RealTimer::Set(int hour, int minute, int second)
{
	_hour = hour;
	_minute = minute;
	_second = second;
	_tSet = Clock::GetTimeMsec();
	_isSet = true;
}

bool RealTimer::Get(int &hour, int &minute, int &second)
{
	if (!_isSet) {
		return false;
	}

	uint32_t tNow = Clock::GetTimeMsec();

	hour = _hour;
	minute = _minute;
	second = _second;

	second += (tNow - _tSet) / 1000;
	minute += second / 60;
	hour += minute / 60;

	second %= 60;
	minute %= 60;

	return true;
}
