#pragma once

#include "IByteTransport.hpp"
#include "FreeRTOS.h"
#include "task.h"

class UsbCdcTransport : public IByteTransport
{
public:
	static constexpr uint32_t RX_SIZE = 1024;
	static constexpr uint32_t TX_SIZE = 4096;
	static constexpr uint32_t RESPONSE_RESERVE = 2048;

	struct Diagnostics {
		uint32_t rxOverflow;
		uint32_t txRejected;
		uint32_t txFailures;
		uint32_t startupFailures;
	};

	bool Start();
	int Receive(uint8_t *buffer, int length) override;
	int ReceiveForSession(uint8_t *buffer, int length, uint32_t &session) override;
	bool Send(const BufferView<uint8_t> &buffer) override;
	bool SendForSession(const BufferView<uint8_t> &buffer, uint32_t session) override;
	bool SendEcho(const BufferView<uint8_t> &buffer, uint32_t session) override;
	bool IsConnected() const override;
	uint32_t SessionId() const override;
	bool BeginResponse(uint32_t *session = nullptr);
	void EndResponse();
	Diagnostics GetDiagnostics() const;

	void OnConfigured();
	void OnReset();
	void OnSuspend(bool suspended);
	void OnReceive(const uint8_t *buffer, uint32_t length);
	void OnTransmitComplete();
	void OnStartupFailed();

private:
	uint8_t _rx[RX_SIZE] = {};
	uint8_t _tx[TX_SIZE] = {};
	uint32_t _rxRead = 0, _rxWrite = 0;
	uint32_t _txRead = 0, _txWrite = 0;
	uint32_t _inFlight = 0, _reserved = 0;
	uint32_t _session = 0;
	bool _configured = false, _suspended = false, _rxArmed = false;
	Diagnostics _diagnostics = {};
	TaskHandle_t _worker = nullptr;
	StaticTask_t _workerControl;
	StackType_t _workerStack[512];

	bool Queue(const BufferView<uint8_t> &buffer, uint32_t session, bool response);
	void Reset(bool configured);
	void Notify();
	void Task();
	void Service();
};