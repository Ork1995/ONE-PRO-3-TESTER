/*
 * Comm.hpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#pragma once

#include "IByteTransport.hpp"
#include "MutexLock.hpp"
#include "Buffer.hpp"
#include "FreeRTOS.h"
#include "task.h"
#include "semphr.h"

class Comm
{
public:
	static const int MAX_CMD_LEN = 256;
	static const int MAX_TOKEN_LEN = 30;
	static const int MAX_RESP_LEN = 200;

	struct Resources {
		StaticTask_t task;
		StackType_t stack[1024];
		StaticSemaphore_t ready;
		StaticSemaphore_t access;
	};

	Comm(IByteTransport &transport, Resources *resources = nullptr);

	void SendResponse(const BufferView<> &response);
	void SendEvent(const BufferView<> &response);
	bool ReceiveCommand(BufferView<> &cmdBuf, uint32_t timeoutMs = 10, uint32_t expectedSession = UINT32_MAX);
	bool IsReady() const { return _thread && _cmdReady && _cmdAccess; }

private:
	IByteTransport &_transport;
	Buffer<MAX_CMD_LEN> _cmd;
	bool _isCmdReady;
	osSemaphoreId_t _cmdReady;
	osMutexId_t _cmdAccess;
	osThreadId_t _thread;
	bool _resettable;
	bool _lastWasCR = false;
	uint32_t _session = 0;
	uint32_t _replySession = 0;

	bool IsCmdReady();
	void SynchronizeSession();
	void Task();
};
