/*
 * Comm.hpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include "Uart.hpp"
#include "MutexLock.hpp"
#include "Buffer.hpp"

class Comm
{
public:
	static const int MAX_CMD_LEN = 256;
	static const int MAX_TOKEN_LEN = 30;
	static const int MAX_RESP_LEN = 200;

	Comm(Uart &uart);

	void SendResponse(const BufferView<> &response);
	bool ReceiveCommand(BufferView<> &cmdBuf, uint32_t timeoutMs = 10);

private:
	Uart &_uart;
	Buffer<MAX_CMD_LEN> _cmd;
	bool _isCmdReady;
	osSemaphoreId_t _cmdReady;
	osMutexId_t _cmdAccess;

	bool IsCmdReady();
	void Task();
};
