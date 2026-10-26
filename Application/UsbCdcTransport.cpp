#include "UsbCdcTransport.hpp"
#include "UsbCdcBridge.h"
#include "usb_device.h"
#include "usbd_cdc_if.h"
#include "usbd_core.h"
#include "cmsis_os2.h"
#include <algorithm>

extern uint8_t UserRxBufferFS[];
extern USBD_HandleTypeDef hUsbDeviceFS;

namespace {
UsbCdcTransport *usbTransport = nullptr;

class UsbCriticalSection
{
public:
	UsbCriticalSection(): _mask(portSET_INTERRUPT_MASK_FROM_ISR()) {}
	~UsbCriticalSection() { portCLEAR_INTERRUPT_MASK_FROM_ISR(_mask); }
private:
	UBaseType_t _mask;
};
}

bool UsbCdcTransport::Start()
{
	if (_worker) {
		return true;
	}
	usbTransport = this;
	const osThreadAttr_t attributes = {
		.name = "USB CDC",
		.attr_bits = 0,
		.cb_mem = &_workerControl,
		.cb_size = sizeof(_workerControl),
		.stack_mem = _workerStack,
		.stack_size = sizeof(_workerStack),
		.priority = osPriorityBelowNormal,
		.tz_module = 0,
		.reserved = 0,
	};
	_worker = static_cast<TaskHandle_t>(osThreadNew([](void *argument) {
		static_cast<UsbCdcTransport *>(argument)->Task();
	}, this, &attributes));
	if (!_worker) {
		OnStartupFailed();
	}
	return _worker != nullptr;
}

void UsbCdcTransport::Notify()
{
	if (!_worker) {
		return;
	}
	if (__get_IPSR() != 0) {
		BaseType_t woken = pdFALSE;
		vTaskNotifyGiveFromISR(_worker, &woken);
		portYIELD_FROM_ISR(woken);
	}
	else {
		xTaskNotifyGive(_worker);
	}
}

void UsbCdcTransport::Task()
{
	MX_USB_DEVICE_Init();
	for (;;) {
		ulTaskNotifyTake(pdTRUE, pdMS_TO_TICKS(10));
		Service();
	}
}

void UsbCdcTransport::Service()
{
	UsbCriticalSection lock;
	if (!_configured || _suspended || hUsbDeviceFS.dev_state != USBD_STATE_CONFIGURED ||
		!hUsbDeviceFS.pClassData) {
		return;
	}
	if (!_rxArmed && RX_SIZE - (_rxWrite - _rxRead) >= CDC_DATA_FS_MAX_PACKET_SIZE) {
		USBD_CDC_SetRxBuffer(&hUsbDeviceFS, UserRxBufferFS);
		_rxArmed = USBD_CDC_ReceivePacket(&hUsbDeviceFS) == USBD_OK;
	}
	if (_inFlight == 0 && _txWrite != _txRead) {
		const uint32_t index = _txRead % TX_SIZE;
		_inFlight = std::min<uint32_t>(CDC_DATA_FS_MAX_PACKET_SIZE,
			std::min<uint32_t>(_txWrite - _txRead, TX_SIZE - index));
		const uint8_t status = CDC_Transmit_FS(&_tx[index], _inFlight);
		if (status != USBD_OK) {
			_inFlight = 0;
			if (status != USBD_BUSY) {
				++_diagnostics.txFailures;
			}
		}
	}
}

int UsbCdcTransport::Receive(uint8_t *buffer, int length)
{
	uint32_t session;
	return ReceiveForSession(buffer, length, session);
}

int UsbCdcTransport::ReceiveForSession(uint8_t *buffer, int length, uint32_t &session)
{
	int received = 0;
	{
		UsbCriticalSection lock;
		session = _session;
		if (!_configured || _suspended || TX_SIZE - (_txWrite - _txRead) < _reserved + 2) {
			return 0;
		}
		while (received < length && _rxRead != _rxWrite) {
			buffer[received++] = _rx[_rxRead++ % RX_SIZE];
		}
	}
	if (received) {
		Notify();
	}
	return received;
}

