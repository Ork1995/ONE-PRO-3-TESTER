#pragma once

#include "IByteTransport.hpp"
#include "Uart.hpp"

class UartTransport : public IByteTransport
{
public:
	explicit UartTransport(Uart &uart): _uart(uart) {}
	int Receive(uint8_t *buffer, int length) override { return _uart.Recv(buffer, length); }
	bool Send(const BufferView<uint8_t> &buffer) override { return _uart.Send(buffer); }
	bool IsConnected() const override { return true; }

private:
	Uart &_uart;
};