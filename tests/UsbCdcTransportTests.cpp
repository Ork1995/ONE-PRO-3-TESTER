#include <algorithm>
#include <cassert>
#include <deque>
#include <iostream>
#include <string>
#include <vector>
#include "UsbCdcTestSupport.hpp"
#define private public
#include "UsbCdcTransport.hpp"
#include "Comm.hpp"
#undef private
#include "UsbCdcBridge.h"

bool fakeInterrupt = false;
static bool failThread = false;
static uint32_t rearmed = 0;
static USBD_CDC_HandleTypeDef cdc = {};
USBD_HandleTypeDef hUsbDeviceFS = {};
struct TaskPause {};

osThreadId_t osThreadNew(void (*)(void *), void *, const osThreadAttr_t *attributes)
{
	return failThread ? nullptr : (attributes->cb_mem ? attributes->cb_mem : &cdc);
}
osSemaphoreId_t osSemaphoreNew(uint32_t, uint32_t initial, const osSemaphoreAttr_t *attributes)
{
	auto semaphore = attributes ? static_cast<StaticSemaphore_t *>(attributes->cb_mem) : new StaticSemaphore_t;
	semaphore->count = initial;
	return semaphore;
}
osMutexId_t osMutexNew(const osMutexAttr_t *attributes) { return osSemaphoreNew(1, 1, attributes); }
int osSemaphoreAcquire(osSemaphoreId_t semaphore, uint32_t)
{
	if (!semaphore->count) return -1;
	--semaphore->count;
	return osOK;
}
int osSemaphoreRelease(osSemaphoreId_t semaphore) { semaphore->count = 1; return osOK; }
int osMutexAcquire(osMutexId_t mutex, uint32_t timeout) { return osSemaphoreAcquire(mutex, timeout); }
int osMutexRelease(osMutexId_t mutex) { return osSemaphoreRelease(mutex); }
void osDelay(uint32_t) { throw TaskPause{}; }
void MX_USB_DEVICE_Init() {}
uint8_t USBD_CDC_SetTxBuffer(USBD_HandleTypeDef *, uint8_t *buffer, uint32_t length)
{
	cdc.TxBuffer = buffer;
	cdc.TxLength = length;
	return USBD_OK;
}
uint8_t USBD_CDC_SetRxBuffer(USBD_HandleTypeDef *, uint8_t *) { return USBD_OK; }
uint8_t USBD_CDC_ReceivePacket(USBD_HandleTypeDef *) { ++rearmed; return USBD_OK; }
uint8_t USBD_CDC_TransmitPacket(USBD_HandleTypeDef *) { cdc.TxState = 1; return USBD_OK; }

class MemoryTransport : public IByteTransport
{
public:
	std::deque<uint8_t> input;
	std::string output;
	int Receive(uint8_t *buffer, int length) override {
		int received = 0;
		while (received < length && !input.empty()) {
			buffer[received++] = input.front(); input.pop_front();
		}
		return received;
	}
	bool Send(const BufferView<uint8_t> &buffer) override {
		output.append(reinterpret_cast<const char *>(buffer.begin()), buffer.Len()); return true;
	}
	bool IsConnected() const override { return true; }
	void Feed(const std::string &text) { input.insert(input.end(), text.begin(), text.end()); }
};

static void Pump(Comm &session) { try { session.Task(); } catch (const TaskPause &) {} }
static void Configure(UsbCdcTransport &transport)
{
	assert(transport.Start());
	cdc = {};
	hUsbDeviceFS = { USBD_STATE_CONFIGURED, &cdc };
	assert(USBD_Interface_fops_FS.Init() == USBD_OK);
}
static std::string Drain(UsbCdcTransport &transport)
{
	std::string output;
	while (transport._txRead != transport._txWrite) {
		transport.Service();
		assert(transport._inFlight != 0);
		output.append(reinterpret_cast<char *>(cdc.TxBuffer), cdc.TxLength);
		cdc.TxState = 0;
		fakeInterrupt = true;
		USBD_Interface_fops_FS.TransmitCplt(nullptr, nullptr, 1);
		fakeInterrupt = false;
	}
	return output;
}
static void Receive(const std::string &text)
{
	uint32_t length = text.size();
	assert(length <= 64);
	std::copy(text.begin(), text.end(), UserRxBufferFS);
	fakeInterrupt = true;
	USBD_Interface_fops_FS.Receive(UserRxBufferFS, &length);
	fakeInterrupt = false;
}

