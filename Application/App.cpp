/*
 * App.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#include "App.hpp"
#include "cmsis_os.h"
#include "gpio.h"
#include "TextScanner.hpp"
#include "TextPrinter.hpp"

App::App():
	_comm { _board._commUart },
	_wmSim {
		{ ._port = WM_SIM_1_GPIO_Port, ._pin = WM_SIM_1_Pin, ._id = 1 },
		{ ._port = WM_SIM_2_GPIO_Port, ._pin = WM_SIM_2_Pin, ._id = 2 },
		{ ._port = WM_SIM_3_GPIO_Port, ._pin = WM_SIM_3_Pin, ._id = 3 },
		{ ._port = WM_SIM_4_GPIO_Port, ._pin = WM_SIM_4_Pin, ._id = 4 },
	},
	_sensorSupply {
		SensorSupply::Config {
			.timer = &htim8,
			.channel = TIM_CHANNEL_4,	// TIM8_CH4 -> PC9 (VSEN_PWM)
			.vsenOnf = { ._port = VSEN_ONF_GPIO_Port, ._pin = VSEN_ONF_Pin, ._id = 0 },
			.vaiVen = {
				{ ._port = VAI1_VEN_GPIO_Port, ._pin = VAI1_VEN_Pin, ._id = 1 },
				{ ._port = VAI2_VEN_GPIO_Port, ._pin = VAI2_VEN_Pin, ._id = 2 },
				{ ._port = VAI3_VEN_GPIO_Port, ._pin = VAI3_VEN_Pin, ._id = 3 },
				{ ._port = VAI4_VEN_GPIO_Port, ._pin = VAI4_VEN_Pin, ._id = 4 },
			},
		}
	}

#if PS_COUNT > 0
	,
	_psOut {
		{ ._port = PS1_GPIO_Port, ._pin = PS1_Pin, ._id = 1 },
		{ ._port = PS2_GPIO_Port, ._pin = PS2_Pin, ._id = 2 },
		{ ._port = PS3_GPIO_Port, ._pin = PS3_Pin, ._id = 3 },
		{ ._port = PS4_GPIO_Port, ._pin = PS4_Pin, ._id = 4 },
		{ ._port = PS5_GPIO_Port, ._pin = PS5_Pin, ._id = 5 },
	}
#endif
{}

void App::Init()
{
	_sensorSupply.Init();	// PWM at 0 %, VSEN_ONF and VAI1..4 off

	for (auto &wm: _wmSim) {
		wm.SetStatus(WaterMeterSimulator::Status::Stopped, 0);
	}

	for (auto &ps: _psOut) {
		ps.Set(false);
	}

	_realTimer.Set(0,0,0);
	
	_dac.Init();
	_dac.SetVoltage(0.0f);
	_dac.SetVoltage2(0.0f);
}

void App::Task()
{
	Init();

	Buffer<100> startupMsg;
	TextPrinter p(startupMsg);
	p << "App Started\r\n";
	_comm.SendResponse(startupMsg);

	for(;;)
	{
		Buffer<Comm::MAX_CMD_LEN> cmdBuf;
		if (_comm.ReceiveCommand(cmdBuf, 10)) {
			HandleCommand(cmdBuf);
		}

		ControlWaterMeters();
	}
}

void App::AppendStatus(TextPrinter &p)
{
	int hour = 0, minute = 0, second = 0;
	_realTimer.Get(hour, minute, second);

	// Print zero-padded time
	if (hour < 10)   p << "0"; p << (long)hour   << ":";
	if (minute < 10) p << "0"; p << (long)minute << ":";
	if (second < 10) p << "0"; p << (long)second;

	p << " | wm1=" << _wmSim[0]._pulseCount
	  << " wm2=" << _wmSim[1]._pulseCount
	  << " wm3=" << _wmSim[2]._pulseCount
	  << " wm4=" << _wmSim[3]._pulseCount;
}

void App::ControlWaterMeters()
{
	for (int wmIdx = 0; wmIdx < WM_SIM_COUNT; ++wmIdx) {
		auto &wm = _wmSim[wmIdx];
		WaterMeterSimulator::StateChange change = wm.Task(false);
		
		if (change != WaterMeterSimulator::StateChange::None) {
			Buffer<Comm::MAX_RESP_LEN> msg;
			TextPrinter p(msg);
			p << "wm " << wm._id << " ";
			if (change == WaterMeterSimulator::StateChange::Started) {
				wm._pulseCount = 0;
				p << "started working at ";
			} else {
				p << "stopped working at ";
			}
			AppendStatus(p);
			p << "\r\n";
			_comm.SendResponse(msg);
			if (change == WaterMeterSimulator::StateChange::Stopped) {
				wm._pulseCount = 0;
			}
		}
	}
}

void App::ToggleWaterMeter(int wmIdx, TextPrinter &response)
{
	auto &wm = _wmSim[wmIdx];

	if (wm._status == WaterMeterSimulator::Status::Stopped) {
		wm.SetManualHigh();
		response << "wm " << (long)wm._id << " manual on";
	}
	else if (wm._status == WaterMeterSimulator::Status::ManualHigh) {
		wm.SetStatus(WaterMeterSimulator::Status::Stopped, 0);
		response << "wm " << (long)wm._id << " manual off";
	}
	else {
		// Running or armed by a start/trigger command; that operation keeps ownership
		response << "ERROR wm " << (long)wm._id << " busy";
	}
}

/**
 * 'set vsen <mV>', 'set vsen_en on|off', 'set vai <1-4> on|off'.
 * Translates the text command into SensorSupply calls. Leaves 'response' empty if the
 * command is not a sensor-supply one or its arguments are invalid (caller reports the error).
 */
