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
#include "adc.h"

App::App():
	_uartTransport { _board._commUart },
	_comm { _uartTransport },
	_usbComm { _usbTransport, &_usbResources },
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
	
	_dac.Init(false);
	_dac.SetVoltage(0.0f);
	InitAnalogInputs();
}

void App::InitAnalogInputs()
{
	_analogReady = false;
	GPIO_InitTypeDef pullupControl = {};
	pullupControl.Mode = GPIO_MODE_OUTPUT_PP;
	pullupControl.Pull = GPIO_NOPULL;
	pullupControl.Speed = GPIO_SPEED_FREQ_LOW;
	pullupControl.Pin = MCU_AI2DI1_NEN_Pin | MCU_AI2DI2_NEN_Pin;
	HAL_GPIO_WritePin(GPIOD, pullupControl.Pin, GPIO_PIN_SET);
	HAL_GPIO_Init(GPIOD, &pullupControl);
	pullupControl.Pin = MCU_AI2DI3_NEN_Pin;
	HAL_GPIO_WritePin(MCU_AI2DI3_NEN_GPIO_Port, pullupControl.Pin, GPIO_PIN_SET);
	HAL_GPIO_Init(MCU_AI2DI3_NEN_GPIO_Port, &pullupControl);
	pullupControl.Pin = MCU_AI2DI4_NEN_Pin;
	HAL_GPIO_WritePin(MCU_AI2DI4_NEN_GPIO_Port, pullupControl.Pin, GPIO_PIN_SET);
	HAL_GPIO_Init(MCU_AI2DI4_NEN_GPIO_Port, &pullupControl);
	HAL_GPIO_WritePin(I_SNS1_SEL_GPIO_Port, I_SNS1_SEL_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(I_SNS2_SEL_GPIO_Port, I_SNS2_SEL_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(I_SNS3_SEL_GPIO_Port, I_SNS3_SEL_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(I_SNS4_SEL_GPIO_Port, I_SNS4_SEL_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(V_SNS1_10K_GPIO_Port, V_SNS1_10K_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(V_SNS2_10K_GPIO_Port, V_SNS2_10K_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(V_SNS3_10K_GPIO_Port, V_SNS3_10K_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(V_SNS4_10K_GPIO_Port, V_SNS4_10K_Pin, GPIO_PIN_RESET);
	HAL_GPIO_WritePin(V_SNS1_3K3_GPIO_Port, V_SNS1_3K3_Pin, GPIO_PIN_SET);
	HAL_GPIO_WritePin(V_SNS2_3K3_GPIO_Port, V_SNS2_3K3_Pin, GPIO_PIN_SET);
	HAL_GPIO_WritePin(V_SNS3_3K3_GPIO_Port, V_SNS3_3K3_Pin, GPIO_PIN_SET);
	HAL_GPIO_WritePin(V_SNS4_3K3_GPIO_Port, V_SNS4_3K3_Pin, GPIO_PIN_SET);
	osDelay(50);
	HAL_SYSCFG_DisableVREFBUF();
	HAL_SYSCFG_VREFBUF_VoltageScalingConfig(SYSCFG_VREFBUF_VOLTAGE_SCALE1);
	HAL_SYSCFG_VREFBUF_HighImpedanceConfig(SYSCFG_VREFBUF_HIGH_IMPEDANCE_DISABLE);
	if (HAL_SYSCFG_EnableVREFBUF() != HAL_OK) {
		return;
	}
	if (HAL_ADCEx_Calibration_Start(&hadc1, ADC_SINGLE_ENDED) != HAL_OK ||
	    HAL_ADCEx_Calibration_Start(&hadc3, ADC_SINGLE_ENDED) != HAL_OK) {
		return;
	}
	MODIFY_REG(hadc1.Instance->SQR1, ADC_SQR1_L, 0UL);
	MODIFY_REG(hadc3.Instance->SQR1, ADC_SQR1_L, 0UL);
	_analogReady = true;
}

void App::ReadAnalogInput(uint8_t channel, TextPrinter &response)
{
	if (!_analogReady) {
		response << "ERROR ain " << (long)channel << " not ready";
		return;
	}
	ADC_HandleTypeDef *adc = channel <= 2 ? &hadc1 : &hadc3;
	const uint32_t channels[] = { ADC_CHANNEL_10, ADC_CHANNEL_6, ADC_CHANNEL_3, ADC_CHANNEL_4 };
	ADC_ChannelConfTypeDef config = {};
	config.Channel = channels[channel - 1];
	config.Rank = ADC_REGULAR_RANK_1;
	config.SamplingTime = ADC_SAMPLETIME_247CYCLES_5;
	config.SingleDiff = ADC_SINGLE_ENDED;
	config.OffsetNumber = ADC_OFFSET_NONE;
	if (HAL_ADC_ConfigChannel(adc, &config) != HAL_OK) {
		response << "ERROR ain " << (long)channel << " config";
		return;
	}
	uint32_t sum = 0;
	for (uint8_t sample = 0; sample < 8; ++sample) {
		if (HAL_ADC_Start(adc) != HAL_OK || HAL_ADC_PollForConversion(adc, 10) != HAL_OK) {
			HAL_ADC_Stop(adc);
			response << "ERROR ain " << (long)channel << " conversion";
			return;
		}
		sum += HAL_ADC_GetValue(adc);
		if (HAL_ADC_Stop(adc) != HAL_OK) {
			response << "ERROR ain " << (long)channel << " stop";
			return;
		}
	}
	const uint32_t raw = (sum + 4) / 8;
	const uint32_t mv = (raw * ANALOG_VREF_MV * 133UL + (4095UL * 33UL) / 2) / (4095UL * 33UL);
	response << "ain " << (long)channel << " raw=" << (long)raw << " mv=" << (long)mv;
}

void App::Task()
{
	Init();

	Buffer<100> startupMsg;
	TextPrinter p(startupMsg);
	p << "App Started\r\n";
	p << "ADC init=" << (_analogReady ? "ready" : "failed")
	  << " configured_vref=" << (long)ANALOG_VREF_MV << "mV\r\n";
	_comm.SendResponse(startupMsg);
	if (_usbComm.IsReady()) {
		_usbTransport.Start();
	}

	for(;;)
	{
		Buffer<Comm::MAX_CMD_LEN> cmdBuf;
		if (_comm.ReceiveCommand(cmdBuf, 10)) {
			HandleCommand(cmdBuf, _comm);
		}
		uint32_t responseSession;
		if (_usbTransport.BeginResponse(&responseSession)) {
			if (_usbComm.ReceiveCommand(cmdBuf, 0, responseSession)) {
				HandleCommand(cmdBuf, _usbComm);
			}
			_usbTransport.EndResponse();
		}

		ControlWaterMeters();
		const uint8_t completed = _sensorSupply.Task();
		if (completed != 0) {
			Buffer<Comm::MAX_RESP_LEN> message;
			TextPrinter output(message);
			output << "vai " << (long)completed << " OFF pulse complete\r\n";
			AppendSensorSupplyStatus(output);
			output << "\r\n";
			SendEvent(message);
		}
	}
}

void App::SendEvent(const BufferView<> &message)
{
	_comm.SendResponse(message);
	if (_usbComm.IsReady()) {
		_usbComm.SendEvent(message);
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
			SendEvent(msg);
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
			if (applied != 0 && (applied < SensorSupply::CALIBRATED_MIN_MV || applied > SensorSupply::CALIBRATED_MAX_MV)) {
				response << " (outside calibrated range " << (long)SensorSupply::CALIBRATED_MIN_MV
					<< "-" << (long)SensorSupply::CALIBRATED_MAX_MV << " mV)";
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
					response << (_sensorSupply.IsVsenEnabled() ? "vsen_en ON, " : "vsen_en OFF, ")
						<< (long)_sensorSupply.GetRequestedVoltage_mV() << " mV";
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
	const uint32_t requested = _sensorSupply.GetRequestedVoltage_mV();
	p << " cal=" << (requested == 0 ? "off" :
		(requested >= SensorSupply::CALIBRATED_MIN_MV && requested <= SensorSupply::CALIBRATED_MAX_MV
		? "interpolated" : "extrapolated"));
}

void App::HandleCommand(const BufferView<> &cmd, Comm &sourceSession)
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
					mv = mv < 0 ? 0 : (mv > (long)ANALOG_VREF_MV ? (long)ANALOG_VREF_MV : mv);
					_dac.SetVoltage((float)mv / 1000.0f);
					response << "DAC set to " << mv << "mV";
				}
			}
			else if (token2 == "dac1") {
				long mv;
				scanner >> mv;
				if (!scanner.IsError()) {
					mv = mv < 0 ? 0 : (mv > (long)ANALOG_VREF_MV ? (long)ANALOG_VREF_MV : mv);
					_dac.SetVoltage((float)mv / 1000.0f);
					response << "DAC1 set to " << mv << "mV";
				}
			}
			else if (token2 == "dac2") {
				long mv;
				scanner >> mv;
				if (!scanner.IsError()) {
					response << "ERROR dac2 unavailable: PA5 reserved for ain 1";
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
			if (token2 == "ain") {
				long channel;
				scanner >> channel;
				if (!scanner.IsError() && channel >= 1 && channel <= 4) {
					ReadAnalogInput((uint8_t)channel, response);
				}
			}
			else if (token2 == "time") {
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
		else if (token1 == "pulse") {
			if (token2 == "vai") {
				long channel, mv, durationMs;
				scanner >> channel >> mv >> durationMs;
				if (!scanner.IsError() && channel >= 1 && channel <= SensorSupply::VAI_COUNT &&
				    mv >= 0 && mv <= (long)SensorSupply::MAX_MV &&
				    durationMs >= 10 && durationMs <= 3600000) {
					if (_sensorSupply.StartPulse((uint8_t)channel, (uint32_t)mv, (uint32_t)durationMs)) {
						response << "vai " << channel << (_sensorSupply.IsVaiActive((uint8_t)channel) ? " ON pulse_ms=" : " OFF pulse_ms=")
							<< durationMs << "\r\n";
						AppendSensorSupplyStatus(response);
					}
					else {
						response << "ERROR pulse vai " << channel << " busy or pwm unavailable";
					}
				}
			}
		}
		else if (token1 == "start") {
			if (token2 == "wm") {
				long id, cycleTimeMs;
				scanner >> id >> cycleTimeMs;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT) {
					_wmSim[id - 1].Start((uint32_t)cycleTimeMs);
					response << "wm " << id << " started";
				}
			}
			else if (token2 == "wm_timed") {
				long id, cycleTimeMs, durationMs;
				scanner >> id >> cycleTimeMs >> durationMs;
				if (!scanner.IsError() && id >= 1 && id <= WM_SIM_COUNT &&
				    cycleTimeMs >= 20 && cycleTimeMs <= 3600000 &&
				    durationMs >= 20 && durationMs <= 3600000) {
					_wmSim[id - 1].Start((uint32_t)cycleTimeMs, (uint32_t)durationMs);
					response << "wm " << id << " started duration_ms=" << durationMs;
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
			else if (token2 == "vai") {
				long channel;
				scanner >> channel;
				if (!scanner.IsError() && channel >= 1 && channel <= SensorSupply::VAI_COUNT &&
				    _sensorSupply.StopPulse((uint8_t)channel)) {
					response << "vai " << channel << " OFF pulse cancelled\r\n";
					AppendSensorSupplyStatus(response);
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
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();
			
			helpPrinter << " system init\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set time HH:MM\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get time\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get status\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set dac1 <mV>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get ain <1-4> (0-10V; PA5 reserved for AI1, DAC2 disabled)\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set ps <id> on|off\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vsen <mV>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vsen_en on|off\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " set vai <1-4> on|off\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();
			helpPrinter << " pulse vai <1-4> <mV> <10-3600000 ms>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();
			helpPrinter << " stop vai <1-4>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " get vsen\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " start wm <id> <cycle_ms>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " start wm_timed <id> <cycle_ms> <20-3600000 ms>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " stop wm <id>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " trigger wm <id> <cycle_ms>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

			helpPrinter << " toggle wm <id>\r\n";
			sourceSession.SendResponse(helpBuf); helpBuf.Reset();

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

	sourceSession.SendResponse(respBuf);
}