int main()
{
	MemoryTransport uart;
	Comm uartSession(uart);
	uart.Feed("get time\r\nget status\n");
	Pump(uartSession);
	Buffer<256> command;
	assert(uartSession.ReceiveCommand(command, 0) && command == "get time");
	assert(uart.output == "get time\r\n");
	Pump(uartSession);
	assert(uartSession.ReceiveCommand(command, 0) && command == "get status");
	assert(uart.output == "get time\r\nget status\r\n");

	UsbCdcTransport usb;
	Configure(usb);
	Comm::Resources usbResources = {};
	Comm usbSession(usb, &usbResources);
	Receive("get "); Pump(usbSession);
	assert(!usbSession.ReceiveCommand(command, 0));
	Receive("time\nget status\r\n"); Pump(usbSession);
	assert(usbSession.ReceiveCommand(command, 0) && command == "get time");
	assert(usb.BeginResponse());
	uint8_t reply[] = "OK\r\n";
	usbSession.SendResponse(BufferView<uint8_t>(4, reply, 4));
	usb.EndResponse();
	assert(Drain(usb) == "get time\r\nOK\r\n");
	assert(uart.output == "get time\r\nget status\r\n");
	Pump(usbSession);
	assert(usbSession.ReceiveCommand(command, 0) && command == "get status");
	assert(Drain(usb) == "get status\r\n");

	uint8_t temporary[] = "stack data";
	assert(usb.Send(BufferView<uint8_t>(10, temporary, 10)));
	std::fill(temporary, temporary + 10, 'x');
	usb.Service();
	assert(std::string(reinterpret_cast<char *>(cdc.TxBuffer), cdc.TxLength) == "stack data");
	usb.OnSuspend(true);
	assert(!usb.IsConnected());
	usb.Service();
	assert(usb._inFlight == 10);
	usb.OnSuspend(false);
	assert(Drain(usb) == "stack data");

	std::vector<uint8_t> full(4096, 'a');
	assert(usb.Send(BufferView<uint8_t>(4096, full.data(), 4096)));
	assert(!usb.BeginResponse());
	assert(!usb.Send(BufferView<uint8_t>(4, reply, 4)));
	assert(Drain(usb) == std::string(4096, 'a'));
	for (const int length : { 1, 63, 64, 65, 127, 128, 512, 2048, 4095, 4096 }) {
		assert(usb.Send(BufferView<uint8_t>(length, full.data(), length)));
		assert(Drain(usb) == std::string(length, 'a'));
	}
	assert(usb.Send(BufferView<uint8_t>(4, reply, 4)));
	cdc.TxState = 1;
	usb.Service();
	assert(usb._inFlight == 0);
	cdc.TxState = 0;
	assert(Drain(usb) == "OK\r\n");
	assert(usb.BeginResponse());
	assert(usb.Send(BufferView<uint8_t>(2048, full.data(), 2048)));
	assert(!usb.Send(BufferView<uint8_t>(1, reply, 1)));
	assert(usb.SendForSession(BufferView<uint8_t>(2048, full.data(), 2048), usb.SessionId()));
	usb.EndResponse();
	assert(Drain(usb).size() == 4096);

	Receive("discard this"); Pump(usbSession);
	const uint32_t oldSession = usb.SessionId();
	UsbCdc_Reset(); Configure(usb);
	Receive("get time\n"); Pump(usbSession);
	assert(usbSession.ReceiveCommand(command, 0) && command == "get time");
	assert(usb.BeginResponse());
	assert(!usb.SendForSession(BufferView<uint8_t>(4, reply, 4), oldSession));
	usb.EndResponse();
	Drain(usb);
	Receive("get status\n"); Pump(usbSession);
	assert(usbSession.ReceiveCommand(command, 0));
	UsbCdc_Reset(); Configure(usb);
	assert(usb.BeginResponse());
	usbSession.SendResponse(BufferView<uint8_t>(4, reply, 4));
	usb.EndResponse();
	assert(Drain(usb).empty());
	uint32_t reservedSession;
	assert(usb.BeginResponse(&reservedSession));
	UsbCdc_Reset(); Configure(usb);
	Receive("get time\n"); Pump(usbSession);
	assert(!usbSession.ReceiveCommand(command, 0, reservedSession));
	assert(usb.BeginResponse(&reservedSession));
	assert(usbSession.ReceiveCommand(command, 0, reservedSession) && command == "get time");
	usbSession.SendResponse(BufferView<uint8_t>(4, reply, 4));
	usb.EndResponse();
	assert(Drain(usb) == "get time\r\nOK\r\n");
	assert(usb.Send(BufferView<uint8_t>(4, reply, 4)));
	usb.Service();
	assert(usb._inFlight == 4);
	UsbCdc_Reset(); Configure(usb);
	assert(Drain(usb).empty());

	std::string packet(64, 'b');
	for (int index = 0; index < 16; ++index) Receive(packet);
	const uint32_t previousRearm = rearmed;
	usb.Service();
	assert(rearmed == previousRearm);
	uint8_t readBuffer[64];
	assert(usb.Receive(readBuffer, 64) == 64);
	usb.Service();
	assert(rearmed == previousRearm + 1);
	Receive(packet);
	Receive("overflow");
	assert(!usb.IsConnected() && usb.GetDiagnostics().rxOverflow == 1);

	uint8_t coding[] = { 0x00, 0xC2, 0x01, 0, 0, 0, 8 };
	assert(USBD_Interface_fops_FS.Control(CDC_SET_LINE_CODING, coding, 7) == USBD_OK);
	std::fill(coding, coding + 7, 0);
	assert(USBD_Interface_fops_FS.Control(CDC_GET_LINE_CODING, coding, 7) == USBD_OK);
	assert(coding[1] == 0xC2 && coding[6] == 8);
	assert(USBD_Interface_fops_FS.Control(CDC_GET_LINE_CODING, coding, 6) == USBD_FAIL);
	hUsbDeviceFS = {};
	assert(CDC_Transmit_FS(reply, 4) == USBD_FAIL);
	failThread = true;
	UsbCdcTransport failed;
	assert(!failed.Start() && failed.GetDiagnostics().startupFailures == 1);
	uart.Feed("get time\n"); Pump(uartSession);
	assert(uartSession.ReceiveCommand(command, 0) && command == "get time");
	std::cout << "PASS: framing, fragmentation, routing, TX ownership, reservation, wrap, reset, suspend, backpressure, line coding, startup failure\n";
}