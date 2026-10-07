/*
 * App.h
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include <array>

#include "Board.hpp"
#include "WaterMeterSimulator.hpp"
#include "DigitalOutput.hpp"
#include "Comm.hpp"
#include "CLIManager.h"
#include "RealTimer.hpp"
#include "DacControl.hpp"

class App
{
private:
	App();

public:
	static constexpr int WM_SIM_COUNT = 4;
	#if defined(PS1_Pin) && defined(PS2_Pin) && defined(PS3_Pin) && defined(PS4_Pin) && defined(PS5_Pin)
	static constexpr int PS_COUNT = 5;
	#else
	static constexpr int PS_COUNT = 0;
	#endif

	static App &Instance() {
		static App _instance;
		return _instance;
	}

	Board &GetBoard() { return _board; }

	void Task();

private:
	Board _board;
	// TODO: UART to be defined
	//CLIManager _cli;
	Comm _comm;
	WaterMeterSimulator _wmSim[WM_SIM_COUNT];
	std::array<DigitalOutput, PS_COUNT> _psOut;
	RealTimer _realTimer;
	DacControl _dac;

	void Init();
	void ControlWaterMeters();
	void ToggleWaterMeter(int wmIdx, TextPrinter &response);
	void HandleCommand(const BufferView<> &cmd);
	void AppendStatus(TextPrinter &p);
};
