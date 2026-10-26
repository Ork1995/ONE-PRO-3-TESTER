#pragma once

#include "BufferView.hpp"
#include <cstdint>

class IByteTransport
{
public:
	virtual ~IByteTransport() = default;
	virtual int Receive(uint8_t *buffer, int length) = 0;
	virtual bool Send(const BufferView<uint8_t> &buffer) = 0;
	virtual bool IsConnected() const = 0;
	virtual uint32_t SessionId() const { return 0; }
	virtual int ReceiveForSession(uint8_t *buffer, int length, uint32_t &session)
	{
		session = SessionId();
		return Receive(buffer, length);
	}
	virtual bool SendForSession(const BufferView<uint8_t> &buffer, uint32_t session)
	{
		return session == SessionId() && Send(buffer);
	}
	virtual bool SendEcho(const BufferView<uint8_t> &buffer, uint32_t session)
	{
		return SendForSession(buffer, session);
	}
};