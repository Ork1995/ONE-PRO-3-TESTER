/*
 * WaterMeterSimulator.hpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include "gpio.h"
#include "TextPrinter.hpp"

struct WaterMeterSimulator
{
	enum class Status {
		Stopped,
		Started,
		Triggered,
		RunningTriggered
	};

	enum class StateChange {
		None,
		Started,
		Stopped
	};

	GPIO_TypeDef *_port;
	int _pin;
	int _id;
	uint32_t _cycleTimeMs;
	Status _status;
	uint32_t _periodMs;
	bool _isHigh;
	uint32_t _tLastSwitch;
	int _pulseCount = 0;

	// Resume state — saved when stopping mid-cycle
	bool _savedIsHigh = false;        // pin state at the moment of stop
	uint32_t _resumeRemainingMs = 0;  // ms remaining in that half-period
	bool _hasResumeState = false;     // true after the first stop

	void Set(bool isHigh);
	void SetStatus(Status status, uint32_t cycleTimeMs);
	void PrintStatus(TextPrinter &printer);
	StateChange Task(bool isValvesOpened);
};
