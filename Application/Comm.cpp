/*
 * Comm.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#include "Comm.hpp"
#include <algorithm>

Comm::Comm(Uart &uart): _uart(uart), _isCmdReady(false)
{
	_cmdReady = osSemaphoreNew(1, 0, NULL);
	_cmdAccess = osMutexNew(NULL);

	const osThreadAttr_t attrs = {
		.name = "Comm",
		.stack_size = 4096,
		.priority = (osPriority_t) osPriorityNormal,
	};
	osThreadNew([](void *arg) { ((Comm *) arg)->Task(); }, this, &attrs);
}

bool Comm::IsCmdReady()
{
	MutexLock lock(_cmdAccess);
	return _isCmdReady;
}

void Comm::Task()
{
	bool lastWasCR = false;

	while (true) {
		if (IsCmdReady()) {
			osDelay(10);
			continue;
		}

		uint8_t rxByte;
		if (!_uart.Recv(&rxByte, 1)) {
			osDelay(10);
			continue;
		}

		MutexLock lock(_cmdAccess);

		// Accept common line endings from terminal:
		// - '\r' (CR) or '\n' (LF) terminate a command
		// - If terminal sends "\r\n", ignore the '\n' after '\r'
		if (rxByte == '\r') {
			lastWasCR = true;
			_isCmdReady = true;
			osSemaphoreRelease(_cmdReady);

			// Echo newline
			uint8_t nl[] = "\r\n";
			_uart.Send(BufferView<uint8_t>(2, nl, 2));
		}
		else if (rxByte == '\n') {
			if (lastWasCR) {
				lastWasCR = false;
				continue;
			}
			_isCmdReady = true;
			osSemaphoreRelease(_cmdReady);

			// Echo newline
			uint8_t nl[] = "\r\n";
			_uart.Send(BufferView<uint8_t>(2, nl, 2));
		}
		else {
			lastWasCR = false;
			_cmd.Append((char) rxByte);

			// Echo characterfghfgh
			_uart.Send(BufferView<uint8_t>(1, &rxByte, 1));
		}
	}
}

void Comm::SendResponse(const BufferView<> &response)
{
	MutexLock lock(_cmdAccess);
	_uart.Send(response);
}

bool Comm::ReceiveCommand(BufferView<> &cmdBuf, uint32_t timeoutMs)
{
	if (osSemaphoreAcquire(_cmdReady, timeoutMs) != osOK) {
		return false;
	}

	MutexLock lock(_cmdAccess);

	if (!_isCmdReady) {
		return false;
	}

	cmdBuf = _cmd;

	_cmd.Reset();
	_isCmdReady = false;

	return true;
}
