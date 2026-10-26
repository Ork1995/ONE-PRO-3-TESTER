/*
 * Comm.cpp
 *
 *  Created on: Mar 26, 2025
 *      Author: Igor
 */

#include "Comm.hpp"
#include <algorithm>

Comm::Comm(IByteTransport &transport, Resources *resources):
	_transport(transport), _isCmdReady(false), _resettable(resources != nullptr)
{
	osSemaphoreAttr_t readyAttributes = {};
	osMutexAttr_t accessAttributes = {};
	if (resources) {
		readyAttributes.cb_mem = &resources->ready;
		readyAttributes.cb_size = sizeof(resources->ready);
		accessAttributes.cb_mem = &resources->access;
		accessAttributes.cb_size = sizeof(resources->access);
	}
	_cmdReady = osSemaphoreNew(1, 0, resources ? &readyAttributes : NULL);
	_cmdAccess = osMutexNew(resources ? &accessAttributes : NULL);

	osThreadAttr_t attrs = {
		.name = "Comm",
		.stack_size = 4096,
		.priority = (osPriority_t) osPriorityNormal,
	};
	if (resources) {
		attrs.name = "USB Comm";
		attrs.cb_mem = &resources->task;
		attrs.cb_size = sizeof(resources->task);
		attrs.stack_mem = resources->stack;
		attrs.stack_size = sizeof(resources->stack);
		attrs.priority = osPriorityBelowNormal;
	}
	_thread = (_cmdReady && _cmdAccess) ?
		osThreadNew([](void *arg) { ((Comm *) arg)->Task(); }, this, &attrs) : nullptr;
}

void Comm::SynchronizeSession()
{
	if (_resettable && _session != _transport.SessionId()) {
		_session = _transport.SessionId();
		_cmd.Reset();
		_isCmdReady = false;
		_lastWasCR = false;
		osSemaphoreAcquire(_cmdReady, 0);
	}
}

bool Comm::IsCmdReady()
{
	MutexLock lock(_cmdAccess);
	SynchronizeSession();
	return _isCmdReady;
}

void Comm::Task()
{
	while (true) {
		if (IsCmdReady()) {
			osDelay(10);
			continue;
		}

		uint8_t rxByte;
		uint32_t receivedSession = 0;
		if (!_transport.ReceiveForSession(&rxByte, 1, receivedSession)) {
			osDelay(10);
			continue;
		}

		MutexLock lock(_cmdAccess);
		if (_resettable) {
			SynchronizeSession();
			if (receivedSession != _session) {
				continue;
			}
		}

		// Accept common line endings from terminal:
		// - '\r' (CR) or '\n' (LF) terminate a command
		// - If terminal sends "\r\n", ignore the '\n' after '\r'
		if (rxByte == '\r') {
			_lastWasCR = true;
			_isCmdReady = true;
			osSemaphoreRelease(_cmdReady);

			// Echo newline
			uint8_t nl[] = "\r\n";
			_transport.SendEcho(BufferView<uint8_t>(2, nl, 2), _session);
		}
		else if (rxByte == '\n') {
			if (_lastWasCR) {
				_lastWasCR = false;
				continue;
			}
			_isCmdReady = true;
			osSemaphoreRelease(_cmdReady);

			// Echo newline
			uint8_t nl[] = "\r\n";
			_transport.SendEcho(BufferView<uint8_t>(2, nl, 2), _session);
		}
		else {
			_lastWasCR = false;
			_cmd.Append((char) rxByte);

			// Echo characterfghfgh
			_transport.SendEcho(BufferView<uint8_t>(1, &rxByte, 1), _session);
		}
	}
}

void Comm::SendResponse(const BufferView<> &response)
{
	MutexLock lock(_cmdAccess);
	_transport.SendForSession(response, _replySession);
}

void Comm::SendEvent(const BufferView<> &response)
{
	MutexLock lock(_cmdAccess);
	_transport.Send(response);
}

bool Comm::ReceiveCommand(BufferView<> &cmdBuf, uint32_t timeoutMs, uint32_t expectedSession)
{
	if (osSemaphoreAcquire(_cmdReady, timeoutMs) != osOK) {
		return false;
	}

	MutexLock lock(_cmdAccess);
	SynchronizeSession();

	if (!_isCmdReady) {
		return false;
	}
	if (_resettable && expectedSession != UINT32_MAX && expectedSession != _session) {
		osSemaphoreRelease(_cmdReady);
		return false;
	}

	cmdBuf = _cmd;
	_replySession = _session;

	_cmd.Reset();
	_isCmdReady = false;

	return true;
}