bool UsbCdcTransport::Queue(const BufferView<uint8_t> &buffer, uint32_t session, bool response)
{
	{
		UsbCriticalSection lock;
		const uint32_t length = buffer.Len();
		const uint32_t free = TX_SIZE - (_txWrite - _txRead);
		if (!_configured || session != _session || length > free ||
			(response ? length > _reserved : length + _reserved > free)) {
			++_diagnostics.txRejected;
			return false;
		}
		for (uint32_t index = 0; index < length; ++index) {
			_tx[_txWrite++ % TX_SIZE] = buffer[index];
		}
		if (response) {
			_reserved -= length;
		}
	}
	Notify();
	return true;
}

bool UsbCdcTransport::Send(const BufferView<uint8_t> &buffer)
{
	return Queue(buffer, SessionId(), false);
}

bool UsbCdcTransport::SendForSession(const BufferView<uint8_t> &buffer, uint32_t session)
{
	return Queue(buffer, session, true);
}

bool UsbCdcTransport::SendEcho(const BufferView<uint8_t> &buffer, uint32_t session)
{
	return Queue(buffer, session, false);
}

bool UsbCdcTransport::IsConnected() const
{
	UsbCriticalSection lock;
	return _configured && !_suspended;
}

uint32_t UsbCdcTransport::SessionId() const
{
	UsbCriticalSection lock;
	return _session;
}

bool UsbCdcTransport::BeginResponse(uint32_t *session)
{
	UsbCriticalSection lock;
	if (!_configured || _suspended || _reserved != 0 ||
		TX_SIZE - (_txWrite - _txRead) < RESPONSE_RESERVE) {
		return false;
	}
	_reserved = RESPONSE_RESERVE;
	if (session) {
		*session = _session;
	}
	return true;
}

void UsbCdcTransport::EndResponse()
{
	UsbCriticalSection lock;
	_reserved = 0;
}

UsbCdcTransport::Diagnostics UsbCdcTransport::GetDiagnostics() const
{
	UsbCriticalSection lock;
	return _diagnostics;
}

void UsbCdcTransport::Reset(bool configured)
{
	UsbCriticalSection lock;
	++_session;
	_configured = configured;
	_suspended = false;
	_rxArmed = configured;
	_rxRead = _rxWrite = 0;
	_txRead = _txWrite = 0;
	_inFlight = _reserved = 0;
}

void UsbCdcTransport::OnConfigured()
{
	Reset(true);
	Notify();
}

void UsbCdcTransport::OnReset()
{
	Reset(false);
	Notify();
}

void UsbCdcTransport::OnSuspend(bool suspended)
{
	{
		UsbCriticalSection lock;
		_suspended = suspended;
	}
	Notify();
}

void UsbCdcTransport::OnReceive(const uint8_t *buffer, uint32_t length)
{
	{
		UsbCriticalSection lock;
		_rxArmed = false;
		if (!_configured) {
			return;
		}
		if (length > CDC_DATA_FS_MAX_PACKET_SIZE || length > RX_SIZE - (_rxWrite - _rxRead)) {
			++_diagnostics.rxOverflow;
			Reset(false);
			return;
		}
		for (uint32_t index = 0; index < length; ++index) {
			_rx[_rxWrite++ % RX_SIZE] = buffer[index];
		}
	}
	Notify();
}

void UsbCdcTransport::OnTransmitComplete()
{
	{
		UsbCriticalSection lock;
		_txRead += _inFlight;
		_inFlight = 0;
	}
	Notify();
}

void UsbCdcTransport::OnStartupFailed()
{
	{
		UsbCriticalSection lock;
		++_diagnostics.startupFailures;
	}
	OnReset();
}

extern "C" {
void UsbCdc_Configured(void) { if (usbTransport) usbTransport->OnConfigured(); }
void UsbCdc_Reset(void) { if (usbTransport) usbTransport->OnReset(); }
void UsbCdc_Suspend(void) { if (usbTransport) usbTransport->OnSuspend(true); }
void UsbCdc_Resume(void) { if (usbTransport) usbTransport->OnSuspend(false); }
void UsbCdc_Receive(const uint8_t *buffer, uint32_t length) { if (usbTransport) usbTransport->OnReceive(buffer, length); }
void UsbCdc_TransmitComplete(void) { if (usbTransport) usbTransport->OnTransmitComplete(); }
void UsbCdc_StartupFailed(void) { if (usbTransport) usbTransport->OnStartupFailed(); }
}