void App::HandleSetSensorSupply(BufferView<> &token2, TextScanner &scanner, TextPrinter &response)
{
	if (token2 == "vsen") {
		long mv;
		scanner >> mv;
		if (!scanner.IsError() && mv >= 0) {
			uint32_t applied = _sensorSupply.SetVoltage_mV((uint32_t)mv);
			response << "vsen set to " << (long)applied << " mV";
			if (applied != (uint32_t)mv) {
				response << " (clamped from " << mv << " mV)";
			}
			if (!_sensorSupply.IsVsenEnabled()) {
				response << " (booster off)";
			}
		}
	}
	else if (token2 == "vsen_en") {
		Buffer<Comm::MAX_TOKEN_LEN> onOff;
		scanner >> onOff;
		if (!scanner.IsError()) {
			if (onOff == "on") {
				if (_sensorSupply.SetVsenEnable(true)) {
					response << "vsen_en ON, " << (long)_sensorSupply.GetRequestedVoltage_mV() << " mV";
				}
				else {
					response << "ERROR vsen pwm not running";
				}
			}
			else if (onOff == "off") {
				_sensorSupply.SetVsenEnable(false);
				response << "vsen_en OFF";
			}
		}
	}
	else if (token2 == "vai") {
		long ch;
		Buffer<Comm::MAX_TOKEN_LEN> onOff;
		scanner >> ch >> onOff;
		if (!scanner.IsError() && ch >= 1 && ch <= SensorSupply::VAI_COUNT) {
			bool isOn = (onOff == "on");
			if (isOn || onOff == "off") {
				_sensorSupply.SetVaiEnable((uint8_t)ch, isOn);
				response << "vai " << ch << (isOn ? " ON" : " OFF");
				if (isOn && !_sensorSupply.IsVsenEnabled()) {
					response << " (pending: vsen_en is off)";
				}
			}
		}
	}
}

void App::AppendSensorSupplyStatus(TextPrinter &p)
{
	const uint32_t dutyX100 = _sensorSupply.GetDutyPercentX100();
	const uint32_t dutyFrac = dutyX100 % 100;

	p << "vsen en=" << (long)_sensorSupply.IsVsenEnabled()
	  << " mv=" << (long)_sensorSupply.GetRequestedVoltage_mV()
	  << " ccr4=" << (long)_sensorSupply.GetCompareValue()
	  << " duty=" << (long)(dutyX100 / 100) << "." << (dutyFrac < 10 ? "0" : "") << (long)dutyFrac << "%"
	  << " pwm=" << (_sensorSupply.IsPwmRunning() ? "run" : "stopped");

	for (uint8_t ch = 1; ch <= SensorSupply::VAI_COUNT; ++ch) {
		p << " vai" << (long)ch << "="
		  << (_sensorSupply.IsVaiActive(ch) ? "on" : (_sensorSupply.IsVaiRequested(ch) ? "pend" : "off"));
	}
}

void App::HandleCommand(const BufferView<> &cmd)
{
	TextScanner scanner(cmd);

	Buffer<Comm::MAX_RESP_LEN> respBuf;
	TextPrinter response(respBuf);

	Buffer<Comm::MAX_TOKEN_LEN> token1, token2;
	scanner >> token1 >> token2;

	if (!scanner.IsError()) {
		if (token1 == "system") {
			if (token2 == "init") {
				Init();
				response << "OK";
			}
		}
		else if (token1 == "set") {
			if (token2 == "time") {
				long hour, minute;
				scanner >> hour >> ":" >> minute;
				if (!scanner.IsError()) {
					_realTimer.Set(hour, minute, 0);
					response << "OK";
				}
			}
			else if (token2 == "dac") {
				long mv;
				scanner >> mv;
				if (!scanner.IsError()) {
					_dac.SetVoltage((float)mv / 1000.0f);
					response << "DAC set to " << mv << "mV";
				}
			}
			else if (token2 == "dac1") {
				long mv;
				scanner >> mv;
				if (!scanner.IsError()) {
					_dac.SetVoltage((float)mv / 1000.0f);
					response << "DAC1 set to " << mv << "mV";
				}
			}
			else if (token2 == "dac2") {
				long mv;
				scanner >> mv;
				if (!scanner.IsError()) {
					_dac.SetVoltage2((float)mv / 1000.0f);
					response << "DAC2 set to " << mv << "mV";
				}
			}
			else if (token2 == "vsen" || token2 == "vsen_en" || token2 == "vai") {
				HandleSetSensorSupply(token2, scanner, response);
			}
			else if (token2 == "ps") {
				long id;
				Buffer<Comm::MAX_TOKEN_LEN> onOff;
				scanner >> id >> onOff;
				if (!scanner.IsError() && id >= 1 && id <= PS_COUNT) {
					if (onOff == "on") {
						_psOut[id - 1].Set(true);
						response << "ps " << id << " ON";
					}
					else if (onOff == "off") {
						_psOut[id - 1].Set(false);
						response << "ps " << id << " OFF";
					}
				}
			}

		}
		else if (token1 == "get") {
			if (token2 == "time") {
				int hour, minute, second;
				if (_realTimer.Get(hour, minute, second)) {
					response << "sys time " << hour << ":" << minute << ":" << second;
				}
			}
			else if (token2 == "vsen") {
				AppendSensorSupplyStatus(response);
			}
			else if (token2 == "status") {
				response << "wm status";
				for (auto wm: _wmSim) {
					wm.PrintStatus(response);
				}
			}
		}
		else if (token1 == "start") {
			if (token2 == "wm") {
				long id, cycleTimeMs;
				scanner >> id >> cycleTimeMs;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT) {
					_wmSim[id - 1].SetStatus(WaterMeterSimulator::Status::Started, (uint32_t)cycleTimeMs);
					response << "wm " << id << " started";
				}
			}
		}
		else if (token1 == "stop") {
			if (token2 == "wm") {
				long id;
				scanner >> id;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT) {
					_wmSim[id - 1].SetStatus(WaterMeterSimulator::Status::Stopped, 0);
					response << "wm " << id << " stopped";
				}
			}
		}
		else if (token1 == "trigger") {
			if (token2 == "wm") {
				long id, cycleTimeMs;
				scanner >> id >> cycleTimeMs;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT) {
					_wmSim[id - 1].SetStatus(WaterMeterSimulator::Status::Triggered, (uint32_t)cycleTimeMs);
					response << "wm " << id << " triggered";
				}
			}
		}
		else if (token1 == "toggle") {
			if (token2 == "wm") {
				long id;
				scanner >> id;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT) {
					ToggleWaterMeter(id - 1, response);
				}
			}
		}
		else if (token1 == "help") {
			Buffer<100> helpBuf;
			TextPrinter helpPrinter(helpBuf);
			
			helpPrinter << "Available Commands:\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();
			
			helpPrinter << " system init\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set time HH:MM\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get time\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get status\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set dac1 <mV>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set dac2 <mV>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set ps <id> on|off\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vsen <mV>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vsen_en on|off\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vai <1-4> on|off\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get vsen\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " start wm <id> <cycle_ms>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " stop wm <id>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " trigger wm <id> <cycle_ms>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " toggle wm <id>\r\n";
			_comm.SendResponse(helpBuf); helpBuf.Reset();

			response << "OK";
		}
	}

	if (respBuf.Len() <= 0 || scanner.IsError()) {
		response << "ERROR " << cmd;
		if (scanner.IsError()) {
			response << " (Scanner Error)";
		}
	}

	response << "\r\n";

	_comm.SendResponse(respBuf);
}
